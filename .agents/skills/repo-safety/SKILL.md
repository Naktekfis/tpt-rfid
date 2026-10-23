---
name: repo-safety
description: Use when touching secrets, environment files, real user data, database migrations or deletion, deployment, or hardware/network-facing code.
---

# Repository safety

Read `.Codex/knowledge/GATES.md` first. Code and config in the repo are authoritative. Never print, copy, or commit secrets, `.env` contents, credentials, cookies, or real personal data; refer to them by name only. Use synthetic or fixture data for tests. For anything on the gate list, stop and confirm with the user before acting.
