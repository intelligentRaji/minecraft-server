"""Linux X11/Xvfb dialog and system-tray automation driver."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ..png import write_rgb_png
from ..polling import FatalPollError, get_process_tree_pids, terminate_process_tree, wait_until
from .base import (
    DIALOG_CLOSE_DELAY,
    POLL_INTERVAL_FAST,
    TIMEOUT_PROC_WAIT,
    BaseDialogDriver,
    DialogWindow,
)

ENV_DISPLAY = "DISPLAY"
XVFB_DISPLAY_MIN = 95
XVFB_DISPLAY_MAX = 125
XVFB_SCREEN_GEOMETRY = "1280x800x24"
XDOTOOL_TYPING_DELAY_MS = "15"
SYSTEM_TRAY_SELECTION_ATOM = "_NET_SYSTEM_TRAY_S0"
WM_CHECK_ATOM = "_NET_SUPPORTING_WM_CHECK"
TINT2_CONFIG_TEMPLATE = (
    "panel_position = bottom center horizontal\n"
    "panel_size = 100% 32\n"
    "panel_items = S\n"
    "systray_padding = 4 2 4\n"
    "systray_icon_size = 24\n"
)


class X11DialogDriver(BaseDialogDriver):
    """Drives Tkinter X11 dialogs and optional tint2 tray under an isolated Xvfb display."""

    def __init__(self) -> None:
        self.display: str = ""
        self.has_system_tray: bool = False
        self._xvfb_process: subprocess.Popen[str] | None = None
        self._wm_process: subprocess.Popen[str] | None = None
        self._tray_process: subprocess.Popen[str] | None = None
        self._log_dir: Path | None = None
        self._owns_log_dir: bool = False

    def __enter__(self) -> X11DialogDriver:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @classmethod
    def start(
        cls,
        *,
        use_live_display: bool = False,
        log_dir: Path | None = None,
    ) -> X11DialogDriver:
        """Start an isolated Xvfb + openbox + tint2 session (or attach to live DISPLAY)."""
        if not shutil.which("xdotool"):
            raise RuntimeError("xdotool is not installed on PATH")

        driver = cls()
        if log_dir is None:
            driver._log_dir = Path(tempfile.mkdtemp(prefix="modsync-x11-"))
            driver._owns_log_dir = True
        else:
            log_dir.mkdir(parents=True, exist_ok=True)
            driver._log_dir = log_dir

        try:
            existing_display = os.environ.get(ENV_DISPLAY, "").strip()
            if use_live_display and existing_display:
                driver.display = existing_display
                driver.has_system_tray = driver._is_tray_owned()
                return driver

            driver._start_xvfb()
            driver._start_window_manager_if_available()
            driver._start_tray_if_available()
            return driver
        except BaseException:
            driver.close()
            raise

    def _open_display(self) -> Any:
        from Xlib import display as xdisplay

        return xdisplay.Display(self.display)

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

    def _start_xvfb(self) -> None:
        xvfb_path = shutil.which("Xvfb")
        if not xvfb_path:
            raise RuntimeError("Xvfb is not installed on PATH")
        assert self._log_dir is not None
        xvfb_log = self._log_dir / "xvfb.log"

        for display_num in range(XVFB_DISPLAY_MIN, XVFB_DISPLAY_MAX):
            candidate = f":{display_num}"
            lock_file = f"/tmp/.X{display_num}-lock"
            if os.path.exists(lock_file):
                continue
            with xvfb_log.open("w", encoding="utf-8") as log_file:
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
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            try:
                self._wait_x_server_ready(candidate, proc)
                self.display = candidate
                self._xvfb_process = proc
                return
            except (FatalPollError, TimeoutError):
                terminate_process_tree(proc, timeout=3.0)
            except BaseException:
                terminate_process_tree(proc, timeout=3.0)
                raise

        raise RuntimeError(
            f"Failed to start Xvfb on any display between :{XVFB_DISPLAY_MIN} and :{XVFB_DISPLAY_MAX - 1}"
        )

    def _start_window_manager_if_available(self) -> None:
        wm_path = shutil.which("openbox")
        if not wm_path:
            return
        assert self._log_dir is not None
        env = self.prepare_env(os.environ.copy())
        with (self._log_dir / "openbox.log").open("w", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                [wm_path],
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )

        from Xlib import X

        def _wm_ready() -> bool:
            if proc.poll() is not None:
                raise FatalPollError(f"openbox exited early with code {proc.returncode}")
            dpy = self._open_display()
            try:
                atom = dpy.intern_atom(WM_CHECK_ATOM)
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
            self._wm_process = proc
        except BaseException:
            terminate_process_tree(proc, timeout=3.0)
            raise

    def _is_tray_owned(self) -> bool:
        from Xlib import X

        dpy = self._open_display()
        try:
            tray_atom = dpy.intern_atom(SYSTEM_TRAY_SELECTION_ATOM)
            owner = dpy.get_selection_owner(tray_atom)
            return bool(owner) and getattr(owner, "id", owner) != X.NONE
        except Exception:
            return False
        finally:
            dpy.close()

    def _start_tray_if_available(self) -> None:
        tint2_path = shutil.which("tint2")
        if not tint2_path:
            self.has_system_tray = False
            return
        assert self._log_dir is not None
        tint2rc_path = self._log_dir / "tint2rc"
        tint2rc_path.write_text(TINT2_CONFIG_TEMPLATE, encoding="utf-8")
        env = self.prepare_env(os.environ.copy())
        with (self._log_dir / "tint2.log").open("w", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                [tint2_path, "-c", str(tint2rc_path)],
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )

        def _tray_ready() -> bool:
            if proc.poll() is not None:
                raise FatalPollError(f"tint2 exited early with code {proc.returncode}")
            return self._is_tray_owned()

        try:
            wait_until(
                _tray_ready,
                timeout=5.0,
                interval=POLL_INTERVAL_FAST,
                description=f"tint2 {SYSTEM_TRAY_SELECTION_ATOM} ownership on {self.display}",
            )
            self._tray_process = proc
            self.has_system_tray = True
        except BaseException:
            terminate_process_tree(proc, timeout=3.0)
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

    def _get_wm_class(self, dpy: Any, wid: int) -> str:
        from Xlib.error import XError

        try:
            win = dpy.create_resource_object("window", wid)
            wm_class = win.get_wm_class()
            if wm_class:
                return str(wm_class[1] or wm_class[0] or "")
        except XError:
            return ""
        return ""

    def list_visible_windows(self, root_pid: int) -> list[DialogWindow]:
        pids = get_process_tree_pids(root_pid)
        res = self._run_xdotool("search", "--onlyvisible", "--name", ".", check=False)
        if res.returncode != 0 or not res.stdout.strip():
            return []

        windows: list[DialogWindow] = []
        dpy = self._open_display()
        try:
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
                windows.append(
                    DialogWindow(
                        handle=wid,
                        title=title,
                        class_name=self._get_wm_class(dpy, wid),
                    )
                )
        finally:
            dpy.close()
        return windows

    def _is_window_visible(self, handle: int) -> bool:
        from Xlib import X
        from Xlib.error import XError

        dpy = self._open_display()
        try:
            win = dpy.create_resource_object("window", handle)
            return win.get_attributes().map_state == X.IsViewable
        except XError:
            return False
        finally:
            dpy.close()

    def _wait_closed(self, handle: int, timeout: float = TIMEOUT_PROC_WAIT) -> None:
        wait_until(
            lambda: not self._is_window_visible(handle),
            timeout=timeout,
            interval=POLL_INTERVAL_FAST,
            description=f"X11 dialog {handle} to close",
        )

    def _is_window_or_descendant_focused(self, target_wid: int) -> bool:
        res = self._run_xdotool("getwindowfocus", check=False)
        raw = res.stdout.strip()
        if res.returncode != 0 or not raw.isdigit():
            return False
        focused_wid = int(raw)
        if focused_wid == target_wid:
            return True

        from Xlib import X
        from Xlib.error import XError

        dpy = self._open_display()
        try:
            current = dpy.create_resource_object("window", focused_wid)
            for _ in range(32):
                tree = current.query_tree()
                parent = tree.parent
                if not parent or getattr(parent, "id", parent) == X.NONE:
                    return False
                if int(parent.id) == target_wid:
                    return True
                if int(parent.id) == int(tree.root.id):
                    return False
                current = parent
        except XError:
            return False
        finally:
            dpy.close()
        return False

    def _focus_window(self, wid: str) -> None:
        target_wid = int(wid)
        self._run_xdotool("windowactivate", "--sync", wid, check=False)
        self._run_xdotool("windowfocus", "--sync", wid, check=False)
        wait_until(
            lambda: self._is_window_or_descendant_focused(target_wid),
            timeout=5.0,
            interval=POLL_INTERVAL_FAST,
            description=f"X11 window {wid} to gain focus",
        )

    def _clear_focused_entry(self) -> None:
        self._run_xdotool("key", "--clearmodifiers", "Home", "Shift+End", "BackSpace", check=False)

    def enter_text_and_accept(self, window: DialogWindow, text: str) -> None:
        wid = str(window.handle)
        self._focus_window(wid)
        self._clear_focused_entry()
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

    def select_folder(self, window: DialogWindow, folder_path: Path) -> None:
        wid = str(window.handle)
        self._focus_window(wid)
        self._clear_focused_entry()
        self._run_xdotool(
            "type",
            "--clearmodifiers",
            "--delay",
            XDOTOOL_TYPING_DELAY_MS,
            "--",
            str(folder_path),
        )
        time.sleep(POLL_INTERVAL_FAST)
        self._run_xdotool("key", "--clearmodifiers", "Return")
        try:
            self._wait_closed(window.handle, timeout=1.5)
        except TimeoutError:
            # Tk's tkfbox directory dialog navigates into the typed path on first Return.
            self._run_xdotool("key", "--clearmodifiers", "Return")
            self._wait_closed(window.handle, timeout=TIMEOUT_PROC_WAIT)

    def capture_screenshot(self, output_path: Path) -> Path | None:
        if not self.display:
            return None
        from Xlib import X

        dpy = self._open_display()
        try:
            root = dpy.screen().root
            geom = root.get_geometry()
            width, height = int(geom.width), int(geom.height)
            if width <= 0 or height <= 0:
                return None
            img = root.get_image(0, 0, width, height, X.ZPixmap, 0xFFFFFFFF)
            raw = img.data if isinstance(img.data, (bytes, bytearray)) else bytes(img.data)
            if len(raw) == width * height * 4:
                return write_rgb_png(output_path, width, height, bytes(raw), bgrx=True)
            if len(raw) == width * height * 3:
                return write_rgb_png(output_path, width, height, bytes(raw), bgrx=False)
            return None
        finally:
            dpy.close()

    def close(self) -> None:
        for attr in ("_tray_process", "_wm_process", "_xvfb_process"):
            proc = getattr(self, attr)
            if proc is not None:
                terminate_process_tree(proc, timeout=3.0)
                setattr(self, attr, None)
        if self._owns_log_dir and self._log_dir is not None:
            shutil.rmtree(self._log_dir, ignore_errors=True)
            self._log_dir = None
