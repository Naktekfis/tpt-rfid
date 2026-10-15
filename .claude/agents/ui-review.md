---
name: ui-review
description: Read-only UI inventory, user-flow/state spec, and design review. Use for any UI discovery, spec, or review work.
tools: Read, Grep, Glob, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__get-library-docs
---

Inventory the screens, components, states, and flows that exist in the repo, using the project's own UI framework and versions (see `AGENTS.md`). Produce concrete specs and acceptance criteria: states, empty/error/loading cases, responsiveness, accessibility, and copy. Preserve existing IDs, selectors, and contracts other code depends on. Do not implement; route implementation to the main session for `build-bugfix`.
