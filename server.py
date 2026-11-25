#!/usr/bin/env python3
"""krakeeb — a local, read-only browser for your Claude Code sessions.

Reads the session files Claude Code already keeps in ~/.claude/projects and shows
them as a tree of chats, branches and continuations. No LLM calls, no network.

Run:   python3 server.py            then open http://127.0.0.1:8765
Demo:  python3 server.py --demo     (made-up sessions, port 8799)
"""
import json, os, re, sys, glob, time, threading, subprocess, shlex
from collections import Counter
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HOME = os.path.expanduser("~")
CLAUDE = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")
PROJECTS = os.path.join(CLAUDE, "projects")
LIVE_DIR = os.path.join(CLAUDE, "sessions")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.expanduser(os.environ.get("KRAKEEB_DATA_DIR") or os.path.join(CLAUDE, "krakeeb"))
MARKS = os.path.join(DATA_DIR, "marks.json")
PORT = int(os.environ.get("KRAKEEB_PORT", "8765"))
IDLE_EXIT_MIN = float(os.environ.get("KRAKEEB_IDLE_MIN", "10"))
IGNORE_BG = os.environ.get("KRAKEEB_IGNORE_BG", "0") not in ("", "0", "false", "no")
DEMO = "--demo" in sys.argv

_cache = {}           # path -> (mtime, size, parsed)
_lock = threading.Lock()
_marks_lock = threading.Lock()


