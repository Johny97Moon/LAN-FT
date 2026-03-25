import hashlib
import logging
import socket
import struct
import time
import zipfile
from pathlib import Path
from typing import Callable

from config.settings import CHUNK_SIZE, load_settings
from models.file_info import TransferProgress
from net.protocol import encode_message, read_message, _recv_exact
from net.crypto import ChannelCipher

_log = logging.getLogger("lan_ft.receiver")
_PROGRESS_INTERVAL = 0.1
_SPEED_WINDOW = 1.0
_MAX_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB DoS guard


def start_receiver(
    port: int,
    save_dir: str,
    progress_cb: Callable[[TransferProgress], None] | None = None,
    status_cb: Callable[[str], None] | None = None,
    stop_event=None,
    psk: str = "",
) -> None:
    _log.info("Receiver starting on port %d, save_dir=%s", port, save_dir)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        server.bind(("", port))
        server.listen(5)
        server.settimeout(1.0)

        if status_cb:
            status_cb("listening")

        while not (stop_event and stop_event.is_set()):
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue

            _log.info("Connection from %s", addr[0])
            if status_cb:
                status_cb(f"connected:{addr[0]}")
            _handle_connection(conn, addr, save_dir, progress_cb, status_cb, psk)
            if status_cb:
                status_cb("listening")

    _log.info("Receiver stopped.")


def _handle_connection(conn, addr, save_dir, progress_cb, status_cb, psk: str):
    settings = load_settings()
    max_file_mb = settings.get("max_file_size_mb", 0)
    overwrite_policy = settings.get("overwrite_existing", "ask")

    with conn:
        try:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)  # 2MB
        except Exception:
            pass
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        conn.settimeout(120)
        try:
            msg = read_message(conn)
            if msg.get("action") != "file":
                return

            payload = msg["payload"]
            # ── Security: Robust name sanitization ────────────────────────
            raw_name = payload.get("name", "unnamed")
            # Allow Ukrainian/Unicode characters and common filename symbols while stripping illegal characters for Windows
            # Illegal characters: < > : " / \ | ? *
            forbidden = {'<', '>', ':', '"', '/', '\\', '|', '?', '*'}
            file_name_raw = "".join(c for c in Path(raw_name).name if c not in forbidden and ord(c) > 31)
            file_name = file_name_raw.strip(". ") # No leading/trailing dots or spaces
            
            if not file_name:
                file_name = f"received_{int(time.time())}"
            
            file_size = int(payload.get("size", 0))
            _MAX_FILE_SIZE = 100 * 1024 * 1024 * 1024  # 100 GB hard limit

            if file_size < 0 or file_size > _MAX_FILE_SIZE:
                conn.sendall(encode_message("error", {"error": "Invalid file size."}))
                return

            # ── File size limit check ─────────────────────────────────────
            if max_file_mb > 0 and file_size > max_file_mb * 1024 * 1024:
                msg_err = f"File too large: {file_size // (1024*1024)} MB (limit: {max_file_mb} MB)"
                _log.warning("Rejected %s: %s", file_name, msg_err)
                conn.sendall(encode_message("error", {"error": msg_err}))
                if status_cb:
                    status_cb(f"error:{msg_err}")
                return

            encrypted = payload.get("encrypted", False)
            is_folder = payload.get("is_folder", False)

            cipher: ChannelCipher | None = None
            if encrypted:
                if not psk:
                    conn.sendall(encode_message("error", {"error": "PSK не задано."}))
                    return
                cipher = ChannelCipher(psk)

            save_path = Path(save_dir) / file_name
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # ── Resume support ────────────────────────────────────────────
            resume_offset = 0
            if save_path.exists() and save_path.stat().st_size < file_size:
                resume_offset = save_path.stat().st_size
                _log.info("Resuming %s from offset %d", file_name, resume_offset)

            # ── Overwrite handling ────────────────────────────────────────
            if save_path.exists() and resume_offset == 0:
                action = _resolve_overwrite(
                    conn, file_name, overwrite_policy, status_cb
                )
                if action == "skip":
                    _log.info("Skipping existing file: %s", save_path)
                    return
                if action == "rename":
                    save_path = _unique_path(save_path)
                    _log.info("Renamed to: %s", save_path)
                # "overwrite" — continue normally

            prog = TransferProgress(
                total=file_size,
                transferred=resume_offset,
                status="receiving",
            )
            # ── Handshake ─────────────────────────────────────────────────
            conn.sendall(encode_message("ready", {"offset": resume_offset}))
            
            sha = hashlib.sha256()
            window: list[tuple[float, int]] = []
            last_cb = 0.0

            # Hash already-received bytes for resume
            if resume_offset > 0 and save_path.exists():
                with open(save_path, "rb") as existing:
                    _hash_existing(existing, resume_offset, sha)

            try:
                open_mode = "ab" if resume_offset > 0 else "wb"
                # Optimization: 2MB buffer for disk writes
                out_file = open(save_path, open_mode, buffering=2 * 1024 * 1024)
            except OSError as e:
                conn.sendall(encode_message("error", {"error": str(e)}))
                return

            _log.info("Receiving %s (%d bytes, offset=%d)", file_name, file_size, resume_offset)

            with out_file as f:
                while prog.transferred < file_size:
                    chunk_data = _recv_framed(conn)
                    raw = cipher.decrypt(chunk_data) if cipher else chunk_data
                    sha.update(raw)
                    f.write(raw)

                    now = time.monotonic()
                    chunk_len = len(raw)
                    prog.transferred += chunk_len

                    if prog.transferred > file_size:
                        raise ValueError(
                            f"Received more data than expected: {prog.transferred} > {file_size}"
                        )

                    window.append((now, chunk_len))
                    if len(window) > 20:
                        window = window[-20:]

                    cutoff = now - _SPEED_WINDOW
                    while window and window[0][0] < cutoff:
                        window.pop(0)

                    elapsed_w = now - window[0][0] if len(window) > 1 else 0
                    window_bytes = sum(b for _, b in window)
                    prog.speed_bps = window_bytes / elapsed_w if elapsed_w > 0 else 0

                    if progress_cb and now - last_cb >= _PROGRESS_INTERVAL:
                        progress_cb(prog)
                        last_cb = now

            if progress_cb:
                progress_cb(prog)

            # ── Checksum ──────────────────────────────────────────────────
            chk_msg = read_message(conn)
            local_hash = sha.hexdigest().lower()
            remote_hash = chk_msg.get("payload", {}).get("sha256", "").lower()
            checksum_ok = local_hash == remote_hash

            prog.checksum = local_hash
            prog.status = "done" if checksum_ok else "error"
            if not checksum_ok:
                prog.error = "Контрольна сума не збіглася."
                _log.error("Checksum mismatch for %s", file_name)
            else:
                _log.info("Received %s OK (sha256=%s…)", file_name, local_hash[:12])

            conn.sendall(encode_message("done", {
                "saved_as": str(save_path),
                "checksum_ok": checksum_ok,
            }))

            if progress_cb:
                progress_cb(prog)

            # ── Unzip folder ──────────────────────────────────────────────
            if is_folder and checksum_ok and save_path.suffix == ".zip":
                extract_to = Path(save_dir)
                with zipfile.ZipFile(save_path, "r") as zf:
                    resolved_base = extract_to.resolve()
                    for member in zf.infolist():
                        member_path = (extract_to / member.filename).resolve()
                        if not str(member_path).startswith(str(resolved_base)):
                            raise ValueError(f"Zip path traversal: {member.filename}")
                    zf.extractall(extract_to)
                save_path.unlink()
                if status_cb:
                    status_cb(f"done:{extract_to / save_path.stem}")
            elif checksum_ok:
                if status_cb:
                    status_cb(f"done:{save_path}")
            else:
                if status_cb:
                    status_cb(f"error:checksum_mismatch:{save_path}")

        except Exception as e:
            _log.exception("Error handling connection from %s", addr[0])
            try:
                conn.sendall(encode_message("error", {"error": str(e)}))
            except Exception:
                pass
            if status_cb:
                status_cb(f"error:{e}")


