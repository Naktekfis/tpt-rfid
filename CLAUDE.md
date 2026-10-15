@AGENTS.md

## Routing (you are `lead`)

The main session is `lead`: it owns scope, integration, risk calls, and the final report. Route work like this:

- Discovery, doc lookup, bounded planning → `explore-plan` (also `/plan`, `/reference`).
- Approved implementation or diagnosis → `build-bugfix`.
- Independent review/validation of a diff → `test-review` (also `/review`).
- UI inventory, flow spec, design review → `ui-review` (also `/ui-audit`).
- Agent setup and knowledge upkeep (this file, `AGENTS.md`, `CONTEXT.md`, `.claude/`) → `docs-knowledge`.

`explore-plan`, `test-review`, and `ui-review` are read-only (no Edit/Write in their `tools`); never ask them to change files.

## Gates and references

- Stop and confirm with the user before anything listed in `.claude/knowledge/GATES.md`.
- Pick sources by `.claude/knowledge/REFERENCE_POLICY.md`: checked-out code and lockfiles first, then official docs for the exact versions the project pins.
- Other files in `.claude/knowledge/` are read-on-demand, not preloaded.

## Token budget

- Do small tasks inline (≤ ~2 files, change already known). Delegate only when a subagent saves more context than its cold start costs.
- Every delegation uses this brief; the subagent must not re-derive what it states:
  ```
  Task: <one-sentence outcome>
  Decided: <decisions + reason; do not reopen>
  Where: <file:line / symbol already read + what it holds>
  Cause/context: <proven findings>
  Limits: do not touch <X>; do not re-read AGENTS.md/CLAUDE.md or the files above unless other lines are needed
  Outside limits: flag (and fix if trivial) anything the change breaks beyond these limits
  Verify: <exact commands>
  Report: decisions + files changed + check results, ~15 lines, no pasted diff
  ```
- Model per call: `build-bugfix` Opus; `explore-plan`, `test-review`, `ui-review`, `docs-knowledge` Sonnet (Opus for architecture or anything in GATES.md); Haiku only for mechanical search/log summaries.
- Light review by default: `test-review` reads the diff, reports only breaking findings, and does not re-run checks the implementer already reported green. Full review only when asked or gated.
- Run the full check command once at the end, by one agent. Read code by line ranges, pipe long output through `tail`.
