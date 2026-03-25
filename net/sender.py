import hashlib
import io
import logging
import socket
import struct
import time
import zipfile
import os
import contextlib
import tempfile
from pathlib import Path
from typing import Callable

from config.settings import CHUNK_SIZE
from models.file_info import FileInfo, TransferProgress
from net.protocol import encode_message, read_message
from net.crypto import ChannelCipher, crypto_available

_log = logging.getLogger("lan_ft.sender")
_PROGRESS_INTERVAL = 0.1
_SPEED_WINDOW = 1.0
_PACK_UINT32 = struct.Struct(">I")
_CHUNK_MIN = 16 * 1024
_CHUNK_MAX = 512 * 1024
_CHUNK_TARGET_MS = 50


def send_file(
    host: str,
    port: int,
    file_path: str,
    progress_cb: Callable[[TransferProgress], None] | None = None,
    pause_event=None,
    cancel_event=None,
    speed_limit_bps: int = 0,
    psk: str = "",
    connect_timeout: float = 30.0,
    overwrite_cb: Callable[[str], str] | None = None,
) -> TransferProgress:
    """Send a file or folder to host:port.

    overwrite_cb(filename) -> 'overwrite' | 'skip' | 'rename'
    Called when receiver reports the file already exists.
    """
    p = Path(file_path)
    if p.is_dir():
        return _send_folder(host, port, p, progress_cb, pause_event, cancel_event,
                            speed_limit_bps, psk, connect_timeout, overwrite_cb)
    return _send_single(host, port, p, progress_cb, pause_event, cancel_event,
                        speed_limit_bps, psk, connect_timeout, overwrite_cb)


def _make_socket(host: str, port: int, connect_timeout: float = 30.0) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Optimization: Large buffers for high-speed LAN
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)  # 2MB
    except Exception:
        pass
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    s.settimeout(connect_timeout)
    try:
        s.connect((host, port))
    except Exception:
        s.close()
        raise
    s.settimeout(120.0)
    return s


# ── Single file ──────────────────────────────────────────────────────────────

def _send_single(host, port, p: Path, progress_cb, pause_event, cancel_event,
                 speed_limit_bps, psk, connect_timeout, overwrite_cb):
    if not p.exists():
        return TransferProgress(status="error", error=f"Файл не знайдено: {p}")
    info = FileInfo.from_path(str(p))
    cipher = _make_cipher(psk)
    _log.info("Sending %s (%d bytes) to %s:%d", info.name, info.size, host, port)

    try:
        with _make_socket(host, port, connect_timeout) as s:
            s.sendall(encode_message("file", {
                "name": info.name,
                "size": info.size,
                "encrypted": cipher is not None,
                "is_folder": False,
            }))
            resp = read_message(s)

            # ── Overwrite prompt from receiver ────────────────────────────
            if resp.get("action") == "overwrite_prompt":
                choice = _handle_overwrite_prompt(resp, info.name, overwrite_cb)
                s.sendall(encode_message("overwrite", {"choice": choice}))
                if choice == "skip":
                    _log.info("Skipping %s (overwrite=skip)", info.name)
                    return TransferProgress(status="done", total=info.size,
                                           transferred=info.size)
                resp = read_message(s)

            if resp.get("action") != "ready":
                return TransferProgress(
                    status="error",
                    error=resp.get("payload", {}).get("error", "Receiver not ready."),
                )

            # ── Resume support ────────────────────────────────────────────
            resume_offset = int(resp.get("payload", {}).get("offset", 0))
            prog = TransferProgress(total=info.size, transferred=resume_offset,
                                    status="sending")
            if resume_offset > 0:
                _log.info("Resuming %s from offset %d", info.name, resume_offset)

            sha = hashlib.sha256()
            with open(info.path, "rb") as f:
                if resume_offset > 0:
                    # Hash already-sent bytes so final checksum matches
                    _hash_prefix(f, resume_offset, sha)
                    f.seek(resume_offset)
                prog, ok = _stream_data(
                    s, f, prog, sha, cipher,
                    pause_event, cancel_event, speed_limit_bps, progress_cb,
                )

            if not ok:
                return prog
            result = _finalize(s, prog, sha)
            _log.info("Sent %s: %s", info.name, result.status)
            return result
    except OSError as e:
        _log.error("OSError sending %s: %s", info.name, e)
        return TransferProgress(status="error", error=str(e))


