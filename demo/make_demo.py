"""Generate made-up Claude Code session files for `server.py --demo` and screenshots.

Writes the same record shapes Claude Code keeps on disk (projects/<dir>/<id>.jsonl,
custom titles, subagent metadata, live-process files) — all content is fictional.
"""
import json, os, time, uuid, random

DEMO_HOME = "/Users/demo"
NOW = time.time()
random.seed(7)


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".000Z"


def enc(path):
    return "".join(c if c.isalnum() else "-" for c in path)


class Session:
    def __init__(self, root, cwd, title=None, ai_title=None, branch="main"):
        self.root, self.cwd, self.id = root, cwd, str(uuid.uuid4())
        self.records, self.title, self.ai_title, self.branch = [], title, ai_title, branch
        self.subagents, self.last_uuid = [], None

    def _msg(self, kind, content, t, forked=None, model="claude-opus-5-5"):
        u = str(uuid.uuid4())
        r = {"type": kind, "uuid": u, "parentUuid": self.last_uuid, "sessionId": self.id,
             "timestamp": iso(t), "cwd": self.cwd, "gitBranch": self.branch, "version": "2.1.322",
             "entrypoint": "cli", "message": {"role": kind, "content": content}}
        if kind == "assistant":
            r["message"]["model"] = model
        if forked:
            r["forkedFrom"] = forked
        self.records.append(r)
        self.last_uuid = u
        return u

    def turn(self, prompt, t, forked=None):
        self._msg("user", prompt, t, forked)
        self._msg("assistant", [{"type": "text", "text": "…"}], t + 40, forked)

    def fork_from(self, parent, upto):
        """Copy the parent's first `upto` turns, as a branch does."""
        msgs = [r for r in parent.records if r["type"] in ("user", "assistant")][: upto * 2]
        for r in msgs:
            c = dict(r, sessionId=self.id, forkedFrom={"sessionId": parent.id, "messageUuid": r["uuid"]},
                     uuid=str(uuid.uuid4()), parentUuid=self.last_uuid)
            self.records.append(c)
            self.last_uuid = c["uuid"]

    def write(self, cost=None, extra=()):
        d = os.path.join(self.root, "projects", enc(self.cwd))
        os.makedirs(d, exist_ok=True)
        recs = list(self.records)
        if self.ai_title:
            recs.append({"type": "ai-title", "aiTitle": self.ai_title, "sessionId": self.id})
        if self.title:
            recs.append({"type": "custom-title", "customTitle": self.title, "sessionId": self.id})
        if cost is not None:
            recs.append({"type": "cost-state", "sessionId": self.id, "totalCostUSD": cost,
                         "totalLinesAdded": random.randint(40, 900), "totalLinesRemoved": random.randint(5, 300)})
        recs.extend(extra)
        with open(os.path.join(d, self.id + ".jsonl"), "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        for i, (desc, t) in enumerate(self.subagents):
            sd = os.path.join(d, self.id, "subagents")
            os.makedirs(sd, exist_ok=True)
            base = os.path.join(sd, f"agent-demo{i}")
            json.dump({"agentType": "general-purpose", "description": desc, "finished": True}, open(base + ".meta.json", "w"))
            open(base + ".jsonl", "w").close()
            os.utime(base + ".jsonl", (t, t))


def live(root, s, status, kind="interactive", name=None):
    d = os.path.join(root, "sessions")
    os.makedirs(d, exist_ok=True)
    json.dump({"pid": os.getpid(), "sessionId": s.id, "cwd": s.cwd, "kind": kind, "status": status,
               "name": name, "entrypoint": "cli", "updatedAt": int(NOW * 1000)},
              open(os.path.join(d, f"{s.id[:6]}.json"), "w"))


def build(root):
    H, D, M = 3600, 86400, 60
    shop, blog, cli = f"{DEMO_HOME}/code/acme-shop", f"{DEMO_HOME}/code/blog", f"{DEMO_HOME}/side/weather-cli"

    # acme-shop: a main chat with two branches and a continuation
    main = Session(root, shop, ai_title="Checkout flow refactor", branch="feat/checkout")
    t = NOW - 6 * D
    for p in ["The checkout page re-renders on every keystroke. Find out why and propose a fix.",
              "Go with option 2 — move the cart state into a reducer.",
              "Now add tests for the discount code path.",
              "Tests pass. Let's also look at the payment retry logic."]:
        main.turn(p, t); t += 3 * H
    main.subagents = [("Audit payment retry edge cases", NOW - 5 * D), ("Write reducer unit tests", NOW - 5 * D)]

    b1 = Session(root, shop, title="Checkout flow refactor (Branch)", branch="feat/checkout")
    b1.fork_from(main, 2)
    b1.turn("Actually, try the context-selector approach instead of a reducer and compare bundle size.", NOW - 4 * D)
    b1.turn("Context version is 4 KB bigger. Abandon it.", NOW - 4 * D + H)

    b2 = Session(root, shop, title="Checkout flow refactor (Branch 2)", branch="fix/stripe-webhook")
    b2.fork_from(main, 4)
    b2.turn("Stripe webhooks are arriving twice in staging — make the handler idempotent.", NOW - 26 * M)
    b2.turn("Add a migration for the processed_events table.", NOW - 3 * M)

    cont = Session(root, shop, ai_title="Checkout flow refactor", branch="feat/checkout")
    cont.turn("Picking up from yesterday: wire the new reducer into the mobile checkout too.", NOW - 20 * H)
    cont.turn("Ship it behind the new_checkout flag.", NOW - 19 * H)

    main.write(cost=4.12, extra=[{"type": "continued-in", "continuedInSessionId": cont.id, "sessionId": main.id}])
    b1.write(cost=0.88); b2.write(cost=1.37); cont.write(cost=0.64)

    old = Session(root, shop, ai_title="Upgrade to Node 22", branch="chore/node22")
    old.turn("Upgrade the project to Node 22 and fix whatever breaks.", NOW - 24 * D)
    old.turn("The jest config still fails on ESM imports.", NOW - 24 * D + 2 * H)
    old.write(cost=2.05)

    # blog
    post = Session(root, blog, ai_title="Draft: what I learned building a cache", branch="main")
    post.turn("Help me outline a post about the LRU cache I built at work. Keep it practical.", NOW - 2 * D)
    post.turn("Tighten the intro and add a diagram of the eviction order.", NOW - 2 * D + H)
    post.write(cost=0.41)
    post2 = Session(root, blog, branch="main")
    post2.turn("Set up a dark mode toggle for the blog that respects the OS setting.", NOW - 9 * D)
    post2.write(cost=0.22)

    # side project
    r = Session(root, cli, ai_title="Weather CLI with offline cache", branch="main")
    t = NOW - 3 * D
    for p in ["Build a small CLI that prints a 5-day forecast for a city name.",
              "Cache responses on disk for an hour so it works offline.",
              "Add a --units flag for metric or imperial."]:
        r.turn(p, t); t += 2 * H
    r.subagents = [("Compare free weather APIs", NOW - 3 * D)]
    rb = Session(root, cli, title="Weather CLI with offline cache (Branch)", branch="exp/tui")
    rb.fork_from(r, 2)
    rb.turn("What if this were a full-screen TUI instead? Sketch it with a sparkline per day.", NOW - 50 * M)
    r.write(cost=3.30); rb.write(cost=0.95)

    live(root, b2, "busy")
    live(root, rb, "idle", kind="bg")
    live(root, post, "idle")

    os.makedirs(os.path.join(root, "krakeeb"), exist_ok=True)
    json.dump({b1.id: {"status": "obsolete", "note": "Context approach lost — reducer won."},
               b2.id: {"status": "hot"}, old.id: {"status": "obsolete"}},
              open(os.path.join(root, "krakeeb", "marks.json"), "w"))
    return root


if __name__ == "__main__":
    import sys
    print(build(sys.argv[1] if len(sys.argv) > 1 else "/tmp/krakeeb-demo"))
