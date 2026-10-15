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
| `0x33` | Acousto-optic control | Buzzer/LED feedback on a successful scan. |

Status `0x00` = success and `0xFB` = no tag. The full status and tag error tables are in protocol §5–6.

## Dangerous commands (gated, see GATES.md)
Never send these from app code without explicit approval: Write Data `0x03`, Write EPC `0x04`, **Kill Tag `0x05` (permanent)**, Lock `0x06`, Block Erase `0x07`, ReadProtect `0x08–0x0B`, EAS `0x0C`, Block Lock `0x0E` (permanent), Block Write `0x10`, Set Region `0x22`, Set Address `0x24`, Set Baud Rate `0x28`, Set Power `0x2F`. Several of these permanently change tags or reader settings.

## Integration notes
- The tag ID used by the app is the EPC bytes as an uppercase hex string. This replaces the current `rfid_uid` values. Check what format existing rows and the old ESP32 path use before switching.
- Pure protocol code (frame build/parse, CRC) goes in its own module with unit tests built from the vectors above. The serial loop sits behind a Mock/Real factory, so the app still runs without a reader.
- Debounce: one tap produces several inventory hits while the tag is in range, so report a given EPC once per presence window.
- Implemented (step 4): `utils/vx6336.py` (protocol, only the safe commands can be built) and `utils/rfid_reader.py` (`VX6336Reader` thread polls Inventory `0x01`, `ScanDebouncer` with `RFID_ABSENT_TIMEOUT`, reconnects every 3 s if the port is missing). `GET /api/rfid/status` shows mode/connection. Buzzer `0x33` is not used yet (its data layout was not checked).
- Working assumption (user, 2026-10-15): student cards are UHF too and are read on the **same reader**. `clear()` does not reset the debouncer, so a card left on the reader is not re-reported as the next scan.
- Not yet tested against the real reader: response timing, multi-frame `0x03`, and EPC format of the actual cards.