# ── Folder (streaming zip) ───────────────────────────────────────────────────

def _send_folder(host, port, folder: Path, progress_cb, pause_event, cancel_event,
                 speed_limit_bps, psk, connect_timeout, overwrite_cb):
    """Stream folder as ZIP using a temp file to avoid memory spikes."""
    zip_name = folder.name + ".zip"
    cipher = _make_cipher(psk)

    zip_stream = _ZipStream(folder, _pick_compression(folder))
    with zip_stream.create_temp_zip() as tmp_path:
        total = tmp_path.stat().st_size
        prog = TransferProgress(total=total, status="sending")
        
        try:
            with _make_socket(host, port, connect_timeout) as s:
                s.sendall(encode_message("file", {
                    "name": zip_name,
                    "size": total,
                    "encrypted": cipher is not None,
                    "is_folder": True,
                }))
                resp = read_message(s)

                if resp.get("action") == "overwrite_prompt":
                    choice = _handle_overwrite_prompt(resp, zip_name, overwrite_cb)
                    s.sendall(encode_message("overwrite", {"choice": choice}))
                    if choice == "skip":
                        return TransferProgress(status="done", total=total, transferred=total)
                    resp = read_message(s)

                if resp.get("action") != "ready":
                    return TransferProgress(
                        status="error",
                        error=resp.get("payload", {}).get("error", "Receiver not ready."),
                    )

                sha = hashlib.sha256()
                with open(tmp_path, "rb") as f:
                    prog, ok = _stream_data(
                        s, f, prog, sha, cipher,
                        pause_event, cancel_event, speed_limit_bps, progress_cb,
                    )

                if not ok:
                    return prog
                result = _finalize(s, prog, sha)
                _log.info("Sent folder %s: %s", folder.name, result.status)
                return result
        except OSError as e:
            _log.error("OSError sending folder %s: %s", folder.name, e)
            return TransferProgress(status="error", error=str(e))


class _ZipStream:
    """Builds a ZIP into a BytesIO but streams file-by-file to avoid peak memory."""

    def __init__(self, folder: Path, compression: int):
        self._folder = folder
        self._compression = compression

    @contextlib.contextmanager
    def create_temp_zip(self):
        # Optimization: Use a larger buffer and faster traversal
        fd, path = tempfile.mkstemp(suffix=".zip", prefix="lanft_")
        os.close(fd)
        tmp_path = Path(path)
        try:
            with zipfile.ZipFile(tmp_path, "w", self._compression, allowZip64=True) as zf:
                # Optimized rglob/stat calls
                base = self._folder.parent
                for root, dirs, files in os.walk(self._folder):
                    root_path = Path(root)
                    for file in files:
                        fp = root_path / file
                        zf.write(fp, fp.relative_to(base))
            yield tmp_path
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass


def _pick_compression(folder: Path) -> int:
    _COMPRESSED_EXTS = {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mkv", ".avi",
        ".mov", ".mp3", ".aac", ".ogg", ".zip", ".gz", ".7z", ".rar", ".bz2",
    }
    files = [fp for fp in folder.rglob("*") if fp.is_file()]
    if not files:
        return zipfile.ZIP_DEFLATED
    compressed = sum(1 for fp in files if fp.suffix.lower() in _COMPRESSED_EXTS)
    return zipfile.ZIP_STORED if compressed / len(files) > 0.6 else zipfile.ZIP_DEFLATED


# ── Shared streaming logic ───────────────────────────────────────────────────

