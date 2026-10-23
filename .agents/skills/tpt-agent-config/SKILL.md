---
name: tpt-agent-config
description: Maintain tpt-rfid agent instructions, Codex setup, or project knowledge when the user asks to update them.
---

Read `.claude/knowledge/README.md` to find the relevant project references. Keep shared project facts and commands in `AGENTS.md`, domain terms in `CONTEXT.md`, and Codex-specific setup under `.codex/` or `.agents/skills/`. Keep handoffs in `.claude/handoff/` so both agents can use them. Treat `CLAUDE.md` and Claude-specific settings as the existing Claude Code setup; change them only when the user asks for a shared change. Verify claims against the checked-out code and remove stale guidance rather than copying it into another file. Keep evidence and caches in gitignored paths.
