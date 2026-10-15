---
name: evidence
description: Record or update concise local delivery evidence. Only run when the user explicitly asks with /evidence.
disable-model-invocation: true
argument-hint: <what to record>
---

Write a short evidence note (what changed, commands run, results, open risks) under `.claude/evidence/` (gitignored), one file per task named `YYYY-MM-DD-<slug>.md`. Do not install tools or run destructive actions: $ARGUMENTS