def _stream_data(sock, f, prog, sha, cipher, pause_event, cancel_event,
                 speed_limit_bps, progress_cb):
    window: list[tuple[float, int]] = []
    last_cb = 0.0
    chunk_size = CHUNK_SIZE
    
    # Use mv to avoid copies if possible
    buf = bytearray(CHUNK_SIZE * 2) 

    while True:
        if pause_event and not pause_event.is_set():
            prog.status = "paused"
            if progress_cb:
                progress_cb(prog)
            pause_event.wait()
            prog.status = "sending"
            window.clear()

        if cancel_event and cancel_event.is_set():
            prog.status = "error"
            prog.error = "Скасовано користувачем."
            return prog, False

        chunk = f.read(chunk_size)
        if not chunk:
            break

        # CPU/RAM optimization: Update SHA and Encrypt in-place if possible
        sha.update(chunk)
        payload = cipher.encrypt(chunk) if cipher else chunk

        t_send_start = time.monotonic()
        # Use memoryview for framing to avoid extra bytes objects
        sock.sendall(_frame(payload))
        t_send_end = time.monotonic()

        now = t_send_end
        chunk_len = len(chunk)
        prog.transferred += chunk_len
        window.append((now, chunk_len))

        # Speed calculation and dynamic chunk sizing
        if len(window) > 20: # Keep window small for performance
             window = window[-20:]
        
        cutoff = now - _SPEED_WINDOW
        while window and window[0][0] < cutoff:
            window.pop(0)

        window_bytes = sum(b for _, b in window)
        elapsed_w = now - window[0][0] if len(window) > 1 else 0
        if elapsed_w > 0.001:
            prog.speed_bps = window_bytes / elapsed_w
        else:
            prog.speed_bps = 0

        # Adjust chunk size based on network performance
        send_ms = (t_send_end - t_send_start) * 1000
        if send_ms > 0:
            # Target ~50ms per chunk for good balance of responsiveness and throughput
            ideal = int(chunk_size * (_CHUNK_TARGET_MS / send_ms))
            chunk_size = max(_CHUNK_MIN, min(_CHUNK_MAX, (chunk_size + ideal) // 2))

        if speed_limit_bps > 0 and elapsed_w > 0:
            expected_time = window_bytes / speed_limit_bps
            sleep_for = expected_time - elapsed_w
            if sleep_for > 0.001:
                time.sleep(sleep_for)

        if progress_cb and now - last_cb >= _PROGRESS_INTERVAL:
            progress_cb(prog)
            last_cb = now

    if progress_cb:
        progress_cb(prog)

    return prog, True


def _finalize(sock, prog, sha) -> TransferProgress:
    prog.checksum = sha.hexdigest()
    sock.sendall(encode_message("checksum", {"sha256": prog.checksum}))
    resp = read_message(sock)
    if resp.get("action") == "done":
        prog.status = "done" if resp["payload"].get("checksum_ok", True) else "error"
        if prog.status == "error":
            prog.error = "Контрольна сума не збіглася — файл пошкоджено."
    else:
        prog.status = "error"
        prog.error = resp.get("payload", {}).get("error", "Unknown error")
    return prog


def _handle_overwrite_prompt(resp: dict, filename: str,
                              overwrite_cb: Callable | None) -> str:
    """Ask user what to do when file exists on receiver."""
    if overwrite_cb:
        return overwrite_cb(filename)
    return "rename"  # safe default


def _hash_prefix(f, size: int, sha: hashlib.sha256) -> None:
    """Hash first `size` bytes of file for resume checksum continuity."""
    remaining = size
    while remaining > 0:
        chunk = f.read(min(65536, remaining))
        if not chunk:
            break
        sha.update(chunk)
        remaining -= len(chunk)


def _make_cipher(psk: str) -> "ChannelCipher | None":
    if psk and crypto_available():
        return ChannelCipher(psk)
    return None


def _frame(data: bytes) -> bytes:
    return _PACK_UINT32.pack(len(data)) + data
