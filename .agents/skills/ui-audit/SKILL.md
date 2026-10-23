---
name: ui-audit
description: Produce a read-only UI design audit. Only run when the user explicitly asks with /ui-audit.
disable-model-invocation: true
argument-hint: <area to audit>
---

Delegate this to the `ui-review` subagent to audit the UI flow, states, and acceptance criteria. Do not edit files or run destructive actions: $ARGUMENTS