def _resolve_overwrite(conn, file_name: str, policy: str, status_cb) -> str:
    """
    Determine what to do when file exists.
    Returns: 'overwrite' | 'skip' | 'rename'
    """
    if policy == "overwrite":
        return "overwrite"
    if policy == "skip":
        conn.sendall(encode_message("overwrite_prompt", {
            "file": file_name,
            "action": "skip",
        }))
        return "skip"

    # policy == "ask": send prompt to sender, wait for response
    conn.sendall(encode_message("overwrite_prompt", {
        "file": file_name,
        "action": "ask",
    }))
    try:
        resp = read_message(conn)
        if resp.get("action") == "overwrite":
            return resp["payload"].get("choice", "rename")
    except Exception:
        pass
    return "rename"


def _unique_path(path: Path) -> Path:
    """Return a non-existing path by appending (1), (2), etc."""
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    i = 1
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _hash_existing(f, size: int, sha: hashlib.sha256) -> None:
    """Hash the first `size` bytes of an existing file for resume."""
    remaining = size
    buf_size = 65536
    while remaining > 0:
        chunk = f.read(min(buf_size, remaining))
        if not chunk:
            break
        sha.update(chunk)
        remaining -= len(chunk)


def _recv_framed(sock) -> bytes:
    raw_len = _recv_exact(sock, 4)
    length = struct.unpack(">I", raw_len)[0]
    if length > _MAX_CHUNK_SIZE:
        raise ValueError(f"Frame too large: {length} bytes")
    return _recv_exact(sock, length)
