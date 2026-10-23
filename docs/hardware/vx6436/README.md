# HW-VX6436 migration candidate — 2026-10-23

Target: useful rack coverage around **1 metre**. This is a documented protocol
implementation tested with synthetic transports, **not physical acceptance**.
No connected reader was accessed; no settings, tags, data or backups changed.

## Official sources and provenance

- [Electron product page](https://electron.id/produk/hw-vx6436/): published
  0–100 cm, USB/RS232, 1–26 dBm and anti-collision >50 tags/s. These are vendor
  specifications, not measured rack performance.
- [SDK share linked by Electron](https://cloud.electron.id/s/BGRA6cMJP8fk8Ak).
  The web research tool could not open the share, but direct HTTPS download
  from its `/download` URL succeeded. The earlier Stage 5 download blocker is
  superseded. Retrieved ZIP SHA256:
  `81263c41fbb27756ec39e881e3f20e213312f7d389205f4d20d4560a4ef5e6db`.
- Archive member `Electron HW-VX6436/4 Protocol/Electron HW-VX6436 UHF RFID
  Reader User's Manual v1.10.pdf`, SHA256
  `0e607e6c52b9c5852f26cee54de059d856a39114b9ac5377e677dc87f8fe88d1`.
- Archive member `Electron HW-VX6436/3 DEMO/PYTHON/hw-vx6436-python-doc-protocol.zip`,
  SHA256 `bb0555f12f1e4df5b25969deccefaa504f1511dd5a8c11685c880bb46ca7100d`.

Original download and extracted inspection files remain in
`/tmp/tpt-vx6436-sdk-download` and `/tmp/tpt-vx6436-inspect/` for this session;
they are not runtime dependencies and may not survive reboot. No vendor binary
or demo was executed. The archive also supplies Windows RRU9816 DLLs, which
are not used by this Python 3.8 / ARM64 candidate.

## Verified wire contract

| Manual section | Candidate implementation |
| --- | --- |
| §§1–3 | Default 57600 8N1; length excludes itself, reflected CRC16 0x8408/0xFFFF, LSB first. Shared framing primitives only are reused from VX6336. |
| §8.2.1 | Inventory `0x01`, minimal data `04 00` = Q=4, Session=S0. Mask, TID, target, antenna and scan-time options omitted. Frame at address 0: `06 00 01 04 00 AC 36`. |
| §8.2.1 | Payload: antenna=1, count, then EPC byte length, EPC, raw RSSI for each tag. RSSI is not labelled calibrated dBm. |
| §5, §8.2.1 | `03` continues; `01` completes. `02` timeout and `04` process limit cannot prove absence. Standalone `FB` with no data or complete antenna=1/count=0 proves an empty inventory. |
| §8.3.1 | Reader info `0x21`; 12-byte data, model type `0F`, EPC capability bit1. Scan time is stored units of 100 ms; read only, never set. |
| §8.3.7 | `0x40` controls automatic beep enable. No documented one-shot alarm matching the app's buzzer contract. No beep/config command is implemented. |

The Python demo is corroborating evidence only. Its inventory builder uses a
one-byte mask address where the PDF specifies two; its response validation is
weak. Its `main.py` includes an automatic **EPC write** example: do not execute
or import it. Our codec follows the PDF's minimal EPC-only request and checks
payload lengths, antenna, trailing bytes and CRC independently of that demo.

## Factory and driver design

`RFID_READER_MODEL` defaults to `vx6336`. `RFID_READER_ENABLED=false` always
selects the existing app mock; unknown model names raise rather than falling
back. `vx6436` selects a separate `VX6436Reader`, never a VX6336 subclass.

`VX6436Reader.start()` raises before starting a thread unless a test transport
factory is explicitly injected in Python. There is no physical serial opener
or environment switch that unlocks it. Injection exists only for offline tests.
Status reports `hardware_validated=false`, `transport=blocked` (or `test`),
and `buzzer_supported=false`. Leave deployed settings unchanged.

The candidate preserves scan state, debounce and complete inventory listeners,
including valid empty rounds. It has one transport owner, reads identity before
polling, reconnects on transport/protocol failure, and exposes bounded aggregate
timing without EPCs. EPCs remain uppercase hex strings. Buzzer calls log an
unsupported warning and send no bytes; no command queue is needed until a
safe alarm command is documented. The only command builders are inventory and
reader-info. There are no tag write, power, region, baud, scan-time or beep
setting builders.

Tests use constructed frames, not device captures. They establish the code's
behavior under those fixtures, not actual firmware compatibility or RF range.

## Physical validation still required (not executed)

1. Obtain a candidate unit and confirm model/firmware, appropriate regional
   certification, vendor-approved power supply and antenna. Have the vendor
   provide compliant Indonesian regional settings; do not copy advertised
   power blindly. No setting command is authorized in this task.
2. With separate authorization for the candidate-device session, stop any
   competing serial owner. Verify USB VID/PID, Linux serial bridge support,
   device path and permissions on the Jetson, without running a vendor demo.
3. Capture only documented read-only `0x21` and minimal `0x01` exchanges.
   Confirm type `0F`, EPC support, 12-byte info, response address, CRC, EPC/RSSI
   layout, complete empty rounds and multiframe endings. Reject mismatched
   identity; never try the VX6336 profile as a fallback. Add sanitized synthetic
   equivalents of captures to fixtures. Retain any real identifiers privately.
4. Benchmark existing unchanged tool tags at 0.25/0.5/0.75/1.0 m and outside
   the rack (e.g. 1.25/1.5 m). Repeat facing/edge-on, installed on metal and
   normal mounting, single-tag and all-tools conditions. Over repeated runs
   record first acquisition p50/p95, per-tag read rate, longest missed-read
   gap, inventory p95, partial/error rates and reads outside the intended zone.
   Agree acceptable acquisition latency and outside-zone detection before
   declaring the one-metre target accepted; vendor tags/s is not app round Hz.
5. Exercise removals, reapproach, simultaneous tools, disconnect/reconnect and
   power cycle. Check alarms do not arise from partial/failed inventories and
   presence thresholds fit measured gaps. Keep current thresholds until measured.
6. Resolve the missing alarm buzzer through vendor documentation or a separate
   verified output. Do not map app alarm calls to persistent beep settings.
   Only after these checks implement/review the production serial opener and
   separately authorize activation/deployment. No deployment is authorized here.

Remaining blockers are physical firmware/USB acceptance, measured one-metre
coverage and outside-rack rejection, regional device suitability, and an alarm
output. The official serial protocol itself has now been found and inspected.
