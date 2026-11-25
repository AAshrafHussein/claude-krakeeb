# Roadmap

Ideas for where Krakeeb could go next. Nothing here is promised; it's a list to discuss and add to. Open an issue to suggest something or to pick an item up.

**Ground rules every feature keeps:**
- **No LLM calls.** Everything shown comes from files already on disk.
- **Never changes `~/.claude`.** Krakeeb only reads Claude Code's files. Its own data lives in `~/.claude/krakeeb/`.
- **Local only.** Binds to `127.0.0.1` and loads nothing from the internet.
- **No dependencies.** Python standard library and one HTML file.

Size: **S** = an evening, **M** = a weekend, **L** = needs design first.

---

## Now: polish and robustness

| Feature | Why | Size |
|---|---|---|
| **Warn before Claude Code deletes old sessions** | Claude Code deletes transcripts older than `cleanupPeriodDays` (30 days by default). Show a countdown on old chats, and a banner when ★ Hot chats are close, with a pointer to the setting. | S |
| **"Lights left on" panel** | List sessions whose process has been open but idle for days (background ones especially), with a copyable command to close each. Krakeeb itself never kills anything. | S |
| **Keyboard navigation** | `j`/`k` to move, `Enter` to expand, `c` to copy the resume command, `h`/`o` to mark Hot/Obsolete. | S |
| **Plugin icon** | Fixes the one remaining `claude plugin validate` warning. | S |
| **Tests and CI** | Parser tests built on the demo data, plus a GitHub Action that runs them and `claude plugin validate` on every push. | M |
| **Format-change warning** | Claude Code's session format isn't a public API. Note lines that fail to parse, and show a gentle banner when Claude Code is newer than the last tested version. | S |
| **Clean up orphaned marks** | Drop marks and notes for sessions that no longer exist on disk. | S |

## Next: organising

| Feature | Why | Size |
|---|---|---|
| **Show rewinds as branches** | Rewinding inside a chat leaves several paths in the same file. Draw them in the tree like forks. | M |
| **Read-only transcript view** | Open a whole conversation in the page, with tool calls collapsed, instead of only your prompts. | M |
| **Compare branches** | Pick two branches and see side by side where they split and what each did after. | M |
| **Tags and custom groups** | Your own labels (e.g. `client-x`, `blocked`) alongside Hot/Obsolete, and grouping by tag instead of project. | M |
| **Bulk actions** | Select several chats and mark them Obsolete in one go. | S |
| **Saved filters and date ranges** | E.g. "Hot in acme-shop, last 14 days" as one click. | S |
| **Export a chat to Markdown** | Keep a copy of an important chat before Claude Code's cleanup removes it. | S |
| **Disk usage view** | Biggest sessions, size per project, total. Useful when deciding what to clear. | S |

## Later: bigger ideas

| Feature | Why | Size |
|---|---|---|
| **Search inside replies** | Search Claude's answers too, not just your prompts, using a local SQLite full-text index that's built on demand and can be deleted at any time. | L |
| **Activity and cost over time** | Per-project charts of sessions, prompts and cost per day, from the data already recorded. | M |
| **Subagent drill-down** | Expand a subagent to see its own prompt and outcome. | M |
| **Status line link** | An optional Claude Code status line showing "3 running · 1 idle for 4d", with the page URL. | S |
| **More terminals for Resume** | iTerm2, Ghostty and Warp on macOS; GNOME Terminal and Konsole on Linux; a setting to choose. | M |
| **Sync renames to Claude Code** | Renaming in Krakeeb only changes the name Krakeeb shows. An opt-in setting could also save it the way `/rename` does, so `claude --resume` shows the same name. That means writing to Claude Code's session files, so it must stay off by default, skip running sessions and be clearly labelled. | M |
| **Windows support** | A safe way to check for live processes on Windows, plus testing there. | M |

## Not planned

- **AI-written titles or summaries.** Krakeeb shows what already exists. Claude Code's own titles are used when present.
- **Deleting or editing sessions.** Cleanup stays in your hands. Krakeeb can tell you what to clean up and give you the command.
- **Cloud sync or sharing.** Your chats stay on your machine.
