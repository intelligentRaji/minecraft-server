"""Windows Job Object subprocess tracker for multi-phase installers and relaunched children."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ERROR_MORE_DATA = 234
INFINITE = 0xFFFFFFFF
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
STILL_ACTIVE = 259

CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100
HANDLE_FLAG_INHERIT = 0x00000001

JOB_OBJECT_BASIC_PROCESS_ID_LIST_CLASS = 3
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

PROCESS_SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

POLL_INTERVAL_SECONDS = 0.05

KERNEL32: Any = None

if sys.platform == "win32":
    from ctypes import wintypes

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    def _make_job_pid_list_struct(capacity: int) -> type[ctypes.Structure]:
        class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
            _fields_ = [
                ("NumberOfAssignedProcesses", wintypes.DWORD),
                ("NumberOfProcessIdsInList", wintypes.DWORD),
                ("ProcessIdList", ctypes.c_size_t * capacity),
            ]

        return JOBOBJECT_BASIC_PROCESS_ID_LIST

    JOBOBJECT_BASIC_PROCESS_ID_LIST = _make_job_pid_list_struct(64)

    KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    KERNEL32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    KERNEL32.CreateJobObjectW.restype = wintypes.HANDLE
    KERNEL32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    KERNEL32.SetInformationJobObject.restype = wintypes.BOOL
    KERNEL32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    KERNEL32.QueryInformationJobObject.restype = wintypes.BOOL
    KERNEL32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    KERNEL32.AssignProcessToJobObject.restype = wintypes.BOOL
    KERNEL32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    KERNEL32.TerminateJobObject.restype = wintypes.BOOL
    KERNEL32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    KERNEL32.CreateProcessW.restype = wintypes.BOOL
    KERNEL32.ResumeThread.argtypes = [wintypes.HANDLE]
    KERNEL32.ResumeThread.restype = wintypes.DWORD
    KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    KERNEL32.OpenProcess.restype = wintypes.HANDLE
    KERNEL32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    KERNEL32.WaitForSingleObject.restype = wintypes.DWORD
    KERNEL32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    KERNEL32.GetExitCodeProcess.restype = wintypes.BOOL
    KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    KERNEL32.CloseHandle.restype = wintypes.BOOL
    KERNEL32.GetStdHandle.argtypes = [wintypes.DWORD]
    KERNEL32.GetStdHandle.restype = wintypes.HANDLE
    KERNEL32.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
    KERNEL32.SetHandleInformation.restype = wintypes.BOOL


def _raise_last_winerror(action: str) -> None:
    err = ctypes.get_last_error()
    raise OSError(err, f"{action} failed (winerror={err})")


class WinJobProcessTracker:
    """Tracks a spawned Windows process and all descendants via a Win32 Job Object."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WinJobProcessTracker is only supported on Windows")

        job = KERNEL32.CreateJobObjectW(None, None)
        if not job:
            _raise_last_winerror("CreateJobObjectW")
        self._job: int = int(job)
        self._handles: dict[int, int] = {}
        self._exit_codes: dict[int, int] = {}
        self._closed = False

        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not KERNEL32.SetInformationJobObject(
            self._job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            self.close()
            _raise_last_winerror("SetInformationJobObject")

    def __enter__(self) -> WinJobProcessTracker:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @property
    def pids(self) -> set[int]:
        return set(self._handles) | set(self._exit_codes)

    @property
    def exit_codes(self) -> dict[int, int]:
        return dict(self._exit_codes)

    def spawn(
        self,
        args: Sequence[str | Path],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        stdout: Path | None = None,
        stderr: Path | None = None,
    ) -> int:
        """Spawn a suspended process, assign it to the Job Object, resume it, and return PID."""
        import msvcrt

        cmdline = subprocess.list2cmdline([str(a) for a in args])
        cmd_buf = ctypes.create_unicode_buffer(cmdline)

        env_buf = None
        creation_flags = CREATE_SUSPENDED
        if env is not None:
            sorted_items = sorted(env.items(), key=lambda kv: kv[0].upper())
            env_text = "".join(f"{k}={v}\0" for k, v in sorted_items) + "\0"
            env_buf = ctypes.create_unicode_buffer(env_text)
            creation_flags |= CREATE_UNICODE_ENVIRONMENT

        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        pi = PROCESS_INFORMATION()

        opened_files: list[Any] = []
        inherit_handles = False
        try:
            if stdout is not None or stderr is not None:
                inherit_handles = True
                si.dwFlags |= STARTF_USESTDHANDLES
                null_in = open(os.devnull, "rb")
                opened_files.append(null_in)
                in_h = msvcrt.get_osfhandle(null_in.fileno())
                KERNEL32.SetHandleInformation(in_h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
                si.hStdInput = in_h

                if stdout is not None:
                    stdout.parent.mkdir(parents=True, exist_ok=True)
                    out_f = stdout.open("ab")
                else:
                    out_f = open(os.devnull, "wb")
                opened_files.append(out_f)
                out_h = msvcrt.get_osfhandle(out_f.fileno())
                KERNEL32.SetHandleInformation(out_h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
                si.hStdOutput = out_h

                if stderr is not None:
                    if stderr == stdout:
                        err_h = out_h
                    else:
                        stderr.parent.mkdir(parents=True, exist_ok=True)
                        err_f = stderr.open("ab")
                        opened_files.append(err_f)
                        err_h = msvcrt.get_osfhandle(err_f.fileno())
                        KERNEL32.SetHandleInformation(err_h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
                else:
                    err_f = open(os.devnull, "wb")
                    opened_files.append(err_f)
                    err_h = msvcrt.get_osfhandle(err_f.fileno())
                    KERNEL32.SetHandleInformation(err_h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
                si.hStdError = err_h

            ok = KERNEL32.CreateProcessW(
                None,
                cmd_buf,
                None,
                None,
                inherit_handles,
                creation_flags,
                env_buf,
                str(cwd) if cwd is not None else None,
                ctypes.byref(si),
                ctypes.byref(pi),
            )
            if not ok:
                _raise_last_winerror(f"CreateProcessW({args[0]})")
        finally:
            for f in opened_files:
                try:
                    f.close()
                except OSError:
                    pass

        pid = int(pi.dwProcessId)
        try:
            if not KERNEL32.AssignProcessToJobObject(self._job, pi.hProcess):
                _raise_last_winerror("AssignProcessToJobObject")
            self._handles[pid] = int(pi.hProcess)
            if KERNEL32.ResumeThread(pi.hThread) == 0xFFFFFFFF:
                _raise_last_winerror("ResumeThread")
        except BaseException:
            if pid not in self._handles:
                KERNEL32.CloseHandle(pi.hProcess)
            raise
        finally:
            KERNEL32.CloseHandle(pi.hThread)

        return pid

    def _query_job_pids(self) -> list[int]:
        capacity = 64
        while True:
            struct_cls = (
                JOBOBJECT_BASIC_PROCESS_ID_LIST
                if capacity == 64
                else _make_job_pid_list_struct(capacity)
            )
            buf = struct_cls()
            if KERNEL32.QueryInformationJobObject(
                self._job,
                JOB_OBJECT_BASIC_PROCESS_ID_LIST_CLASS,
                ctypes.byref(buf),
                ctypes.sizeof(buf),
                None,
            ):
                count = int(buf.NumberOfProcessIdsInList)
                return [int(buf.ProcessIdList[i]) for i in range(count)]
            err = ctypes.get_last_error()
            if err == ERROR_MORE_DATA:
                capacity = max(capacity * 2, int(buf.NumberOfAssignedProcesses) + 16)
                continue
            return []

    def refresh_tracked_pids(self) -> None:
        """Open handles to any newly spawned processes inside the Job Object."""
        for pid in self._query_job_pids():
            if pid in self._handles or pid in self._exit_codes:
                continue
            handle = KERNEL32.OpenProcess(
                PROCESS_SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid,
            )
            if handle:
                self._handles[pid] = int(handle)

    def _harvest_exited(self) -> None:
        from ctypes import wintypes

        finished: list[int] = []
        for pid, handle in list(self._handles.items()):
            wait_rc = KERNEL32.WaitForSingleObject(handle, 0)
            if wait_rc == WAIT_OBJECT_0:
                code = wintypes.DWORD(0)
                if KERNEL32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    self._exit_codes[pid] = int(code.value)
                else:
                    self._exit_codes[pid] = 0
                finished.append(pid)

        for pid in finished:
            handle = self._handles.pop(pid)
            KERNEL32.CloseHandle(handle)

    def is_pid_alive(self, pid: int) -> bool:
        self.refresh_tracked_pids()
        self._harvest_exited()
        return pid in self._handles

    def wait_for_pid(self, pid: int, *, timeout: float) -> int:
        """Wait for a specific tracked PID to exit while keeping job descendants tracked."""
        deadline = time.monotonic() + timeout
        while True:
            self.refresh_tracked_pids()
            self._harvest_exited()
            if pid in self._exit_codes:
                return self._exit_codes[pid]
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out after {timeout:.1f}s waiting for PID {pid}")
            time.sleep(POLL_INTERVAL_SECONDS)

    def wait_all(self, *, timeout: float) -> dict[int, int]:
        """Wait for all processes in the job to exit and return {pid: exit_code}."""
        deadline = time.monotonic() + timeout
        while True:
            self.refresh_tracked_pids()
            self._harvest_exited()
            if not self._handles:
                # Re-check once more in case a child spawned right as the last handle exited.
                self.refresh_tracked_pids()
                if not self._handles:
                    return dict(self._exit_codes)
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out after {timeout:.1f}s waiting for Job Object processes "
                    f"(remaining pids={sorted(self._handles)})"
                )
            time.sleep(POLL_INTERVAL_SECONDS)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._job:
                KERNEL32.TerminateJobObject(self._job, 1)
        finally:
            for handle in self._handles.values():
                KERNEL32.CloseHandle(handle)
            self._handles.clear()
            if self._job:
                KERNEL32.CloseHandle(self._job)
                self._job = 0
