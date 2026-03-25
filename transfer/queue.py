"""
Transfer queue — supports parallel transfers via ThreadPoolExecutor.
Each job has its own cancel/pause events so individual items can be controlled.
"""
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from config.settings import load_settings
from models.file_info import TransferProgress
from net.sender import send_file

_log = logging.getLogger("lan_ft.queue")


def _set_event() -> threading.Event:
    e = threading.Event()
    e.set()
    return e


@dataclass
class QueueJob:
    job_id: str
    host: str
    port: int
    path: str
    speed_limit_bps: int = 0
    psk: str = ""
    connect_timeout: float = 30.0
    status: str = "pending"      # pending | sending | done | error | cancelled
    progress: TransferProgress = field(default_factory=TransferProgress)
    overwrite_cb: Callable[[str], str] | None = field(default=None, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _pause: threading.Event = field(default_factory=_set_event, repr=False)

    def cancel(self) -> None:
        self._cancel.set()
        self._pause.set()

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()

    @property
    def is_paused(self) -> bool:
        return not self._pause.is_set()


class QueueManager:
    def __init__(self):
        self._jobs: dict[str, QueueJob] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._new_job = threading.Event()
        self._running = False
        self._dispatcher: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._active_count = 0
        self._active_lock = threading.Lock()
        self.on_job_update: Callable[[QueueJob], None] | None = None

    # ── Public API ───────────────────────────────────────────────────────────

    def enqueue(
        self,
        host: str,
        port: int,
        paths: list[str],
        speed_limit_bps: int = 0,
        psk: str = "",
        connect_timeout: float = 30.0,
        overwrite_cb: Callable[[str], str] | None = None,
    ) -> list[str]:
        ids = []
        with self._lock:
            for p in paths:
                jid = str(uuid.uuid4())[:8]
                job = QueueJob(
                    job_id=jid,
                    host=host,
                    port=port,
                    path=p,
                    speed_limit_bps=speed_limit_bps,
                    psk=psk,
                    connect_timeout=connect_timeout,
                    overwrite_cb=overwrite_cb,
                )
                self._jobs[jid] = job
                self._order.append(jid)
                ids.append(jid)
                _log.debug("Enqueued job %s: %s", jid, p)
        self._new_job.set()
        self._ensure_dispatcher()
        self._auto_clear_if_needed()
        return ids

    def _auto_clear_if_needed(self) -> None:
        """Limit the number of jobs kept in memory to prevent leaks."""
        LIMIT = 1000
        with self._lock:
            if len(self._order) > LIMIT:
                # Keep current active jobs, clear oldest 'done'/'error'/'cancelled'
                active = {"pending", "sending"}
                new_order = []
                to_remove = len(self._order) - LIMIT
                removed_count = 0
                
                for jid in self._order:
                    if removed_count < to_remove and self._jobs[jid].status not in active:
                        del self._jobs[jid]
                        removed_count += 1
                    else:
                        new_order.append(jid)
                self._order = new_order

    def cancel_job(self, job_id: str) -> None:
        job = self._find(job_id)
        if job:
            job.cancel()

    def pause_job(self, job_id: str) -> None:
        job = self._find(job_id)
        if job:
            job.pause()

    def resume_job(self, job_id: str) -> None:
        job = self._find(job_id)
        if job:
            job.resume()

    def get_jobs(self) -> list[QueueJob]:
        with self._lock:
            return [self._jobs[jid] for jid in self._order]

    def clear_done(self) -> None:
        with self._lock:
            active = {"pending", "sending"}
            self._order = [jid for jid in self._order if self._jobs[jid].status in active]
            self._jobs = {jid: self._jobs[jid] for jid in self._order}

    def stop(self) -> None:
        self._running = False
        self._new_job.set()
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    # ── Dispatcher ───────────────────────────────────────────────────────────

    def _ensure_dispatcher(self) -> None:
        if self._dispatcher and self._dispatcher.is_alive():
            return
        self._running = True
        max_parallel = load_settings().get("max_parallel_transfers", 3)
        self._executor = ThreadPoolExecutor(
            max_workers=max_parallel, thread_name_prefix="lan_ft_transfer"
        )
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()
        _log.info("Queue dispatcher started (max_parallel=%d)", max_parallel)

    def _dispatch_loop(self) -> None:
        """Continuously dispatch pending jobs up to the parallel limit."""
        max_parallel = load_settings().get("max_parallel_transfers", 3)
        while self._running:
            with self._active_lock:
                slots = max_parallel - self._active_count

            if slots > 0:
                jobs = self._take_pending(slots)
                for job in jobs:
                    with self._active_lock:
                        self._active_count += 1
                    with self._lock:
                        job.status = "sending"
                    self._notify(job)
                    self._executor.submit(self._run_job, job)

            self._new_job.clear()
            self._new_job.wait(timeout=0.5)

        _log.info("Queue dispatcher stopped.")

    def _run_job(self, job: QueueJob) -> None:
        _log.info("Starting job %s: %s → %s:%d", job.job_id, job.path, job.host, job.port)

        def _progress(prog: TransferProgress, j: QueueJob = job) -> None:
            j.progress = prog
            self._notify(j)

        try:
            result = send_file(
                host=job.host,
                port=job.port,
                file_path=job.path,
                progress_cb=_progress,
                pause_event=job._pause,
                cancel_event=job._cancel,
                speed_limit_bps=job.speed_limit_bps,
                psk=job.psk,
                connect_timeout=job.connect_timeout,
                overwrite_cb=job.overwrite_cb,
            )
        except Exception as e:
            _log.exception("Job %s failed", job.job_id)
            with self._lock:
                job.status = "error"
            job.progress.error = str(e)
            self._notify(job)
            self._job_done()
            return

        if job._cancel.is_set():
            with self._lock:
                job.status = "cancelled"
            _log.info("Job %s cancelled.", job.job_id)
        elif result.status == "done":
            with self._lock:
                job.status = "done"
            _log.info("Job %s done.", job.job_id)
        else:
            with self._lock:
                job.status = "error"
            job.progress = result
            _log.warning("Job %s error: %s", job.job_id, result.error)

        self._notify(job)
        self._job_done()

    def _job_done(self) -> None:
        with self._active_lock:
            self._active_count = max(0, self._active_count - 1)
        self._new_job.set()  # wake dispatcher to pick next pending

    def _take_pending(self, n: int) -> list[QueueJob]:
        result = []
        with self._lock:
            for jid in self._order:
                if len(result) >= n:
                    break
                j = self._jobs[jid]
                if j.status == "pending":
                    result.append(j)
        return result

    def _find(self, job_id: str) -> QueueJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _notify(self, job: QueueJob) -> None:
        if self.on_job_update:
            self.on_job_update(job)
