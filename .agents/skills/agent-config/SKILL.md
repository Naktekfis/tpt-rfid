---
name: agent-config
description: Use when updating this repo's agent setup or knowledge (AGENTS.md, CONTEXT.md, AGENTS.md, .Codex/agents, .Codex/skills, .Codex/knowledge, .mcp.json).
---

# Agent config governance

Read `.Codex/knowledge/README.md` for the index. Project facts go in `AGENTS.md` (shape, commands, gotchas) and `CONTEXT.md` (domain terms); generic agent behaviour stays in `AGENTS.md` and `.Codex/`. The code overrides stale prose: fix or delete docs that disagree with it. Evidence, caches, and local data stay in gitignored paths. Generic improvements belong back in the agent kit (`~/agent-kit/template/`) so other projects get them. Codex picks up changes to `.Codex/` and `AGENTS.md` on the next turn.
