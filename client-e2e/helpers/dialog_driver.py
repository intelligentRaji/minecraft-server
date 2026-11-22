"""Cross-platform GUI dialog automation driver for ModSync onboarding E2E tests.

- Windows (`win32`): Uses stdlib `ctypes.windll.user32` (`EnumWindows`, `SendInput`,
  `PostMessageW`, `SendMessageW`) to locate and drive both Tk top-level dialogs
  (`simpledialog`) and native Win32 Common Dialogs (`messagebox`, `filedialog`).
- Linux (`linux`): Manages an isolated `Xvfb` display (when needed) and drives X11
  Tk dialogs via `xdotool`.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from .polling import FatalPollError, get_process_tree_pids, terminate_process_tree, wait_until

ENV_CI = "CI"
CI_TRUTHY_VALUES = frozenset({"1", "true", "yes"})
ENV_DISPLAY = "DISPLAY"

XVFB_DISPLAY_MIN = 95
XVFB_DISPLAY_MAX = 125
XVFB_SCREEN_GEOMETRY = "1280x800x24"
WIN32_DIALOG_CLASS = "#32770"

POLL_INTERVAL_FAST = 0.05
POLL_INTERVAL_DEFAULT = 0.1
DISPLAY_STARTUP_DELAY = 0.25
KEY_EVENT_DELAY = 0.01
DIALOG_FOCUS_DELAY = 0.1
DIALOG_CLOSE_DELAY = 0.15
XDOTOOL_TYPING_DELAY_MS = "15"
CLEAR_INPUT_BACKSPACE_COUNT = 30
TIMEOUT_PROC_WAIT = 20.0
TIMEOUT_DIALOG = 30.0


def is_ci_environment() -> bool:
    return os.environ.get(ENV_CI, "").strip().lower() in CI_TRUTHY_VALUES


@dataclass
class DialogWindow:
    """Represents a discovered OS dialog window handle/ID and metadata."""

    handle: int
    title: str
    class_name: str = ""


class BaseDialogDriver:
    """Platform-agnostic dialog driver interface for ModSync onboarding tests."""

    def prepare_env(self, env: dict[str, str]) -> dict[str, str]:
        return env

    def wait_for_dialog(
        self,
        root_pid: int,
        title_substring: str,
        *,
        exclude_handles: set[int] | None = None,
        class_name: str | None = None,
        timeout: float = TIMEOUT_DIALOG,
    ) -> DialogWindow:
        raise NotImplementedError

    def enter_text_and_accept(self, window: DialogWindow, text: str) -> None:
        raise NotImplementedError

    def accept_dialog(self, window: DialogWindow) -> None:
        raise NotImplementedError

    def cancel_or_close_dialog(self, window: DialogWindow) -> None:
        raise NotImplementedError

    def list_visible_windows(self, root_pid: int) -> list[DialogWindow]:
        raise NotImplementedError

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Linux Xvfb + xdotool implementation
# ---------------------------------------------------------------------------


@dataclass
class X11DialogDriver(BaseDialogDriver):
    """Drives Tkinter X11 dialogs under Xvfb using xdotool."""

    display: str = ""
    xvfb_process: subprocess.Popen[str] | None = field(default=None, init=False)
    wm_process: subprocess.Popen[str] | None = field(default=None, init=False)

    def _wait_x_server_ready(
        self,
        display_name: str,
        xvfb_proc: subprocess.Popen[str],
        *,
        timeout: float = 5.0,
    ) -> None:
        from Xlib import display as xdisplay

        def _connected() -> bool:
            if xvfb_proc.poll() is not None:
                raise FatalPollError(f"Xvfb exited early with code {xvfb_proc.returncode}")
            try:
                dpy = xdisplay.Display(display_name)
            except Exception:
                return False
            dpy.close()
            return True

        wait_until(
            _connected,
            timeout=timeout,
            interval=POLL_INTERVAL_FAST,
            description=f"X11 display {display_name} to accept connections",
        )

    def _start_window_manager_if_available(self) -> None:
        wm_path = shutil.which("openbox")
        if not wm_path:
            return
        env = self.prepare_env(os.environ.copy())
        proc = subprocess.Popen(
            [wm_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        from Xlib import X, display as xdisplay

        def _wm_ready() -> bool:
            if proc.poll() is not None:
                raise FatalPollError(f"openbox exited early with code {proc.returncode}")
            dpy = xdisplay.Display(self.display)
            try:
                atom = dpy.intern_atom("_NET_SUPPORTING_WM_CHECK")
                prop = dpy.screen().root.get_full_property(atom, X.AnyPropertyType)
                return prop is not None and bool(prop.value)
            finally:
                dpy.close()

        try:
            wait_until(
                _wm_ready,
                timeout=5.0,
                interval=POLL_INTERVAL_FAST,
                description=f"openbox WM ready on {self.display}",
            )
            self.wm_process = proc
        except BaseException:
            terminate_process_tree(proc, timeout=3.0)
            raise

    def start_if_needed(self) -> None:
        xdotool_path = shutil.which("xdotool")
        if not xdotool_path:
            raise RuntimeError("xdotool is not installed on PATH")

        existing_display = os.environ.get(ENV_DISPLAY, "").strip()
        if existing_display:
            self.display = existing_display
            return

        xvfb_path = shutil.which("Xvfb")
        if not xvfb_path:
            raise RuntimeError("Neither DISPLAY nor Xvfb is available on Linux")

        for display_num in range(XVFB_DISPLAY_MIN, XVFB_DISPLAY_MAX):
            candidate = f":{display_num}"
            lock_file = f"/tmp/.X{display_num}-lock"
            if os.path.exists(lock_file):
                continue
            proc = subprocess.Popen(
                [
                    xvfb_path,
                    candidate,
                    "-screen",
                    "0",
                    XVFB_SCREEN_GEOMETRY,
                    "-ac",
                    "-nolisten",
                    "tcp",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                self._wait_x_server_ready(candidate, proc)
                self.display = candidate
                self.xvfb_process = proc
                break
            except (FatalPollError, TimeoutError):
                terminate_process_tree(proc, timeout=3.0)
            except BaseException:
                terminate_process_tree(proc, timeout=3.0)
                raise
        else:
            raise RuntimeError(
                f"Failed to start Xvfb on any display between :{XVFB_DISPLAY_MIN} and :{XVFB_DISPLAY_MAX - 1}"
            )

        try:
            self._start_window_manager_if_available()
        except BaseException:
            self.close()
            raise

    def prepare_env(self, env: dict[str, str]) -> dict[str, str]:
        updated = dict(env)
        if self.display:
            updated[ENV_DISPLAY] = self.display
        return updated

    def _run_xdotool(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = self.prepare_env(os.environ.copy())
        return subprocess.run(
            ["xdotool", *args],
            env=env,
            capture_output=True,
            text=True,
            check=check,
            timeout=TIMEOUT_PROC_WAIT,
        )

    def list_visible_windows(self, root_pid: int) -> list[DialogWindow]:
        pids = get_process_tree_pids(root_pid)
        res = self._run_xdotool("search", "--onlyvisible", "--name", ".", check=False)
        if res.returncode != 0 or not res.stdout.strip():
            return []

        windows: list[DialogWindow] = []
        for raw_line in res.stdout.strip().splitlines():
            line = raw_line.strip()
            if not line.isdigit():
                continue
            wid = int(line)
            title_res = self._run_xdotool("getwindowname", str(wid), check=False)
            title = title_res.stdout.strip() if title_res.returncode == 0 else ""
            if not title:
                continue
            pid_res = self._run_xdotool("getwindowpid", str(wid), check=False)
            if pid_res.returncode == 0 and pid_res.stdout.strip().isdigit():
                win_pid = int(pid_res.stdout.strip())
                if win_pid not in pids:
                    continue
            windows.append(DialogWindow(handle=wid, title=title))
        return windows

    def wait_for_dialog(
        self,
        root_pid: int,
        title_substring: str,
        *,
        exclude_handles: set[int] | None = None,
        class_name: str | None = None,
        timeout: float = TIMEOUT_DIALOG,
    ) -> DialogWindow:
        excluded = exclude_handles or set()
        needle = title_substring.lower()

        def _find() -> DialogWindow | None:
            for win in self.list_visible_windows(root_pid):
                if win.handle in excluded:
                    continue
                if needle in win.title.lower():
                    return win
            return None

        return wait_until(
            _find,
            timeout=timeout,
            interval=POLL_INTERVAL_DEFAULT,
            description=f"X11 dialog matching {title_substring!r}",
        )

    def _wait_closed(self, root_pid: int, handle: int, timeout: float = TIMEOUT_PROC_WAIT) -> None:
        wait_until(
            lambda: all(w.handle != handle for w in self.list_visible_windows(root_pid)),
            timeout=timeout,
            interval=POLL_INTERVAL_FAST,
            description=f"dialog {handle} to close",
        )

    def _focus_window(self, wid: str) -> None:
        self._run_xdotool("windowactivate", "--sync", wid, check=False)
        self._run_xdotool("windowfocus", "--sync", wid, check=False)
        time.sleep(DIALOG_FOCUS_DELAY)

    def enter_text_and_accept(self, window: DialogWindow, text: str) -> None:
        wid = str(window.handle)
        self._focus_window(wid)
        # Clear any pre-filled initialvalue ("modsync://") in Tk simpledialog Entry via XTEST.
        self._run_xdotool("key", "--clearmodifiers", "End", check=False)
        self._run_xdotool(
            "key",
            "--clearmodifiers",
            *(["BackSpace"] * CLEAR_INPUT_BACKSPACE_COUNT),
            check=False,
        )
        if text:
            self._run_xdotool(
                "type",
                "--clearmodifiers",
                "--delay",
                XDOTOOL_TYPING_DELAY_MS,
                "--",
                text,
            )
        time.sleep(POLL_INTERVAL_FAST)
        self._run_xdotool("key", "--clearmodifiers", "Return")

    def accept_dialog(self, window: DialogWindow) -> None:
        wid = str(window.handle)
        self._focus_window(wid)
        self._run_xdotool("key", "--clearmodifiers", "Return")

    def cancel_or_close_dialog(self, window: DialogWindow) -> None:
        wid = str(window.handle)
        self._focus_window(wid)
        self._run_xdotool("key", "--clearmodifiers", "Escape", check=False)
        time.sleep(DIALOG_CLOSE_DELAY)
        self._run_xdotool("windowclose", wid, check=False)

    def close(self) -> None:
        if self.wm_process is not None:
            terminate_process_tree(self.wm_process, timeout=3.0)
            self.wm_process = None
        if self.xvfb_process is not None:
            terminate_process_tree(self.xvfb_process, timeout=3.0)
            self.xvfb_process = None


# ---------------------------------------------------------------------------
# Windows Win32 ctypes implementation
# ---------------------------------------------------------------------------

WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
BM_CLICK = 0x00F5
IDOK = 1
IDCANCEL = 2
VK_BACK = 0x08
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_END = 0x23
VK_CONTROL = 0x11
VK_A = 0x41
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
GW_OWNER = 4
SW_RESTORE = 9
SMTO_ABORTIFHUNG = 0x0002
SENDMESSAGE_TIMEOUT_MS = 2000


class Win32DialogDriver(BaseDialogDriver):
    """Drives Tk and native Win32 dialogs on Windows via ctypes.windll.user32."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Win32DialogDriver is only supported on Windows")
        from ctypes import wintypes

        self.user32: Any = ctypes.windll.user32
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.IsWindow.argtypes = [wintypes.HWND]
        self.user32.IsWindow.restype = wintypes.BOOL
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetClassNameW.restype = ctypes.c_int
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
        self.user32.GetWindow.restype = wintypes.HWND
        self.user32.PostMessageW.argtypes = [
            wintypes.HWND,
            ctypes.c_uint,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.PostMessageW.restype = wintypes.BOOL
        self.user32.SendMessageW.argtypes = [
            wintypes.HWND,
            ctypes.c_uint,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.SendMessageW.restype = wintypes.LPARAM
        self.user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            ctypes.c_uint,
            wintypes.WPARAM,
            wintypes.LPARAM,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(wintypes.WPARAM),
        ]
        self.user32.SendMessageTimeoutW.restype = wintypes.LPARAM
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.SetForegroundWindow.restype = wintypes.BOOL
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetDlgItem.restype = wintypes.HWND

    def _window_title(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def _window_class(self, hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def _window_pid(self, hwnd: int) -> int:
        if sys.platform != "win32":
            raise RuntimeError("Win32DialogDriver is only supported on Windows")
        from ctypes import wintypes

        pid = wintypes.DWORD(0)
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def list_visible_windows(self, root_pid: int) -> list[DialogWindow]:
        if sys.platform != "win32":
            raise RuntimeError("Win32DialogDriver is only supported on Windows")
        from ctypes import wintypes

        pids = get_process_tree_pids(root_pid)
        found: list[DialogWindow] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        def _callback(hwnd: int, _lparam: int) -> bool:
            if not self.user32.IsWindowVisible(hwnd):
                return True
            win_pid = self._window_pid(hwnd)
            owner = self.user32.GetWindow(hwnd, GW_OWNER)
            owner_pid = self._window_pid(owner) if owner else 0
            if win_pid not in pids and owner_pid not in pids:
                return True
            title = self._window_title(hwnd).strip()
            if not title:
                return True
            found.append(
                DialogWindow(
                    handle=int(hwnd),
                    title=title,
                    class_name=self._window_class(hwnd),
                )
            )
            return True

        self.user32.EnumWindows(WNDENUMPROC(_callback), 0)
        return found

    def wait_for_dialog(
        self,
        root_pid: int,
        title_substring: str,
        *,
        exclude_handles: set[int] | None = None,
        class_name: str | None = None,
        timeout: float = TIMEOUT_DIALOG,
    ) -> DialogWindow:
        excluded = exclude_handles or set()
        needle = title_substring.lower()

        def _find() -> DialogWindow | None:
            for win in self.list_visible_windows(root_pid):
                if win.handle in excluded:
                    continue
                if class_name and win.class_name != class_name:
                    continue
                if needle in win.title.lower():
                    return win
            return None

        return wait_until(
            _find,
            timeout=timeout,
            interval=POLL_INTERVAL_DEFAULT,
            description=f"Win32 dialog matching {title_substring!r} (class={class_name})",
        )

    def _focus_window(self, hwnd: int) -> None:
        self.user32.ShowWindow(hwnd, SW_RESTORE)
        self.user32.SetForegroundWindow(hwnd)
        time.sleep(DIALOG_FOCUS_DELAY)

    def _send_vk(self, vk: int, *, key_up: bool = False) -> None:
        flags = KEYEVENTF_KEYUP if key_up else 0
        self.user32.keybd_event(vk, 0, flags, 0)

    def _tap_vk(self, vk: int) -> None:
        self._send_vk(vk, key_up=False)
        time.sleep(KEY_EVENT_DELAY)
        self._send_vk(vk, key_up=True)
        time.sleep(KEY_EVENT_DELAY)

    def _type_unicode_text(self, text: str) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Win32DialogDriver is only supported on Windows")
        from ctypes import wintypes

        ULONG_PTR = wintypes.WPARAM

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD),
            ]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [
                ("ki", KEYBDINPUT),
                ("mi", MOUSEINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", wintypes.DWORD),
                ("union", INPUT_UNION),
            ]

        for ch in text:
            code = ord(ch)
            down = INPUT(
                type=INPUT_KEYBOARD,
                union=INPUT_UNION(
                    ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
                ),
            )
            up = INPUT(
                type=INPUT_KEYBOARD,
                union=INPUT_UNION(
                    ki=KEYBDINPUT(
                        wVk=0,
                        wScan=code,
                        dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            )
            arr = (INPUT * 2)(down, up)
            self.user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))
            time.sleep(0.01)

    def enter_text_and_accept(self, window: DialogWindow, text: str) -> None:
        self._focus_window(window.handle)
        # Clear pre-filled "modsync://" in Tk Entry
        self._send_vk(VK_CONTROL, key_up=False)
        try:
            self._tap_vk(VK_A)
        finally:
            self._send_vk(VK_CONTROL, key_up=True)
        self._tap_vk(VK_BACK)
        self._tap_vk(VK_END)
        for _ in range(CLEAR_INPUT_BACKSPACE_COUNT):
            self._tap_vk(VK_BACK)
        if text:
            self._type_unicode_text(text)
        time.sleep(POLL_INTERVAL_FAST)
        self._tap_vk(VK_RETURN)

    def accept_dialog(self, window: DialogWindow) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Win32DialogDriver is only supported on Windows")
        from ctypes import wintypes

        hwnd = window.handle
        if window.class_name == WIN32_DIALOG_CLASS:
            ok_btn = self.user32.GetDlgItem(hwnd, IDOK)
            if ok_btn:
                result = wintypes.WPARAM(0)
                self.user32.SendMessageTimeoutW(
                    ok_btn,
                    BM_CLICK,
                    0,
                    0,
                    SMTO_ABORTIFHUNG,
                    SENDMESSAGE_TIMEOUT_MS,
                    ctypes.byref(result),
                )
                time.sleep(DIALOG_FOCUS_DELAY)
                if not self.user32.IsWindowVisible(hwnd):
                    return
            self.user32.PostMessageW(hwnd, WM_COMMAND, IDOK, 0)
            time.sleep(DIALOG_CLOSE_DELAY)
            if not self.user32.IsWindowVisible(hwnd):
                return
        self._focus_window(hwnd)
        self._tap_vk(VK_RETURN)

    def cancel_or_close_dialog(self, window: DialogWindow) -> None:
        hwnd = window.handle
        self.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(DIALOG_CLOSE_DELAY)
        if self.user32.IsWindowVisible(hwnd) and window.class_name == WIN32_DIALOG_CLASS:
            self.user32.PostMessageW(hwnd, WM_COMMAND, IDCANCEL, 0)


def create_dialog_driver() -> BaseDialogDriver:
    """Create and initialize the platform-appropriate GUI dialog driver."""
    if sys.platform == "win32":
        return Win32DialogDriver()
    driver = X11DialogDriver()
    driver.start_if_needed()
    return driver
