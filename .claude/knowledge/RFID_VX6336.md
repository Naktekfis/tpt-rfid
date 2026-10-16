# RFID reader: Electron HW-VX6336

Source: `docs/hardware/vx6336/communication-protocol-v1.2.pdf` (authoritative) and `datasheet.pdf`. The vendor bundle in `RFID HW/` (gitignored) only has Windows SDKs (C#/VB6/Delphi/Java DLLs, VC DLL with C++ source) and Windows drivers. None of them run on the Jetson, so we talk to the reader's serial protocol directly from Python with `pyserial`, which is already in `requirements.txt`.

## Hardware
- Desktop USB UHF reader/writer, ISO18000-6C (EPC Gen2), 902–928 MHz, 0–13 dBm, built-in antenna, **0–20 cm** range (tap-style). Powered by USB, 120–200 mA.
- USB shows up as a virtual serial port. The bundle ships CP210x and CH340 Windows drivers, so the bridge chip is one of those. On Linux both have in-kernel drivers (`cp210x`, `ch341`), and the reader should appear as `/dev/ttyUSB*`. **Not yet verified on the Jetson's L4T kernel**: check `lsusb`, `dmesg`, and `ls /dev/ttyUSB*`. The user needs to be in the `dialout` group. Add a udev rule for a stable name such as `/dev/rfid-reader`.
- The hardware team confirmed the reader detects tags with the vendor's Windows demo app.

## Serial settings
57600 baud, 8 data bits, no parity, 1 stop bit (8N1). Bytes inside one frame must be < 15 ms apart. The reader handles one command at a time, and commands sent while it is busy are lost.

## Frames
- Command: `Len Adr Cmd Data[] CRC-LSB CRC-MSB`. `Len` excludes itself, so it is `len(Data) + 4`. `Adr` defaults to `0x00`, and `0xFF` broadcasts.
- Response: `Len Adr reCmd Status Data[] CRC-LSB CRC-MSB`. `Len` is `len(Data) + 5`. `reCmd` is `0x00` if the command was not recognised.
- CRC-16 covers every byte from `Len` through the end of `Data`. Preset `0xFFFF`, reflected polynomial `0x8408`, sent LSB first:
  ```python
  def crc16(data: bytes) -> int:
      crc = 0xFFFF
      for b in data:
          crc ^= b
          for _ in range(8):
              crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
      return crc
  ```
- Test vectors computed with the code above (use them in unit tests):
  - Inventory `04 00 01 DB 4B`
  - Inventory (Single) `04 00 0F A5 A2`
  - Get Reader Info `04 00 21 D9 6A`

## Commands we need
| Cmd | Name | Notes |
|---|---|---|
| `0x01` | Inventory | Response Data = `Num`, then per tag `EPCLen(1 byte) + EPC`. Status: `0x01` done, `0x02` scan time ran out (partial), `0x03` more frames follow, `0x04` reader buffer full. |
| `0x0F` | Inventory (Single) | Same layout, one tag. |
| `0x21` | Get Reader Information | Data = Version(2), Type, Tr_Type, DMaxFre, DMinFre, Power, ScanTime. Good for "is the reader alive?". |
| `0x25` | Set ScanTime | 3–255 × 100 ms, default 10 (1 s). Persistent. |
| `0x33` | Acousto-optic control | Data = `ActiveT, SilentT, Times` (each 0-255; ActiveT/SilentT in 50 ms). One-shot: beeps and flashes `Times` times, nothing is stored. Response `05 Adr 33 00`. The manual has **no** command to turn beep-on-read on or off. |
| `0x35` | Set Beep Mode | **Not in manual v1.2** (found in the UHFReader09-family SDK, tested on firmware 2.32). Data = 1 byte: `0x00` read (reply Data bit0: 1 = beep on every tag read), `0x80` off, `0x81` on (factory). Stored in the reader. Our readers are set to off; `0x33` still beeps. `vx6336.beep_mode_command()` allows only these three values; probe `--beep-mode read\|off\|on`. |

Status `0x00` = success and `0xFB` = no tag. The full status and tag error tables are in protocol §5–6.

## Dangerous commands (gated, see GATES.md)
Never send these from app code without explicit approval: Write Data `0x03`, Write EPC `0x04`, **Kill Tag `0x05` (permanent)**, Lock `0x06`, Block Erase `0x07`, ReadProtect `0x08–0x0B`, EAS `0x0C`, Block Lock `0x0E` (permanent), Block Write `0x10`, Set Region `0x22`, Set Address `0x24`, Set Baud Rate `0x28`, Set Power `0x2F`. Several of these permanently change tags or reader settings.

## Integration notes
- The tag ID used by the app is the EPC bytes as an uppercase hex string. This replaces the current `rfid_uid` values. Check what format existing rows and the old ESP32 path use before switching.
- Pure protocol code (frame build/parse, CRC) goes in its own module with unit tests built from the vectors above. The serial loop sits behind a Mock/Real factory, so the app still runs without a reader.
- Debounce: one tap produces several inventory hits while the tag is in range, so report a given EPC once per presence window.
- Implemented (step 4): `utils/vx6336.py` (protocol, only the safe commands can be built) and `utils/rfid_reader.py` (`VX6336Reader` thread polls Inventory `0x01`, `ScanDebouncer` with `RFID_ABSENT_TIMEOUT`, reconnects every 3 s if the port is missing). `GET /api/rfid/status` shows mode/connection. `vx6336.buzzer_command()` builds `0x33`; the app does not send it yet.
- Student cards (KTM) are read by a **different scanner** (user, 2026-10-16); that scanner is not integrated yet, leave it alone until the user says otherwise. Until then the app still treats every tap on the VX6336 as either a student or a tool. `clear()` does not reset the debouncer, so a card left on the reader is not re-reported as the next scan.
- Tested on the laptop 2026-10-16 (`scripts/rfid_probe.py`, read-only):
  - Bridge is **CH340 `1a86:7523`**. Ubuntu's `brltty` grabs it and `/dev/ttyUSB0` vanishes a second after plugging; `apt remove brltty` fixes it (install.sh does this).
  - Get Reader Info: firmware 2.32, type 0xD1, power 13 dBm (the max), DMaxFre 0x13 / DMinFre 0x40, ScanTime 0xFF (25.5 s). ScanTime does not slow polling: with no tag the reader answers in ~23 ms with status `0x01`, `Num=0` (not `0xFB`); with 1–3 tags 30–50 ms.
  - EPCs are 12 bytes (24 hex chars), e.g. `E28068940000401A2C141084`. Several tags in range are reported in one round (up to 3 seen), so the app must decide what to do when several tags are in the field at once.
  - `0x33` sent 2026-10-16 (`--beep 2,2,2`, frame `07 00 33 02 02 02 84 D8`): reader answered `05 00 33 00`. **The firmware beeps on every inventory round that sees a tag** (user, 2026-10-16: "many short beep" with one tag on the reader during continuous polling). The manual documents no way to turn that off, and `0x33 0,0,0` (accepted, status `0x00`) does not stop it (tested 2026-10-16). **Fix: `0x35` Set Beep Mode** (undocumented in our manual). Source: https://github.com/klks/UHFReader `LJYZN-105/PROTOCOL.md` and `Shared/Basic.cs` `SetBeep` (C# port of the vendor `Basic.dll` for the RRU9809/UHFReader09 family; its other command codes match our manual), and the Chinese vendor demo in https://github.com/wi1dcard/RFID-Toolkit (`USB 设备/演示软件/Csharp/UHFReader09demomain/Form1.cs`, panel 蜂鸣器开关). Data = 1 byte `BeepEn`: bit7 = 0 reads the current mode (reply Data = mode, bit0 1 = beep on), `0x80` writes beep off, `0x81` writes beep on (restore). Our bundled `Basic.dll` has no `SetBeep`, so firmware 2.32 may not support it (an unknown command answers `reCmd` 0x00). Probably stored in the reader. **Read test 2026-10-16 (user-approved): `05 00 35 00 6C A5` → `06 00 35 00 01 8A A5`, so firmware 2.32 supports `0x35` and the factory mode is `0x01` (beep on).** To restore factory: send `0x81`. **Write test 2026-10-16 (user-approved): `05 00 35 80 64 21` → `05 00 35 00 6C A5`; read-back mode `00`; `0x01` polling with 3 tags no longer beeps (user confirmed).** With beep mode off, `0x33 4,2,3` still beeps (user confirmed), so the buzzer stays usable for alarms. **The mode is stored: after unplugging and replugging (2026-10-16), `35 00` still reads `00`.** **Inventory (Single) `0x0F` does not beep** (user, 2026-10-16; probe `--single`, one still tag: 99.7% read rate, longest gap 0.05 s, empty rounds answer `0xFB`). `0x0F` returns at most one tag per round; First 2-tag test (2026-10-16): `0x0F` over 30 s reported only the strong tag (99.7%), never the weak one; `0x01` saw both (96.7% / 11%). Retest with two tags placed equally close: `0x01` read both (82.5% / 75%), `0x0F` over 30 s reported only one of them (84.6%) and never the other. **Conclusion: `0x0F` keeps answering with one tag and cannot do presence for many tags; presence must use `0x01`, which beeps.**
  - Probe `--stats --duration S --quiet` gives the per-EPC read rate, longest gap, and frames/tags per round. Empty field: ~42 rounds/s, 23 ms median. One still tag: read rate 82%, longest gap 0.07 s, ~30 ms rounds.
  - Not yet tested: multi-frame `0x03` (needs ~15-25 tags on the reader at once), tags on metal (KTM is out of scope for this reader).
