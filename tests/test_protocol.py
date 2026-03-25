import pytest
import socket
import threading
import time
import io
import os
from pathlib import Path
from net.sender import send_file
from net.receiver import start_receiver

def test_transfer_integrity(tmp_path):
    """Test file transfer with checksum verification."""
    # 1. Setup
    save_dir = tmp_path / "received"
    save_dir.mkdir()
    
    src_file = tmp_path / "test.txt"
    content = b"Hello, LAN-FT integrity test! " * 1000
    src_file.write_bytes(content)
    
    stop_event = threading.Event()
    port = 5999
    
    # 2. Start receiver
    recv_thread = threading.Thread(
        target=start_receiver,
        args=(port, str(save_dir)),
        kwargs={"stop_event": stop_event, "psk": ""},
        daemon=True
    )
    recv_thread.start()
    time.sleep(0.5) # Wait for bind
    
    # 3. Send file
    def progress_cb(p): pass
    def overwrite_cb(f): return "overwrite"
    pause = threading.Event()
    pause.set() # Start in 'running' state
    cancel = threading.Event()
    
    send_file("127.0.0.1", port, str(src_file), progress_cb, pause, cancel, 0, None, 5, overwrite_cb)
    
    # 4. Verify
    dest_file = save_dir / "test.txt"
    assert dest_file.exists()
    assert dest_file.read_bytes() == content
    
    # 5. Cleanup
    stop_event.set()
    # Trigger receiver to exit loop (it's blocking on accept)
    try:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", port))
    except: pass
    recv_thread.join(timeout=1.0)
