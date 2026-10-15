---
name: plan
description: Create a source-verified, bounded implementation plan. Only run when the user explicitly asks with /plan.
disable-model-invocation: true
argument-hint: <request to plan>
---

Plan this request using the routing in `CLAUDE.md` and the gates in `.claude/knowledge/GATES.md`. Delegate discovery to `explore-plan` when the scope is non-trivial. Do not edit files or run destructive actions: $ARGUMENTS
