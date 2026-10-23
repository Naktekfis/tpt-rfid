# VX6336: one-tag placement acquisition

Prepared offline; physical results are pending. Do not repeat app deployment or
VX6436 work. Use `scripts/vx6336_acquisition_probe.py`, not `rfid_probe.py`:
the latter exposes setting/buzzer options and EPC output.

## Limits and measurement

- Exactly three command codes, empty payload, address 00: Inventory 01,
  Inventory Single 0F, Get Reader Info 21. No 25/33/35/settings/tag writes.
- Protocol file loaded directly; no `utils/__init__`, app, config, DB, NFC,
  camera, reader factory or startup sequence. pyserial opens only in CLI main.
- Only one command outstanding. Default deadline 27 s covers the maximum
  documented ScanTime of 25.5 s. The deadline is not a reader setting.
- Timeout, incomplete multiframe response, damaged stream, invalid payload,
  unexpected command/address, or unexpected status stops the session, without
  retry, input-buffer flush, or another command. Do not rerun immediately.
- EPCs are transient in RAM for counting/one-tag validation; never printed or
  saved. No raw frames, logs, app state, or student records are collected.
- ENTER timestamp uses the host monotonic clock while inventory is active.
  A helper presses ENTER as the tag reaches its marked position. This includes
  human synchronization error and serial receive scheduling (10 ms read timeout);
  it does not claim sensor-accurate physical placement timing. Use the same helper
  throughout; optional video of ruler/placement/terminal can assess marker error
  without filming identifiers or people. Do not subtract guessed reaction times.

## Before physical work — wait for explicit readiness

The reusable wrapper is `scripts/vx6336_acquisition_run.sh`. A staged copy can
be named `run.sh` at the temporary directory root. It accepts an initially
active or inactive service; it stops/restores an initially active service and
leaves an initially inactive service inactive. Failed/transitional/unknown
service states abort. It checks port ownership in both cases, saves aggregate
output to a newly created private file, and waits 27 s after probe exit before
any automatic service restart. It does not automatically retry the probe.
If the service was initially inactive, starting kiosk afterwards is explicit:
`sudo systemctl start tpt-rfid.service`.

Finish any active loan/return operation first. Stopping `tpt-rfid.service` makes
the kiosk, NFC, UHF presence monitoring and app alarms unavailable for the test.
Keep tools/students out of active use during this window. The DB, configuration,
backups and deployed app source are not replaced. No service action or Jetson
command has been run as part of offline preparation.

Once the user is ready, verify current service/device state (do not reuse old
PIDs), then use the following sequence on Jetson. This is an operator procedure,
not an executed record:

```bash
systemctl is-active tpt-rfid.service
sudo systemctl stop tpt-rfid.service
systemctl is-active tpt-rfid.service
sudo fuser -v /dev/rfid-reader
```

`is-active` must report inactive after stop (its nonzero exit code is expected).
`fuser` must show no owner; absent utility is not proof of an unowned port. If
ownership cannot be checked, stop and inspect before opening. Do not kill an
unidentified process. Exclusive serial open supplements this check; it cannot
evict an already-open noncooperating reader process.

The new probe has not been transferred to Jetson. After readiness, stage just
the probe and pure protocol file in a fresh private temporary directory with
`scripts/` and `utils/` subdirectories. Preserve that directory and output; do
not write into `/home/tpt/tpt-rfid` or rerun an installer. Use the existing Jetson
Python environment, passing the absolute path to the staged script:

```bash
/home/tpt/tpt-rfid/.venv/bin/python /ABSOLUTE/PRIVATE/TEMP/scripts/vx6336_acquisition_probe.py --port /dev/rfid-reader --trials 5 --window 10
```

Run in an interactive terminal. Do not pipe stdin or stdout; stdout must remain
visible for placement cues. If recording a terminal transcript, save to a fresh
private filename, never overwrite an existing result. Output includes only
aggregate metrics, reader info and operator cues.

## Placement sequence

1. Use ONE loose test tag, the same tag and orientation for all attempts; no tag
   on metal for this first comparison. Keep reader, USB cable, support material,
   hand position and surroundings fixed. Remove all other UHF tags from range.
2. The casing permits 10, 20, 30 cm: mark these along the same axis, keeping
   the casing installed. Record whether the origin is the outer casing surface
   or antenna face, and the antenna-to-casing offset if known; do not invent an
   offset if it cannot be measured. Use a nonmetallic jig/ruler. Record tag
   orientation; compare orientations only in a separate experiment. The 30 cm
   point probes beyond the documented 0–20 cm range; misses there alone do not
   establish a reader fault.
3. For each trial, remove the tag well beyond range and press ENTER. The probe
   verifies at least two seconds of empty-field inventory. If tags are still
   detected, it warns and waits up to 30 seconds for removal and two consecutive
   empty seconds. A tag seen after arming but before the marker is recorded as
   `pre_marker_detected`; the trial continues, but its acquisition latency is
   excluded from placement-latency comparisons. Protocol failures stop immediately
   with byte/frame/status diagnostics.
