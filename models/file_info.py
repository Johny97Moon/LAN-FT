from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class FileInfo:
    name: str = ""
    path: str = ""
    size: int = 0

    @staticmethod
    def from_path(file_path: str) -> "FileInfo":
        p = Path(file_path)
        return FileInfo(name=p.name, path=str(p), size=p.stat().st_size)


@dataclass(slots=True)
class TransferProgress:
    total: int = 0
    transferred: int = 0
    status: str = "idle"  # idle | sending | receiving | paused | done | error
    error: str = ""
    checksum: str = ""       # SHA256 of the file (set when done)
    speed_bps: float = 0.0   # current bytes/sec

    @property
    def percent(self) -> float:
        if self.total == 0:
            return 0.0
        return min(100.0, self.transferred / self.total * 100)
