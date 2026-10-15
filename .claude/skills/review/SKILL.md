---
name: review
description: Run a read-only independent review of the current changes. Only run when the user explicitly asks with /review.
disable-model-invocation: true
argument-hint: <request or diff>
---

Delegate this to the `test-review` subagent and report its findings. Do not edit files or run destructive actions: $ARGUMENTS
