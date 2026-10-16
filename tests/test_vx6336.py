import pytest

from utils import vx6336


def response_frame(cmd, status, data=b"", addr=0x00):
    body = bytes((len(data) + 5, addr, cmd, status)) + data
    crc = vx6336.crc16(body)
    return body + bytes((crc & 0xFF, crc >> 8))


def inventory_data(*epcs):
    out = bytes((len(epcs),))
    for epc in epcs:
        raw = bytes.fromhex(epc)
        out += bytes((len(raw),)) + raw
    return out


EPC_A = "E2801160600002084C1A2B3C"
EPC_B = "300833B2DDD9014000000001"


@pytest.mark.parametrize(
    "frame",
    [
        "04 00 01 DB 4B",  # Inventory
        "04 00 0F A5 A2",  # Inventory (Single)
        "04 00 21 D9 6A",  # Get Reader Info
    ],
)
def test_crc_vectors_from_knowledge_doc(frame):
    raw = bytes.fromhex(frame)
    crc = vx6336.crc16(raw[:-2])
    assert raw[-2:] == bytes((crc & 0xFF, crc >> 8))


def test_command_builders_match_vectors():
    assert vx6336.inventory_command() == bytes.fromhex("040001DB4B")
    assert vx6336.inventory_single_command() == bytes.fromhex("04000FA5A2")
    assert vx6336.reader_info_command() == bytes.fromhex("040021D96A")


def test_set_scan_time_frame_and_range():
    frame = vx6336.set_scan_time_command(10)
    assert frame[:4] == bytes((0x05, 0x00, 0x25, 10))
    with pytest.raises(ValueError):
        vx6336.set_scan_time_command(2)


def test_buzzer_frame_and_range():
    frame = vx6336.buzzer_command(2, 1, 3)
    assert frame[:6] == bytes((0x07, 0x00, 0x33, 2, 1, 3))
    assert vx6336.parse_response(response_frame(0x33, 0x00)).status == 0
    with pytest.raises(ValueError):
        vx6336.buzzer_command(256, 0, 1)


def test_beep_mode_frames_match_hardware():
    # Captured from the reader (firmware 2.32) on 2026-10-16.
    assert vx6336.beep_mode_command(0x00) == bytes.fromhex("050035006CA5")
    assert vx6336.beep_mode_command(0x80) == bytes.fromhex("0500358064 21")
    with pytest.raises(ValueError):
        vx6336.beep_mode_command(0x01)


def test_parse_beep_mode():
    off = vx6336.parse_response(bytes.fromhex("06003500 0003B4"))
    on = vx6336.parse_response(response_frame(0x35, 0x00, b"\x01"))
    assert vx6336.parse_beep_mode(off) is False
    assert vx6336.parse_beep_mode(on) is True
    with pytest.raises(vx6336.ProtocolError):
        vx6336.parse_beep_mode(vx6336.parse_response(response_frame(0x35, 0x00)))


@pytest.mark.parametrize("cmd", [0x03, 0x04, 0x05, 0x06, 0x22, 0x24, 0x28, 0x2F])
def test_dangerous_commands_are_refused(cmd):
    with pytest.raises(ValueError):
        vx6336.build_command(cmd)


def test_parse_inventory_response():
    frame = response_frame(0x01, 0x01, inventory_data(EPC_A, EPC_B))
    resp = vx6336.parse_response(frame)
    assert resp.cmd == 0x01 and resp.status == 0x01
    assert vx6336.inventory_epcs(resp) == [EPC_A, EPC_B]


def test_no_tag_response_has_no_epcs():
    resp = vx6336.parse_response(response_frame(0x01, vx6336.STATUS_NO_TAG))
    assert vx6336.inventory_epcs(resp) == []


def test_bad_crc_rejected():
    frame = bytearray(response_frame(0x01, 0x01, inventory_data(EPC_A)))
    frame[-1] ^= 0xFF
    with pytest.raises(vx6336.ProtocolError):
        vx6336.parse_response(bytes(frame))


def test_truncated_epc_rejected():
    with pytest.raises(vx6336.ProtocolError):
        vx6336.parse_epcs(bytes((1, 12)) + b"\x01\x02")


def test_parse_reader_info():
    data = bytes((0x03, 0x01, 0x0C, 0x02, 0x4E, 0x00, 0x1A, 0x0A))
    info = vx6336.parse_reader_info(
        vx6336.parse_response(response_frame(0x21, 0x00, data))
    )
    assert info.version == (3, 1)
    assert info.scan_time == 10


def test_splitter_reassembles_chunks_and_resyncs():
    f1 = response_frame(0x01, 0x03, inventory_data(EPC_A))
    f2 = response_frame(0x01, 0x01, inventory_data(EPC_B))
    stream = b"\x00\xff" + f1 + f2  # leading garbage
    splitter = vx6336.FrameSplitter()
    out = []
    for i in range(0, len(stream), 3):
        out.extend(splitter.feed(stream[i : i + 3]))
    assert [vx6336.inventory_epcs(r) for r in out] == [[EPC_A], [EPC_B]]
    assert out[0].status == vx6336.STATUS_INVENTORY_MORE
    assert splitter.dropped >= 1


def test_splitter_skips_corrupt_frame():
    bad = bytearray(response_frame(0x01, 0x01, inventory_data(EPC_A)))
    bad[5] ^= 0x01
    good = response_frame(0x01, 0x01, inventory_data(EPC_B))
    out = vx6336.FrameSplitter().feed(bytes(bad) + good)
    assert [vx6336.inventory_epcs(r) for r in out] == [[EPC_B]]
