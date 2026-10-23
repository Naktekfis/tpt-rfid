# Overall HMI/RFID latency: deployed optimizations; mouse-triggered repaint unresolved

## User decisions and scope

User broadened diagnosis to the entire HMI and RFID, explicitly requested analysis/testing/patches through other agents and deployment to Jetson, and said all changes are allowed. These permissions supersede the older local-only/no-Jetson handoff restrictions for this task. Still preserve dirty work, real records/configuration/backups; no commits, tag writes, VX6436 activation, schema changes or face activation. No student payloads or credentials printed. Latest user wants to switch GPT-6.1 Sol from high to medium; continue from this handoff, not from scratch.

Latest observations: HMI improved but remains intermittently slow. Sometimes red status only visibly becomes normal/green when the mouse moves. Present→absent is slower than absent→present. Beep type remains uncertain (user selected both/unclear).

## State and completed patches

Local main, HEAD 99cc143, heavily dirty from prior work; preserve everything. RTK.md absent. AGENTS/GATES and target/reader/face references read. Safety skills applied. Earlier turns changed defaults missing_after 5→1.5 s and polls: kiosk/monitor/admin alerts 500 ms, admin tools 1000 ms. Admin type metadata now refreshes independently every 60 s/after edits.

Current work delegated: diagnose_overall_latency (read-only analysis), patch_query_latency (backend implementation), patch_frontend_latency (frontend implementation), patch_rfid_read_latency (reader diagnostics), test_frontend_latency (independent tests/review). All finished; reuse agents if helpful.

Backend removes image BLOB loading from get_all_tools_with_borrowers and get_tool_types; get_open_alarms fetches names in one joined query rather than N+1 photo loads. Frontend retains unchanged admin rows/photos, ignores volatile scan timestamps in render key, separates type requests from status, and guards overlapping polls. UI.fetchJSON bounds GET including JSON parsing at 5 s and respects caller cancellation; POST timeout/retry behavior unchanged. Reader patch adds anonymous status histograms, accepted-empty and rejected-with-valid-EPC counts; no reader command/settings/presence/recovery behavior change. Diagnostic poll field corrected to 0.5 s.

Deployed SIX selected files using exact fetched Jetson source baseline, not whole dirty local files:
- utils/database_handler.py
- utils/rfid_reader.py
- utils/rfid_diagnostics.py
- static/js/ui.js
- static/js/admin_monitor.js
- routes/diagnostics_routes.py

Local frontend includes older unrelated loadNotice/accessibility changes absent remotely; deployed candidate deliberately excludes them. Local reader has prior undeployed recovery/buzzer changes; those were NOT deployed. Never replace the whole local reader/tool_presence package blindly.

## Exact evidence and deployment

Local: scripts/check.sh → 352 passed, 1 skipped; Ruff passed. py_compile app/config/utils/routes passed. node --test tests/js/hmi_polling.test.js → 5 passed. After tiny diagnostic poll-field correction, tests/test_operational_diagnostics.py → 1 passed. Independent agent verified backend 4 new projection/contract cases, frontend 5 tests, and actual deployed reader candidate 9 tests. No concrete review findings.

Jetson synthetic in-memory benchmark (Python 3.8.0; 30 synthetic tools/types/students with 512KiB photos; 8 repetitions; session cache cleared each call; exact payload equality): median admin_tools 311.792→17.661 ms; types 138.317→17.293 ms; alarms 96.870→7.460 ms, queries31→1; board effectively unchanged20.275→20.183 ms. These are synthetic query timings, not real end-to-end screen latency.

Jetson tpt@10.42.0.14, app /home/tpt/tpt-rfid, service tpt-rfid. Deployment staging /home/tpt/tpt-overall-latency-tgTaukKL contains candidate/, remote-before/, source-before/ (code-only backup), manifest.json, installed-manifest.json, install.py, query_bench.py, jetson-query-bench.json, postdeploy-health.json. Installer checked source hashes, compiled candidates, stopped service, atomically replaced named files preserving permissions, restarted, probed safe device status; code-only rollback on failure. All six final and served JS hashes matched. Last health: active, MainPID11646, one worker, NRestarts0; recheck before acting. Browser Chromium97.0.4692.71.