def iso_to_ms(s):
    try:
        import datetime
        return int(datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


CMD_RE = re.compile(r"<command-name>(.*?)</command-name>", re.S)
ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def prompt_text(rec):
    """Return the human-typed text of a user record, or None if it isn't a human prompt."""
    if rec.get("isMeta") or rec.get("isCompactSummary") or rec.get("toolUseResult") is not None:
        return None
    msg = rec.get("message") or {}
    c = msg.get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(c, str):
        return None
    t = c.strip()
    if not t:
        return None
    m = CMD_RE.search(t)
    if m:
        a = ARGS_RE.search(t)
        return (m.group(1).strip() + " " + (a.group(1).strip() if a else "")).strip()
    if t.startswith("<local-command") or t.startswith("<system-reminder") or t.startswith("<task-notification") \
            or t.startswith("Caveat:") or t.startswith("[Request interrupted"):
        return None
    return t


def parse_session(path):
    sid = os.path.basename(path)[:-6]
    d = dict(id=sid, file=path, size=os.path.getsize(path), mtime=int(os.path.getmtime(path) * 1000),
             first_ts=None, last_ts=None, custom_title=None, ai_title=None, agent_name=None,
             cwd=None, git_branch=None, version=None, entrypoints=[], kinds=[],
             own_msgs=0, inherited_msgs=0, prompts=[], inherited_prompts=0, branched_after=None,
             last_prompt=None, models={}, cost=None, lines_added=None, lines_removed=None,
             artifacts=[], remote=False, compactions=0, continued_in=[], fork_parent=None,
             fork_point=None)
    forked = Counter()
    entry, kinds, models = set(), set(), Counter()
    last_inherited_prompt = None
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return d
    with fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = r.get("type")
            ts = r.get("timestamp")
            ff = r.get("forkedFrom")
            if ts and not ff:
                ms = iso_to_ms(ts)
                if ms:
                    if d["first_ts"] is None or ms < d["first_ts"]:
                        d["first_ts"] = ms
                    if d["last_ts"] is None or ms > d["last_ts"]:
                        d["last_ts"] = ms
            if r.get("cwd") and not d["cwd"]:
                d["cwd"] = r["cwd"]  # starting directory = project dir (what --resume needs)
            if r.get("gitBranch"):
                d["git_branch"] = r["gitBranch"]
            if r.get("version"):
                d["version"] = r["version"]
            if r.get("entrypoint"):
                entry.add(r["entrypoint"])
            if r.get("sessionKind"):
                kinds.add(r["sessionKind"])
            if t in ("user", "assistant"):
                if r.get("isSidechain"):
                    continue
                if ff:
                    forked[ff.get("sessionId")] += 1
                    d["fork_point"] = ff.get("messageUuid")
                    d["inherited_msgs"] += 1
                    if t == "user":
                        p = prompt_text(r)
                        if p:
                            d["inherited_prompts"] += 1
                            last_inherited_prompt = p
                    continue
                d["own_msgs"] += 1
                if t == "assistant":
                    m = (r.get("message") or {}).get("model")
                    if m and not m.startswith("<"):
                        models[m] += 1
                else:
                    p = prompt_text(r)
                    if p:
                        d["prompts"].append({"ts": iso_to_ms(ts) if ts else None, "text": p[:1200]})
            elif t == "custom-title":
                d["custom_title"] = r.get("customTitle")
            elif t == "ai-title":
                d["ai_title"] = r.get("aiTitle")
            elif t == "agent-name":
                d["agent_name"] = r.get("agentName")
            elif t == "last-prompt":
                d["last_prompt"] = r.get("lastPrompt")
            elif t == "cost-state":
                d["cost"] = r.get("totalCostUSD")
                d["lines_added"] = r.get("totalLinesAdded")
                d["lines_removed"] = r.get("totalLinesRemoved")
            elif t == "frame-link":
                if r.get("frameUrl") or r.get("title"):
                    a = {"url": r.get("frameUrl"), "title": r.get("title"), "ts": iso_to_ms(ts) if ts else None}
                    if a not in d["artifacts"]:
                        d["artifacts"].append(a)
            elif t == "bridge-session":
                d["remote"] = True
            elif t == "continued-in":
                c = r.get("continuedInSessionId")
                if c and c not in d["continued_in"]:
                    d["continued_in"].append(c)
            elif t == "system" and r.get("subtype") == "compact_boundary":
                d["compactions"] += 1
    if forked:
        d["fork_parent"] = forked.most_common(1)[0][0]
        d["branched_after"] = (last_inherited_prompt or "")[:600] or None
    d["entrypoints"] = sorted(entry)
    d["kinds"] = sorted(kinds)
    d["models"] = dict(models.most_common())
    # title file written by /rename takes precedence
    tf = os.path.join(path[:-6], "custom-title.json")
    if os.path.exists(tf):
        try:
            d["custom_title"] = json.load(open(tf)).get("customTitle") or d["custom_title"]
        except Exception:
            pass
    # subagents
    subs = []
    for mf in sorted(glob.glob(os.path.join(path[:-6], "subagents", "*.meta.json"))):
        try:
            m = json.load(open(mf))
            jl = mf[:-10] + ".jsonl"
            subs.append({"description": m.get("description"), "type": m.get("agentType"),
                         "finished": m.get("finished", False),
                         "mtime": int(os.path.getmtime(jl) * 1000) if os.path.exists(jl) else None})
        except Exception:
            pass
    d["subagents"] = subs
    if d["last_ts"] is None:
        d["last_ts"] = d["mtime"]
    if d["first_ts"] is None:
        d["first_ts"] = d["last_ts"]
    return d


def pid_alive(pid):
    if os.name == "nt":  # os.kill(pid, 0) would terminate the process on Windows
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except Exception:
        return False


def live_sessions():
    out = {}
    rank = {"busy": 3, "shell": 2, "idle": 1}
    for f in glob.glob(os.path.join(LIVE_DIR, "*.json")):
        try:
            j = json.load(open(f))
        except Exception:
            continue
        sid = j.get("sessionId")
        if not sid or not pid_alive(j.get("pid")):
            continue
        info = {"pid": j.get("pid"), "status": j.get("status"), "kind": j.get("kind"),
                "name": j.get("name"), "entrypoint": j.get("entrypoint"), "updated": j.get("updatedAt"),
                "former_names": [x.get("name") for x in j.get("formerNames") or [] if x.get("name")]}
        prev = out.get(sid)
        if not prev or rank.get(info["status"], 0) > rank.get(prev["status"], 0):
            out[sid] = info
    return out


def load_marks():
    try:
        return json.load(open(MARKS))
    except Exception:
        return {}


def save_marks(m):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = MARKS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f, indent=1)
    os.replace(tmp, MARKS)


def scan():
    files = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    sessions = {}
    with _lock:
        for p in files:
            try:
                st = os.stat(p)
            except OSError:
                continue
            c = _cache.get(p)
            if not c or c[0] != st.st_mtime or c[1] != st.st_size:
                c = (st.st_mtime, st.st_size, parse_session(p))
                _cache[p] = c
            s = c[2]
            s["project_dir"] = os.path.basename(os.path.dirname(p))
            sessions[s["id"]] = s
        for p in list(_cache):
            if p not in files:
                del _cache[p]
    live = live_sessions()
    marks = load_marks()
    # parents: fork first, then continuation
    cont_parent = {}
    for s in sessions.values():
        for c in s["continued_in"]:
            cont_parent.setdefault(c, s["id"])
    out = []
    for s in sessions.values():
        parent, rel = None, None
        if s["fork_parent"] and s["fork_parent"] in sessions and s["fork_parent"] != s["id"]:
            parent, rel = s["fork_parent"], "branch"
        elif s["id"] in cont_parent and cont_parent[s["id"]] != s["id"]:
            parent, rel = cont_parent[s["id"]], "continued"
        light = {k: v for k, v in s.items() if k not in ("prompts", "file")}
        light["prompt_count"] = len(s["prompts"])
        light["first_prompt"] = s["prompts"][0]["text"][:400] if s["prompts"] else None
        light["latest_prompt"] = s["prompts"][-1]["text"][:400] if s["prompts"] else s["last_prompt"]
        light["parent"], light["relation"] = parent, rel
        light["live"] = live.get(s["id"])
        light["mark"] = marks.get(s["id"], {})
        out.append(light)
    # break cycles
    by = {s["id"]: s for s in out}
    for s in out:
        seen, cur = {s["id"]}, s.get("parent")
        while cur:
            if cur in seen:
                s["parent"] = None
                break
            seen.add(cur)
            cur = by.get(cur, {}).get("parent")
    return {"generated": int(time.time() * 1000), "home": HOME, "platform": sys.platform,
            "demo": DEMO, "sessions": out}


