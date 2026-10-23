# VX6336 timeout and busy recovery — offline candidate

2026-10-23. Local software changes only. No Jetson commands, service changes,
physical tests, deployment, reader setting changes, or tag writes were performed.
The deployed software remains the version described in the earlier deployment
handoff. Current service state is unknown; check it only after fresh permission.

## Diagnosis from the previous local code

- Initial `response_timeout` was 1.5 s. Only a successful reader-info reply set
  it to `ScanTime / 10 + 0.5`. ScanTime 255 means 25.5 s and a 26 s deadline.
- Missing reader-info merely logged a warning, then startup sent beep-mode read
  and inventory using the 1.5 s fallback. Reconnect retained old info/timeout.
- A timed-out transaction returned silence or partial frames without recording
  an outstanding command. The next transaction reset the serial input buffer,
  used a fresh splitter, and immediately wrote again. Commands sent while busy
  can be lost; late inventory terminals can be discarded or attributed to a
  subsequent inventory because both have command byte 01.
- Stop was checked only after sending, allowing a startup follow-up after stop.

These are protocol-state failure paths established from code and synthetic
serial tests. They do not establish how often they occurred on the Jetson or
whether they explain the physical first-acquisition delay.

## Candidate behavior

`utils/rfid_reader.py` now uses:

1. A 26 s unknown inventory timeout, reset with reader-info on each connection.
   Valid info refines this to ScanTime + 500 ms. Invalid ScanTime outside 3..255
   is rejected. Short control requests use a separate 1.5 s response deadline.
2. A pending command/address and the same frame splitter across timeout. Before
   any next command, recovery reads and discards matching late frames until a
   terminal arrives. Status 03 continues recovery. Late EPCs and empty terminals
   never enter presence/debounce or a new round's first-EPC timing.
3. A bounded guard ending one additional 26 s after the original response
   deadline. If no matching terminal arrives, a fresh successful reader-info
   handshake is required before beep/inventory. Silence alone does not prove
   that the reader is idle. The guard survives serial exceptions/reconnects.
4. At most two reader-info attempts per startup/resynchronization. Each retry
   first honors outstanding recovery. Continued failure raises an I/O error;
   the existing thread closes the port and retries after its retry delay.
   Startup never proceeds to beep/inventory without successful reader-info.
5. Stop checks before sending and during reads/recovery. Production serial reads
   still use 50 ms timeouts, so a silent reader does not block stop for the full
   guard. No persistent setting command was added; startup beep inspection
   remains `35 00`.

Normal complete inventory rounds have no added delay. The fault path is
intentionally conservative: an inventory with no terminal can wait its response
allowance plus another 26 s before the info handshake. At maximum ScanTime that
is about 52 s from send, plus handshake/retry overhead. An earlier matching
terminal ends the guard immediately. Unknown busy startup can lose the first
info request: 1.5 s timeout + 26 s guard precedes retry if no info terminal arrives.

The protocol has no transaction IDs. Protection assumes one serial owner,
ordered firmware responses, and the documented maximum ScanTime. It cannot
prove safety against arbitrary firmware delays or another process issuing
commands. A reader that permanently refuses reader-info now stays unavailable
rather than continuing degraded polling. Hardware compatibility remains to be
validated only in a separately authorized session.

## Diagnostics and offline verification

Reader diagnostics add identifier-free state/counters:

- `recovering`: outstanding transaction, including during its initial wait.
- `needs_sync`: expired guard requires reader-info acknowledgment.
- `transaction_timeouts_total`: response deadlines reached, excluding stop.
- `recoveries_total`: attempts to drain an outstanding transaction.
- `recovery_terminals_total`: guards released by a matching late terminal.
- `recovery_expirations_total`: guards expired and require resynchronization.

Round `inventory` / `queued_commands` duration includes recovery done in that
phase. First-frame/EPC timing starts at the new inventory write and excludes
recovered frames. Complete-round-only presence semantics are unchanged.

`tests/test_vx6336_recovery.py` uses only synthetic serial events and a virtual
clock. It covers 25.5 s acquisition, missing startup info, late/fragmented
terminals, continued status 03, permanent silence, mandatory info handshake,
wrong address, reconnect after I/O errors, stale info reset, and stop during
startup/recovery. The existing offline pipeline benchmark now provides synthetic
21 acknowledgments without opening a port; its fault scenarios include the
full recovery guard (26,350 ms virtual dispatch versus the old 350 ms).

No new measurement of physical acquisition is available. Existing probe results
and backups remain untouched. ENTER placement is unsuitable because movement
can cause acquisition before ENTER; do not repeat it. Casing distances are
10/20/30 cm. Repeated reads cannot establish first-acquisition speed.
