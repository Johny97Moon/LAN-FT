"""Orchestrates send/receive/discovery operations."""
import threading
from typing import Callable

from transfer.queue import QueueManager, QueueJob
from models.file_info import TransferProgress
from net.receiver import start_receiver
from net.discovery import start_discovery_responder, broadcast_discover


class TransferManager:
    def __init__(self):
        self._receiver_thread: threading.Thread | None = None
        self._discovery_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._discovery_stop = threading.Event()

        # Queue-based sender
        self.queue = QueueManager()

    # ── Queue sender ─────────────────────────────────────────────────────────

    def enqueue(
        self,
        host: str,
        port: int,
        paths: list[str],
        speed_limit_bps: int = 0,
        psk: str = "",
        connect_timeout: float = 30.0,
        overwrite_cb=None,
    ) -> list[str]:
        return self.queue.enqueue(host, port, paths, speed_limit_bps, psk,
                                  connect_timeout, overwrite_cb)

    def cancel_job(self, job_id: str) -> None:
        self.queue.cancel_job(job_id)

    def pause_job(self, job_id: str) -> None:
        self.queue.pause_job(job_id)

    def resume_job(self, job_id: str) -> None:
        self.queue.resume_job(job_id)

    def get_jobs(self) -> list[QueueJob]:
        return self.queue.get_jobs()

    def clear_done_jobs(self) -> None:
        self.queue.clear_done()

    # ── Receiver ─────────────────────────────────────────────────────────────

    def start_hosting(
        self,
        port: int,
        save_dir: str,
        progress_cb: Callable[[TransferProgress], None] | None = None,
        status_cb: Callable[[str], None] | None = None,
        psk: str = "",
    ) -> None:
        self.stop_hosting()
        self._stop_event.clear()
        self._discovery_stop.clear()

        self._receiver_thread = threading.Thread(
            target=start_receiver,
            args=(port, save_dir, progress_cb, status_cb, self._stop_event, psk),
            daemon=True,
        )
        self._receiver_thread.start()

        self._discovery_thread = threading.Thread(
            target=start_discovery_responder,
            args=(port, self._discovery_stop),
            daemon=True,
        )
        self._discovery_thread.start()

    def stop_hosting(self) -> None:
        self._stop_event.set()
        self._discovery_stop.set()
        if self._receiver_thread and self._receiver_thread.is_alive():
            self._receiver_thread.join(timeout=3)
        self._receiver_thread = None
        self._discovery_thread = None

    # ── Discovery ────────────────────────────────────────────────────────────

    def discover_hosts(
        self,
        tcp_port: int,
        timeout: float = 2.0,
        done_cb: Callable[[list[dict]], None] | None = None,
    ) -> None:
        """Run discovery in background thread, call done_cb with results."""
        def _run():
            results = broadcast_discover(tcp_port, timeout)
            if done_cb:
                done_cb(results)

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> None:
        self.stop_hosting()
        self.queue.stop()
