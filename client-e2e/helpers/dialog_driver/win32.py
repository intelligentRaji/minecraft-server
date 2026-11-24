"""Windows Win32 ctypes dialog automation and screenshot driver."""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path
from typing import Any

from ..png import write_rgb_png
from ..polling import get_process_tree_pids, wait_until
from .base import (
    DIALOG_CLOSE_DELAY,
    KEY_EVENT_DELAY,
    POLL_INTERVAL_FAST,
    TIMEOUT_PROC_WAIT,
    WIN32_DIALOG_CLASS,
    BaseDialogDriver,
    DialogWindow,
)

WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
BM_CLICK = 0x00F5
IDOK = 1
IDCANCEL = 2

VK_BACK = 0x08
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_ESCAPE = 0x1B
VK_END = 0x23
VK_HOME = 0x24
VK_A = 0x41

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

GW_OWNER = 4
SW_RESTORE = 9
SMTO_ABORTIFHUNG = 0x0002
SENDMESSAGE_TIMEOUT_MS = 2000

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0

EXTENDED_VKS = frozenset({VK_HOME, VK_END})

USER32: Any = None
GDI32: Any = None
KERNEL32: Any = None

if sys.platform == "win32":
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

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            ("bmiColors", wintypes.DWORD * 3),
        ]

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    WNDENUMCHILDPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    USER32 = ctypes.WinDLL("user32", use_last_error=True)
    USER32.IsWindowVisible.argtypes = [wintypes.HWND]
    USER32.IsWindowVisible.restype = wintypes.BOOL
    USER32.IsWindow.argtypes = [wintypes.HWND]
    USER32.IsWindow.restype = wintypes.BOOL
    USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    USER32.GetWindowTextLengthW.restype = ctypes.c_int
    USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    USER32.GetWindowTextW.restype = ctypes.c_int
    USER32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    USER32.GetClassNameW.restype = ctypes.c_int
    USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    USER32.GetWindowThreadProcessId.restype = wintypes.DWORD
    USER32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
    USER32.GetWindow.restype = wintypes.HWND
    USER32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    USER32.EnumWindows.restype = wintypes.BOOL
    USER32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMCHILDPROC, wintypes.LPARAM]
    USER32.EnumChildWindows.restype = wintypes.BOOL
    USER32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    USER32.FindWindowExW.restype = wintypes.HWND
    USER32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    USER32.PostMessageW.restype = wintypes.BOOL
    USER32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    USER32.SendMessageW.restype = wintypes.LPARAM
    USER32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        ctypes.c_uint,
        wintypes.WPARAM,
        wintypes.LPARAM,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(wintypes.WPARAM),
    ]
    USER32.SendMessageTimeoutW.restype = wintypes.LPARAM
    USER32.SetForegroundWindow.argtypes = [wintypes.HWND]
    USER32.SetForegroundWindow.restype = wintypes.BOOL
    USER32.GetForegroundWindow.argtypes = []
    USER32.GetForegroundWindow.restype = wintypes.HWND
    USER32.SetFocus.argtypes = [wintypes.HWND]
    USER32.SetFocus.restype = wintypes.HWND
    USER32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    USER32.AttachThreadInput.restype = wintypes.BOOL
    USER32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    USER32.ShowWindow.restype = wintypes.BOOL
    USER32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
    USER32.GetDlgItem.restype = wintypes.HWND
    USER32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
    USER32.SendInput.restype = ctypes.c_uint
    USER32.GetSystemMetrics.argtypes = [ctypes.c_int]
    USER32.GetSystemMetrics.restype = ctypes.c_int
    USER32.GetDC.argtypes = [wintypes.HWND]
    USER32.GetDC.restype = wintypes.HDC
    USER32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    USER32.ReleaseDC.restype = ctypes.c_int

    GDI32 = ctypes.WinDLL("gdi32", use_last_error=True)
    GDI32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    GDI32.CreateCompatibleDC.restype = wintypes.HDC
    GDI32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    GDI32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    GDI32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    GDI32.SelectObject.restype = wintypes.HGDIOBJ
    GDI32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    GDI32.BitBlt.restype = wintypes.BOOL
    GDI32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(BITMAPINFO),
        ctypes.c_uint,
    ]
    GDI32.GetDIBits.restype = ctypes.c_int
    GDI32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    GDI32.DeleteObject.restype = wintypes.BOOL
    GDI32.DeleteDC.argtypes = [wintypes.HDC]
    GDI32.DeleteDC.restype = wintypes.BOOL

    KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    KERNEL32.GetCurrentThreadId.argtypes = []
    KERNEL32.GetCurrentThreadId.restype = wintypes.DWORD


