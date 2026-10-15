---
name: agent-config
description: Use when updating this repo's agent setup or knowledge (AGENTS.md, CONTEXT.md, CLAUDE.md, .claude/agents, .claude/skills, .claude/knowledge, .mcp.json).
---

# Agent config governance

Read `.claude/knowledge/README.md` for the index. Project facts go in `AGENTS.md` (shape, commands, gotchas) and `CONTEXT.md` (domain terms); generic agent behaviour stays in `CLAUDE.md` and `.claude/`. The code overrides stale prose: fix or delete docs that disagree with it. Evidence, caches, and local data stay in gitignored paths. Generic improvements belong back in the agent kit (`~/agent-kit/template/`) so other projects get them. Claude Code picks up changes to `.claude/` and `CLAUDE.md` on the next turn.
