---
name: tpt-review
description: Explicitly review the current tpt-rfid diff for behavior-breaking issues without editing files.
---

This is the Codex equivalent of Claude Code's `/review`. Use the `test-review` agent for an independent pass when available and useful. Review against the task goal and repository contracts. Report only actionable findings with file location, concrete failure scenario, and a reproducible check. Do not edit files or repeat green checks without a concrete reason. Flag gated changes; review does not grant authorization.
