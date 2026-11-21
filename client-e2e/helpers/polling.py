"""Deadline polling and process tree cleanup utilities for E2E tests."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Any, TypeVar

import psutil

DEFAULT_POLL_TIMEOUT_SECONDS = 15.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.1
DEFAULT_TERMINATE_TIMEOUT_SECONDS = 5.0
KILL_WAIT_TIMEOUT_SECONDS = 10.0

T = TypeVar("T")


class FatalPollError(Exception):
    """Raised by a wait_until predicate to abort polling immediately."""


def wait_until(
    predicate: Callable[[], T | None],
    *,
    timeout: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    description: str = "condition",
) -> T:
    """Poll predicate() until it returns a truthy value or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
            last_exc = None
        except FatalPollError:
            raise
        except Exception as exc:  # pragma: no cover - transient poll errors
            last_exc = exc
        time.sleep(interval)

    detail = f" (last error: {last_exc})" if last_exc is not None else ""
    raise TimeoutError(f"Timed out after {timeout:.1f}s waiting for {description}{detail}")


def get_process_tree_pids(root_pid: int) -> set[int]:
    """Return root_pid plus all recursive child PIDs (handles PyInstaller onefile children)."""
    pids = {root_pid}
    try:
        proc = psutil.Process(root_pid)
        for child in proc.children(recursive=True):
            pids.add(child.pid)
    except psutil.NoSuchProcess:
        pass
    return pids


def _close_popen_pipes_and_wait(proc: subprocess.Popen[Any]) -> None:
    """Close standard pipes and reap a Popen handle without blocking indefinitely."""
    for pipe in (proc.stdin, proc.stdout, proc.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except (OSError, ValueError):
                pass
    try:
        proc.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass


def terminate_process_tree(
    target: subprocess.Popen[Any] | int,
    *,
    timeout: float = DEFAULT_TERMINATE_TIMEOUT_SECONDS,
) -> None:
    """Cleanly terminate a process and all of its children, force-killing stragglers."""
    pid = target.pid if isinstance(target, subprocess.Popen) else int(target)
    try:
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return

        processes: list[psutil.Process] = [parent]
        try:
            processes.extend(parent.children(recursive=True))
        except psutil.NoSuchProcess:
            pass

        for proc in reversed(processes):
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        _, alive = psutil.wait_procs(processes, timeout=timeout)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        psutil.wait_procs(alive, timeout=KILL_WAIT_TIMEOUT_SECONDS)
    finally:
        if isinstance(target, subprocess.Popen):
            _close_popen_pipes_and_wait(target)
