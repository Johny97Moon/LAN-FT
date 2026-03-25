"""
Simple JSON-based protocol:
  Header (4 bytes, big-endian uint32): length of JSON metadata
  JSON metadata: { "version": 1, "action": "...", "payload": { ... } }

Actions (sender → receiver):
  file        — transfer metadata (name, size, encrypted, is_folder, resume_offset)
  checksum    — SHA256 of the full file
  overwrite   — response to overwrite_prompt (yes | no | rename)

Actions (receiver → sender):
  ready           — ready to receive (offset = bytes already received for resume)
  overwrite_prompt — file exists, ask what to do
  done            — transfer complete (saved_as, checksum_ok)
  error           — error message
"""
import json
import struct

VERSION = 1
HEADER_SIZE = 4
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB — DoS protection

_UINT32 = struct.Struct(">I")


def encode_message(action: str, payload: dict) -> bytes:
    encoded = json.dumps(
        {"version": VERSION, "action": action, "payload": payload},
        ensure_ascii=False,
    ).encode("utf-8")
    return _UINT32.pack(len(encoded)) + encoded


def decode_message(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


def read_message(sock) -> dict:
    """Read a length-prefixed JSON message from socket."""
    raw_len = _recv_exact(sock, HEADER_SIZE)
    msg_len = _UINT32.unpack(raw_len)[0]
    if msg_len > MAX_MESSAGE_SIZE:
        raise ValueError(f"Message too large: {msg_len} bytes (max {MAX_MESSAGE_SIZE})")
    return decode_message(_recv_exact(sock, msg_len))


def _recv_exact(sock, n: int) -> bytearray:
    buf = bytearray(n)
    view = memoryview(buf)
    pos = 0
    while pos < n:
        received = sock.recv_into(view[pos:], n - pos)
        if not received:
            raise ConnectionError("Connection closed unexpectedly.")
        pos += received
    return buf
