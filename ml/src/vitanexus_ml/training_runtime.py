from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def atomic_replace(source: Path, target: Path, attempts: int = 40, delay_seconds: float = 0.25) -> None:
    """Replace with bounded retries for antivirus/OneDrive transient Windows locks."""
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(delay_seconds)
    raise RuntimeError(
        f"Could not atomically promote {source} to {target} after {attempts} attempts. "
        "A sync/antivirus process may be locking the destination. The completed checkpoint remains safe."
    ) from last_error


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    atomic_replace(temporary, path)


def atomic_joblib(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    joblib.dump(value, temporary)
    atomic_replace(temporary, path)


def atomic_torch(path: Path, value) -> None:
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    torch.save(value, temporary)
    atomic_replace(temporary, path)


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "unknown"
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


class ProgressReporter:
    def __init__(self, label: str, total: int | None = None):
        self.label = label
        self.total = total
        self.started = time.perf_counter()
        self.last = self.started
        self.completed = 0
        print(f"[{self.label}] started", flush=True)

    def update(self, completed: int, detail: str = "") -> None:
        self.completed = completed
        now = time.perf_counter()
        elapsed = now - self.started
        rate = completed / elapsed if elapsed > 0 and completed else 0.0
        eta = (self.total - completed) / rate if self.total and rate > 0 else None
        total_text = f"/{self.total}" if self.total is not None else ""
        suffix = f" | {detail}" if detail else ""
        print(
            f"[{self.label}] {completed}{total_text} | elapsed {format_duration(elapsed)}"
            f" | ETA {format_duration(eta)}{suffix}",
            flush=True,
        )
        self.last = now

    def finish(self, detail: str = "") -> float:
        elapsed = time.perf_counter() - self.started
        suffix = f" | {detail}" if detail else ""
        print(f"[{self.label}] complete | elapsed {format_duration(elapsed)}{suffix}", flush=True)
        return elapsed


def process_rss_bytes() -> int:
    try:
        import psutil

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except (ImportError, OSError):
        pass
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
        return 0
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == "darwin" else value * 1024)
    except (ImportError, OSError):
        return 0


class PeakMemoryMonitor(AbstractContextManager):
    def __init__(self, interval_seconds: float = 0.25):
        self.interval_seconds = interval_seconds
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self.peak_bytes = process_rss_bytes()

        def sample() -> None:
            while not self._stop.wait(self.interval_seconds):
                self.peak_bytes = max(self.peak_bytes, process_rss_bytes())

        self._thread = threading.Thread(target=sample, name="peak-memory-monitor", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.peak_bytes = max(self.peak_bytes, process_rss_bytes())
        return False


@dataclass
class StageStore:
    path: Path
    identity: dict

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if state.get("identity") != self.identity:
                raise RuntimeError(
                    f"Training checkpoint identity mismatch at {self.path}. "
                    "Use the matching immutable cohort/configuration; checkpoints are never silently reused."
                )
            self.state = state
        else:
            self.state = {"identity": self.identity, "createdAt": utc_now(), "stages": {}}
            self._save()

    def start(self, name: str, **details) -> None:
        self.state["stages"][name] = {"status": "running", "startedAt": utc_now(), **details}
        self.state["updatedAt"] = utc_now()
        self._save()

    def complete(self, name: str, **details) -> None:
        self.state["stages"][name] = {"status": "complete", "completedAt": utc_now(), **details}
        self.state["updatedAt"] = utc_now()
        self._save()

    def is_complete(self, name: str) -> bool:
        return self.state.get("stages", {}).get(name, {}).get("status") == "complete"

    def details(self, name: str) -> dict:
        return self.state.get("stages", {}).get(name, {})

    def _save(self) -> None:
        atomic_json(self.path, self.state)