class Win32DialogDriver(BaseDialogDriver):
    """Drives Tk and native Win32 dialogs on Windows via isolated User32/GDI32 DLL handles."""

    has_system_tray: bool = True

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Win32DialogDriver is only supported on Windows")

    def _window_title(self, hwnd: int) -> str:
        length = USER32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        USER32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def _window_class(self, hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        USER32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def _window_pid(self, hwnd: int) -> int:
        from ctypes import wintypes

        pid = wintypes.DWORD(0)
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def list_visible_windows(self, root_pid: int) -> list[DialogWindow]:
        pids = get_process_tree_pids(root_pid)
        found: list[DialogWindow] = []

        def _callback(hwnd: int, _lparam: int) -> bool:
            if not USER32.IsWindowVisible(hwnd):
                return True
            win_pid = self._window_pid(hwnd)
            owner = USER32.GetWindow(hwnd, GW_OWNER)
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

        USER32.EnumWindows(WNDENUMPROC(_callback), 0)
        return found

    def _focus_window(self, hwnd: int) -> None:
        USER32.ShowWindow(hwnd, SW_RESTORE)
        USER32.SetForegroundWindow(hwnd)

        def _is_foreground() -> bool:
            if int(USER32.GetForegroundWindow() or 0) == hwnd:
                return True
            USER32.SetForegroundWindow(hwnd)
            return False

        wait_until(
            _is_foreground,
            timeout=5.0,
            interval=POLL_INTERVAL_FAST,
            description=f"Win32 window {hwnd} to become foreground window",
        )

    def _send_vk(self, vk: int, *, key_up: bool = False) -> None:
        flags = KEYEVENTF_KEYUP if key_up else 0
        if vk in EXTENDED_VKS:
            flags |= KEYEVENTF_EXTENDEDKEY
        inp = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(
                ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
            ),
        )
        USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _tap_vk(self, vk: int) -> None:
        self._send_vk(vk, key_up=False)
        time.sleep(KEY_EVENT_DELAY)
        self._send_vk(vk, key_up=True)
        time.sleep(KEY_EVENT_DELAY)

    def _send_ctrl_a(self) -> None:
        self._send_vk(VK_CONTROL, key_up=False)
        try:
            self._tap_vk(VK_A)
        finally:
            self._send_vk(VK_CONTROL, key_up=True)

    def _send_shift_end(self) -> None:
        self._send_vk(VK_SHIFT, key_up=False)
        try:
            self._tap_vk(VK_END)
        finally:
            self._send_vk(VK_SHIFT, key_up=True)

    def _type_unicode_text(self, text: str) -> None:
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
            USER32.SendInput(len(arr), arr, ctypes.sizeof(INPUT))
            time.sleep(KEY_EVENT_DELAY)

    def _clear_focused_input(self) -> None:
        self._send_ctrl_a()
        self._tap_vk(VK_BACK)
        self._tap_vk(VK_HOME)
        self._send_shift_end()
        self._tap_vk(VK_BACK)

    def enter_text_and_accept(self, window: DialogWindow, text: str) -> None:
        self._focus_window(window.handle)
        self._clear_focused_input()
        if text:
            self._type_unicode_text(text)
        time.sleep(POLL_INTERVAL_FAST)
        self._tap_vk(VK_RETURN)

    def _click_dialog_ok(self, hwnd: int) -> bool:
        from ctypes import wintypes

        ok_btn = USER32.GetDlgItem(hwnd, IDOK)
        if ok_btn:
            result = wintypes.WPARAM(0)
            USER32.SendMessageTimeoutW(
                ok_btn,
                BM_CLICK,
                0,
                0,
                SMTO_ABORTIFHUNG,
                SENDMESSAGE_TIMEOUT_MS,
                ctypes.byref(result),
            )
            time.sleep(POLL_INTERVAL_FAST)
            if not USER32.IsWindowVisible(hwnd):
                return True
        USER32.PostMessageW(hwnd, WM_COMMAND, IDOK, 0)
        time.sleep(DIALOG_CLOSE_DELAY)
        return not USER32.IsWindowVisible(hwnd)

    def accept_dialog(self, window: DialogWindow) -> None:
        hwnd = window.handle
        if window.class_name == WIN32_DIALOG_CLASS and self._click_dialog_ok(hwnd):
            return
        self._focus_window(hwnd)
        self._tap_vk(VK_RETURN)

    def cancel_or_close_dialog(self, window: DialogWindow) -> None:
        hwnd = window.handle
        USER32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(DIALOG_CLOSE_DELAY)
        if USER32.IsWindowVisible(hwnd) and window.class_name == WIN32_DIALOG_CLASS:
            USER32.PostMessageW(hwnd, WM_COMMAND, IDCANCEL, 0)

    def _find_edit_under_container(self, container_hwnd: int) -> int | None:
        combo = USER32.FindWindowExW(container_hwnd, 0, "ComboBox", None)
        if combo:
            edit = USER32.FindWindowExW(combo, 0, "Edit", None)
            if edit:
                return int(edit)
        edit = USER32.FindWindowExW(container_hwnd, 0, "Edit", None)
        if edit:
            return int(edit)
        return None

    def _find_folder_edit_hwnd(self, dialog_hwnd: int) -> int:
        def _probe() -> int | None:
            float_sinks: list[int] = []
            combobox_ex_handles: list[int] = []
            combobox_handles: list[int] = []

            def _collect(child_hwnd: int, _lparam: int) -> bool:
                cls = self._window_class(child_hwnd)
                if cls == "FloatNotifySink":
                    float_sinks.append(int(child_hwnd))
                elif cls == "ComboBoxEx32":
                    combobox_ex_handles.append(int(child_hwnd))
                elif cls == "ComboBox":
                    combobox_handles.append(int(child_hwnd))
                return True

            USER32.EnumChildWindows(dialog_hwnd, WNDENUMCHILDPROC(_collect), 0)
            for sink in float_sinks:
                edit = self._find_edit_under_container(sink)
                if edit:
                    return edit
            for cbex in combobox_ex_handles:
                edit = self._find_edit_under_container(cbex)
                if edit:
                    return edit
            for combo in combobox_handles:
                edit = USER32.FindWindowExW(combo, 0, "Edit", None)
                if edit:
                    return int(edit)
            return None

        return wait_until(
            _probe,
            timeout=5.0,
            interval=POLL_INTERVAL_FAST,
            description=f"Folder Edit control inside Win32 dialog {dialog_hwnd}",
        )

    def _dismiss_owned_error_popups(self, dialog_hwnd: int) -> None:
        owned_popups: list[int] = []

        def _collect_owned(hwnd: int, _lparam: int) -> bool:
            if (
                USER32.IsWindowVisible(hwnd)
                and int(USER32.GetWindow(hwnd, GW_OWNER) or 0) == dialog_hwnd
                and self._window_class(hwnd) == WIN32_DIALOG_CLASS
            ):
                owned_popups.append(int(hwnd))
            return True

        USER32.EnumWindows(WNDENUMPROC(_collect_owned), 0)
        for popup in owned_popups:
            self._click_dialog_ok(popup)

    def _focus_child_control(self, dialog_hwnd: int, child_hwnd: int) -> None:
        self._focus_window(dialog_hwnd)
        curr_tid = int(KERNEL32.GetCurrentThreadId())
        dlg_tid = int(USER32.GetWindowThreadProcessId(dialog_hwnd, None))
        attached = False
        if dlg_tid and dlg_tid != curr_tid:
            attached = bool(USER32.AttachThreadInput(curr_tid, dlg_tid, True))
        try:
            USER32.SetFocus(child_hwnd)
        finally:
            if attached:
                USER32.AttachThreadInput(curr_tid, dlg_tid, False)
        time.sleep(POLL_INTERVAL_FAST)

    def select_folder(self, window: DialogWindow, folder_path: Path) -> None:
        hwnd = window.handle
        self._dismiss_owned_error_popups(hwnd)
        edit_hwnd = self._find_folder_edit_hwnd(hwnd)
        self._focus_child_control(hwnd, edit_hwnd)
        self._clear_focused_input()
        self._type_unicode_text(str(folder_path))
        time.sleep(POLL_INTERVAL_FAST)
        if not self._click_dialog_ok(hwnd):
            self._focus_window(hwnd)
            self._tap_vk(VK_RETURN)
        wait_until(
            lambda: not USER32.IsWindowVisible(hwnd),
            timeout=TIMEOUT_PROC_WAIT,
            interval=POLL_INTERVAL_FAST,
            description=f"Win32 folder dialog {hwnd} to dismiss",
        )

    def capture_screenshot(self, output_path: Path) -> Path | None:
        left = int(USER32.GetSystemMetrics(SM_XVIRTUALSCREEN))
        top = int(USER32.GetSystemMetrics(SM_YVIRTUALSCREEN))
        width = int(USER32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
        height = int(USER32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
        if width <= 0 or height <= 0:
            left, top = 0, 0
            width = int(USER32.GetSystemMetrics(SM_CXSCREEN))
            height = int(USER32.GetSystemMetrics(SM_CYSCREEN))
        if width <= 0 or height <= 0:
            return None

        screen_dc = USER32.GetDC(None)
        if not screen_dc:
            return None
        mem_dc = None
        hbmp = None
        old_obj = None
        try:
            mem_dc = GDI32.CreateCompatibleDC(screen_dc)
            if not mem_dc:
                return None
            hbmp = GDI32.CreateCompatibleBitmap(screen_dc, width, height)
            if not hbmp:
                return None
            old_obj = GDI32.SelectObject(mem_dc, hbmp)
            if not GDI32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, SRCCOPY):
                return None

            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB

            buf = ctypes.create_string_buffer(width * height * 4)
            rows = GDI32.GetDIBits(mem_dc, hbmp, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
            if rows == 0:
                return None
            return write_rgb_png(output_path, width, height, buf.raw, bgrx=True)
        finally:
            if mem_dc and old_obj:
                GDI32.SelectObject(mem_dc, old_obj)
            if hbmp:
                GDI32.DeleteObject(hbmp)
            if mem_dc:
                GDI32.DeleteDC(mem_dc)
            USER32.ReleaseDC(None, screen_dc)

    def close(self) -> None:
        return None
