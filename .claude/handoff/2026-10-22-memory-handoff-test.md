# Memory and handoff trial — 2026-10-22

## Goal and user decisions

The user asked what work was last active, then asked to try memory and handoff
("coba teknik memory dan handoff. anything"). This session demonstrates shared
file-based memory. No application changes, deployment, or commit was requested.

## Branch and working tree

- Branch: `main`; HEAD: `99cc143` (Jetson README update, 2026-10-16).
- Pre-existing changes: modified `AGENTS.md`; untracked `.agents/` and `.codex/`.
  They concern agent instructions, skills, hooks and MCP configuration. Preserve them.
- Updated in this trial: existing `CONTEXT.md` (domain vocabulary); added this handoff.
- Nothing committed or pushed in this session.

## Completed and verification

- Read Git status, recent commits, the AGENTS.md diff, and the complete
  `.claude/handoff/2026-10-16-face-presence-plan.md`.
- The latest application handoff's final status says phase 4 is complete and
  records 183 tests. Earlier "next phase 2" and "phase 4a in progress" sections
  in that same file are superseded by its final status. Tests were not rerun here.
- Confirmed vocabulary against `utils/models.py`, `utils/kiosk.py`, `config.py`
  using `rg`; recorded it in `CONTEXT.md`, preserving existing domain entries and
  updating the stale mandatory student RFID card description.
- Called codebase-memory MCP `list_projects`: this repository is not indexed.
  No indexing or MCP memory writes were performed.
- No native cross-session assistant memory was written; this demonstration uses
  repo files. A future session must read them to recover their contents.
- Generic `.agents/skills/agent-config/SKILL.md` refers to absent `.Codex/` paths;
  the project-specific `tpt-agent-config/SKILL.md` instead points to the existing
  `.claude/knowledge/` and lowercase `.codex/`. Neither skill was edited.
- `RTK.md`, referenced in the supplied instructions, was not found at repo root.
- No application code changed; no application tests required for this trial.

## Remaining work and next step

1. To test recall in a fresh session, read this file and `CONTEXT.md`, then check
   current Git status before describing the last work. Distinguish this memory
   trial from the earlier agent setup and application implementation.
2. Agent setup changes remain uncommitted and were not fully reviewed here.
3. Application continuation from the 2026-10-16 handoff: laptop walkthrough,
   then Jetson bring-up. Full-set RFID testing and USB webcam validation remain
   open according to that handoff; hardware availability was not checked here.

No blockers for this trial. Hardware, deployment and sensitive operations must
follow the repository's existing gates if a future task requests them.

Next command: `git status --short`, then read `CONTEXT.md` and this handoff.