4. Wait for `ARMED`. A helper presses ENTER exactly as the tag reaches the
   marked position. `MARK` prints the monotonic timestamp. Leave the tag still
   for the entire 10 s window, including if it is never detected. Wait for JSON
   results and the next REMOVE prompt before moving it. Do not bring it close
   first to obtain a read; that defeats measurement of acquisition at distance.
5. Five paired attempts per distance: 01/0F, 0F/01, 01/0F, 0F/01, 01/0F.
   Each command gets a fresh removal and placement. Total 30 marked windows,
   at least 6 minutes plus handling time. A longer second run can confirm a
   small/noisy difference; retain failures from both runs.

## Metrics and interpretation

If a tag was already detected during approach, `pre_marker_detected=true` and
`first_hit_ms=null`: the next repeated read must not be presented as initial
acquisition. `first_detection_relative_marker_ms` is negative in that case.
These trials still contribute stationary read rate and silence metrics, and are
counted separately as `pre_marker_attempts`, outside `acquisition_valid_attempts`.
When possible, approach laterally at the target height without passing closer
to the antenna. If all attempts acquire during approach, placement latency at
the final height remains unmeasured; report that limitation rather than a speedup.

Per eligible trial: `first_hit_ms` from MARK to first CRC-valid inventory frame carrying
a tag; `null` with `censored=true` means no hit within the full 10 s window.
`read_rate` is hit rounds / all rounds overlapping the window, including empty
rounds before first hit. `longest_silence_s` includes MARK-to-first-hit,
inter-hit gaps, and last-hit-to-window-end; an entirely missed trial is 10 s.
Frame arrival time is not the RF detection instant inside the reader.
The boundary-spanning round counts, but hits after window end do not.
Status counts and stream damage expose protocol problems separately.

The final `comparison` groups by distance and command: attempted/valid/invalid
counts, failed acquisitions, successful-only median/max first-hit latency,
round-weighted read rate, longest silence. Always report failures beside
successful-only latency; never treat null as zero or conclude from the fastest
successful trial alone. Five attempts are exploratory, not a precise tail
estimate. Multiple distinct tags invalidate a trial; the operator must ensure
the same physical tag is used across attempts. An interrupted/faulted window is
not a completed acquisition failure; partial summaries show incomplete rounds
and are excluded from the successful final comparison.

Compare at each distance, not across pooled distances. A benefit for 0F must
appear in placement latency/failure rate, not only stationary read rate.
Even if 0F helps this test, it cannot replace 01 for multi-tool presence: prior
two-tag tests showed starvation of a weaker/other tag.

## Recovery (including Ctrl+C or fault)

Exit probe and verify serial ownership is released. A timeout/Ctrl+C can leave
a command running in the reader: after process exit, wait at least 27 s before
starting any other serial client. Do not clear this by sending setting/reset
commands. If serial responses remain unreliable, leave the app stopped and
discuss device reconnection explicitly; do not launch competing retries.

```bash
sudo fuser -v /dev/rfid-reader
sudo systemctl start tpt-rfid.service
systemctl is-active tpt-rfid.service
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/
```

Verify active service, HTTP 200, one Gunicorn worker and that serial ownership
belongs to that worker. Use the existing aggregate status display to confirm
UHF/NFC/camera recovery; do not dump API payloads/journal containing identifiers.
Current deployed startup reads beep mode; it does not write beep settings.
No code rollback or DB restore is part of recovery. Presence may need its usual
stabilization time after restart. If service recovery fails, preserve output
and investigate without redeploying or restoring old reader code.

## Next experiments — choose only after results, separately authorized

No setting experiments are executed by this probe. These are conditional plans:

| Observed result | Next bounded experiment | Command/value | Risk and recovery |
| --- | --- | --- | --- |
| 0F consistently improves first acquisition/failures at equal distance | Repeat paired placement run at affected distances with 10 attempts per command | 01 vs 0F, empty payloads; `--trials 10` repeats all three distances | No stored change; stop probe, wait out pending command, restore service. Does not authorize changing app inventory mode. |
| Similar delays for 01/0F with short serial rounds, worsening with distance | Rotate the same tag 90 degrees in its plane, then separately test a nonmetallic support keeping distance/origin fixed | Same 21 + 01/0F; no setting value | Geometry can change coupling; restore original orientation/support and repeat baseline. No reader recovery write needed. |
| Long terminal waits, status 02, or timeouts correlate with acquisition delay | After inspecting complete status/timing evidence and obtaining setting authorization, compare ScanTime 3 (300 ms) against freshly read baseline | `25`, data `03`; verify through `21`; repeat exact placement protocol | Persistent setting; may truncate inventories and worsen coverage. Save fresh baseline ScanTime byte first (previous report FF, not assumed current). Restore via `25` with that exact byte, verify `21`, then resume app. Do not shorten host timeout as a substitute. This probe deliberately cannot send 25. |

Power was previously reported at the VX6336 maximum 13 dBm. Do not propose
increasing it beyond 13, invent Q/session settings from VX6436, or guess frequency
bytes from raw reader-info fields. Region/power changes require separately
verified model-specific documentation, permitted band, explicit byte values,
fresh baseline and recovery plan before authorization. EPC/tag writes are not
an acquisition-latency experiment.