Local artifacts /tmp/tpt-overall-latency-WYT4sC3C contain all fetched baselines/candidates, benchmark code and JSON, manifests/health. Frontend incremental baseline/patches /tmp/hmi-frontend-before. Earlier code-only backups remain /home/tpt/hmi-backups and /tmp/tpt-hmi-backups. No DB/config backups restored.

Fresh postdeploy UHF aggregate: 2822 rounds, all status01; zero timeouts/no-responses, skipped/incomplete rounds, rejected-with-EPC; accepted-empty0 means some tag was observed each round, NOT every target tag. Latest120 inventory mean53.859ms, p9560.239ms; listeners mean0.390ms. Safe device-status HTTP about5–7ms after first15ms. RAM available~2.3GB, load~0.3–0.6; no current saturation established.

## Facts versus unresolved hypotheses

Arrival/back emits immediately on first accepted sighting; departure waits missing_after and an accepted absent round. This explains directional asymmetry, not mouse-triggered paint. The default source is1.5s, but effective worker configuration is NOT freshly verified: previous inspection of master process environment does not prove dotenv-loaded worker configuration. Read only this nonsecret effective setting via bounded diagnostics if necessary; do not dump .env/environment or change auth.

ScanTime25500ms is a configured maximum, not measured cycle latency. Both deployed/local readers already use read(in_waiting or1); suspected fixed50ms host-read delay was disproved by agent. Synthetic serial4ms/fragmented9ms completes4ms/9ms. Physical placement→first target detection remains unmeasured; repeated-tag aggregates do not prove RF acquisition speed. Do not alter power/ScanTime or switch multi-tool inventory01 to single0F on this evidence.

Mouse clue: local kiosk+monitor synthetic DOM tests show missing→present on next500ms poll without any input events or rAF callbacks. Source has no mouse/focus/visibility gates; rAF only records optional timing after DOM updates. Actual Jetson kiosk.js/monitor.js were fetched late to remote-before/static/js; independent agent has not yet rerun identical harness on them.

Fresh display checks: DISPLAY=:0 xset q shows screen-saver timeout0 and DPMS Disabled. GSettings session idle-delay0, idle-dimfalse. Active window is focused/maximized Chromium (WM_CLASS chromium-browser), PID11810. No CDP listener on922x. Chromium process argv could not be parsed initially: this Jetson proc cmdline contains space-separated text with NO NULs. The initial empty flag lists were a parser artifact, not evidence no flags. Next parse with shlex.split after replacing NULs if any, output only allowlisted flags (GPU/background/debugging/type), never full URLs/arguments.

Launcher deploy/jetson/kiosk.sh disables X blanking, starts optional unclutter -idle0.5 -root, then normal Chromium kiosk flags. No launcher/GPU/compositor/cursor change made yet. Chromium/X scheduling or paint/cursor interaction is a hypothesis, not proven. Do not immediately disable GPU or shorten polling again.

## Next steps

1. Resume targeted diagnosis of mouse-triggered update. Determine whether polling/DOM pause or only pixels stay stale. Prefer anonymous DOM counts/visibility/focus/timing via existing debugger if available; no debugger currently listening. Do not take screenshots, force layout/getComputedStyle, move mouse or refresh before observation because these may trigger repaint and hide fault. If browser restart/instrumentation is needed, authorization already exists, but preserve current operation/session and make the intervention bounded.
2. Rerun independent no-input DOM test against fetched actual deployed kiosk/monitor. Parse actual Chromium flags correctly; inspect launcher/autostart without printing browsing URLs. Consider controlled unclutter/background scheduling experiment only based on branch evidence. No browser restart has been done by main in this work.
3. Verify effective missing_after safely if discussing asymmetry; avoid treating the master environment check as runtime proof. First target RF acquisition still needs an auditable physical placement marker/user assistance; beep category unclear.
4. User must reload browser once to load new JS. This has been requested repeatedly; do not assume it occurred. Backend deployment is verified; visible improvement is not yet physically accepted.

Next safe command: inspect this handoff/current Git status, then parse allowlisted Chromium process flags over SSH and pass fetched kiosk/monitor paths to independent tester. Preserve backend/query improvements; do not redeploy them unnecessarily.