def detail(sid):
    for p, c in list(_cache.items()):
        if c[2]["id"] == sid:
            s = c[2]
            return {"id": sid, "prompts": s["prompts"], "subagents": s["subagents"],
                    "artifacts": s["artifacts"], "file": s["file"], "models": s["models"]}
    return None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _local_origin(self):
        o = self.headers.get("Origin")
        return o is None or o in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html")
        if u.path == "/api/ping":
            return self._send(200, '{"app":"krakeeb"}')
        if u.path == "/api/sessions":
            return self._send(200, json.dumps(scan()))
        if u.path == "/api/session":
            d = detail(parse_qs(u.query).get("id", [""])[0])
            return self._send(200 if d else 404, json.dumps(d or {"error": "not found"}))
        self._send(404, "{}")

    def do_POST(self):
        if not self._local_origin():
            return self._send(403, '{"error":"forbidden"}')
        u = urlparse(self.path)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except Exception:
            return self._send(400, '{"error":"bad json"}')
        sid = str(body.get("id", ""))
        if not re.fullmatch(r"[0-9a-f-]{36}", sid):
            return self._send(400, '{"error":"bad id"}')
        if u.path == "/api/mark":
            with _marks_lock:
                m = load_marks()
                cur = m.get(sid, {})
                for k in ("status", "note", "title"):
                    if k in body:
                        v = body[k]
                        if v in (None, ""):
                            cur.pop(k, None)
                        else:
                            v = str(v)
                            cur[k] = " ".join(v.split())[:200] if k == "title" else v[:2000]
                if cur:
                    m[sid] = cur
                else:
                    m.pop(sid, None)
                save_marks(m)
            return self._send(200, json.dumps(cur))
        if u.path == "/api/resume":
            if sys.platform != "darwin" or DEMO:
                return self._send(501, '{"error":"only available on macOS"}')
            cwd = next((c[2]["cwd"] for c in _cache.values() if c[2]["id"] == sid), None)
            if not cwd or not os.path.isdir(cwd):
                return self._send(404, '{"error":"cwd not found"}')
            cmd = f"cd {shlex.quote(cwd)} && claude --resume {sid}"
            script = f'tell application "Terminal" to do script {json.dumps(cmd)}\ntell application "Terminal" to activate'
            subprocess.Popen(["osascript", "-e", script])
            return self._send(200, '{"ok":true}')
        self._send(404, "{}")


def watchdog():
    """Exit once no Claude Code process has been alive for IDLE_EXIT_MIN minutes.
    With KRAKEEB_IGNORE_BG=1, background sessions don't count as 'in use'."""
    last_seen = time.time()
    while True:
        time.sleep(60)
        live = [s for s in live_sessions().values() if not (IGNORE_BG and s.get("kind") == "bg")]
        if live:
            last_seen = time.time()
        elif time.time() - last_seen > IDLE_EXIT_MIN * 60:
            print("No live Claude Code sessions; shutting down.", flush=True)
            os._exit(0)


if __name__ == "__main__":
    if DEMO:
        import tempfile
        sys.path.insert(0, os.path.join(HERE, "demo"))
        import make_demo
        root = tempfile.mkdtemp(prefix="krakeeb-demo-")
        make_demo.build(root)
        HOME = make_demo.DEMO_HOME
        PROJECTS, LIVE_DIR = os.path.join(root, "projects"), os.path.join(root, "sessions")
        DATA_DIR = os.path.join(root, "krakeeb")
        MARKS = os.path.join(DATA_DIR, "marks.json")
        PORT = int(os.environ.get("KRAKEEB_PORT", "8799"))
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        raise SystemExit(f"Port {PORT} already in use (already running?)")
    if IDLE_EXIT_MIN > 0 and not DEMO:
        threading.Thread(target=watchdog, daemon=True).start()
    print(f"krakeeb on http://127.0.0.1:{PORT}" + (" (demo data)" if DEMO else ""), flush=True)
    srv.serve_forever()
