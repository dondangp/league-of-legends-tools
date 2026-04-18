from __future__ import annotations

import subprocess
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from tkinter import ttk

from AppKit import NSApp
from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    kCFRunLoopCommonModes,
    kCGEventKeyDown,
    kCGEventFlagMaskControl,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
    kCGEventTapOptionListenOnly,
)


FLASH_COOLDOWN = 300
ROWS = ["Top", "Jungle", "Mid", "ADC", "Support"]
ROLE_HOTKEYS = {
    "Top": "1",
    "Jungle": "2",
    "Mid": "3",
    "ADC": "4",
    "Support": "5",
}


def format_seconds(total_seconds: float) -> str:
    total_seconds = max(0, int(round(total_seconds)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


@dataclass
class ActiveTimer:
    end_game_time: float


class EnemyRow:
    def __init__(self, app: "LeagueOverlayApp", parent: ttk.Frame, role: str) -> None:
        self.app = app
        self.role = role
        self.active_timer: ActiveTimer | None = None

        frame = ttk.Frame(parent, style="Row.TFrame", padding=(6, 5))
        frame.pack(fill="x", pady=1)

        ttk.Label(frame, text=f"{role} [{ROLE_HOTKEYS[role]}]", style="Role.TLabel", width=10).pack(side="left")
        ttk.Label(frame, text="F", style="FlashIcon.TLabel", width=2, anchor="center").pack(side="left", padx=(0, 6))

        self.timer_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.timer_var, style="Timer.TLabel", anchor="e").pack(side="right")

    def start_flash(self) -> None:
        current_game_time = self.app.get_game_time_seconds()
        self.active_timer = ActiveTimer(end_game_time=current_game_time + FLASH_COOLDOWN)
        self.update(current_game_time)

    def clear(self) -> None:
        self.active_timer = None
        self.timer_var.set("Ready")

    def update(self, current_game_time: float) -> None:
        if not self.active_timer:
            return

        remaining = self.active_timer.end_game_time - current_game_time
        if remaining <= 0:
            self.active_timer = None
            self.timer_var.set("Ready")
            self.app.announce_ready(self.role)
            return

        self.timer_var.set(format_seconds(remaining))


class LeagueOverlayApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("LeagueOverlayHUD")
        self.root.geometry(self._default_geometry())
        self.root.configure(bg="#0b1220")
        self.root.attributes("-alpha", 0.34)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)

        self.started_at = time.monotonic()
        self.ns_window = None
        self.event_tap = None
        self.event_source = None
        self.pending_keys: deque[str] = deque()

        self.status_var = tk.StringVar(value="Ctrl+1..5 flash  Ctrl+0 reset")

        self._build_styles()
        self._build_layout()
        self._bind_local_shortcuts()

        self.root.after(50, self._enable_clickthrough)
        self.root.after(50, self._install_global_shortcuts)
        self.root.after(50, self._pin_overlay)
        self.root.after(60, self._drain_pending_keys)
        self._tick()

    def _default_geometry(self) -> str:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = 172
        height = 238
        x = max(8, screen_width - width - 8)
        y = max(12, int(screen_height * 0.14))
        return f"{width}x{height}+{x}+{y}"

    def _build_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Root.TFrame", background="#0b1220")
        style.configure("Header.TFrame", background="#111827")
        style.configure("Row.TFrame", background="#111827")
        style.configure(
            "Title.TLabel",
            background="#111827",
            foreground="#e5e7eb",
            font=("Avenir Next", 10, "bold"),
        )
        style.configure(
            "Hint.TLabel",
            background="#111827",
            foreground="#94a3b8",
            font=("Avenir Next", 7),
        )
        style.configure(
            "Role.TLabel",
            background="#111827",
            foreground="#e5e7eb",
            font=("Avenir Next", 9, "bold"),
        )
        style.configure(
            "FlashIcon.TLabel",
            background="#facc15",
            foreground="#111827",
            font=("Avenir Next", 9, "bold"),
        )
        style.configure(
            "Timer.TLabel",
            background="#111827",
            foreground="#f8fafc",
            font=("Menlo", 10, "bold"),
        )

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="Root.TFrame", padding=4)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="Header.TFrame", padding=(6, 5))
        header.pack(fill="x", pady=(0, 2))
        self._enable_drag(header)

        top = ttk.Frame(header, style="Header.TFrame")
        top.pack(fill="x")
        self._enable_drag(top)

        ttk.Label(top, text="Flash HUD", style="Title.TLabel").pack(side="left")

        ttk.Label(header, textvariable=self.status_var, style="Hint.TLabel").pack(anchor="w", pady=(2, 0))

        board = ttk.Frame(outer, style="Root.TFrame")
        board.pack(fill="both", expand=True)

        self.rows = {role: EnemyRow(self, board, role) for role in ROWS}

    def _bind_local_shortcuts(self) -> None:
        self.root.bind("<Control-Key-1>", lambda _event: self.trigger_role("Top"))
        self.root.bind("<Control-Key-2>", lambda _event: self.trigger_role("Jungle"))
        self.root.bind("<Control-Key-3>", lambda _event: self.trigger_role("Mid"))
        self.root.bind("<Control-Key-4>", lambda _event: self.trigger_role("ADC"))
        self.root.bind("<Control-Key-5>", lambda _event: self.trigger_role("Support"))
        self.root.bind("<Control-Key-0>", lambda _event: self.reset_all())

    def _install_global_shortcuts(self) -> None:
        if self.event_tap is not None:
            return

        keycode_map = {
            18: "1",
            19: "2",
            20: "3",
            21: "4",
            23: "5",
            29: "0",
        }

        def handler(_proxy, event_type, event, _refcon):
            if event_type == kCGEventKeyDown:
                flags = CGEventGetFlags(event)
                if not (flags & kCGEventFlagMaskControl):
                    return event
                keycode = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
                key = keycode_map.get(keycode)
                if key:
                    self.pending_keys.append(key)
            return event

        self.event_tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            CGEventMaskBit(kCGEventKeyDown),
            handler,
            None,
        )

        if self.event_tap is None:
            self.status_var.set("Grant Accessibility to use Ctrl+1..5 and Ctrl+0 in game")
            return

        self.event_source = CFMachPortCreateRunLoopSource(None, self.event_tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), self.event_source, kCFRunLoopCommonModes)
        CGEventTapEnable(self.event_tap, True)

    def _drain_pending_keys(self) -> None:
        while self.pending_keys:
            self._handle_key(self.pending_keys.popleft())
        self.root.after(60, self._drain_pending_keys)

    def _handle_key(self, key: str) -> None:
        if key == "1":
            self.trigger_role("Top")
        elif key == "2":
            self.trigger_role("Jungle")
        elif key == "3":
            self.trigger_role("Mid")
        elif key == "4":
            self.trigger_role("ADC")
        elif key == "5":
            self.trigger_role("Support")
        elif key == "0":
            self.reset_all()

    def _enable_clickthrough(self) -> None:
        self.root.update_idletasks()
        self.root.update()
        for window in NSApp.windows():
            if str(window.title()) == self.root.title():
                self.ns_window = window
                break

        if self.ns_window is not None:
            self.ns_window.setIgnoresMouseEvents_(True)

    def _pin_overlay(self) -> None:
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(1500, self._pin_overlay)

    def _enable_drag(self, widget: ttk.Frame) -> None:
        widget.bind("<ButtonPress-1>", self._start_drag)
        widget.bind("<B1-Motion>", self._drag_window)

    def _start_drag(self, event: tk.Event) -> None:
        self.drag_origin_x = event.x_root - self.root.winfo_x()
        self.drag_origin_y = event.y_root - self.root.winfo_y()

    def _drag_window(self, event: tk.Event) -> None:
        next_x = event.x_root - self.drag_origin_x
        next_y = event.y_root - self.drag_origin_y
        self.root.geometry(f"+{next_x}+{next_y}")

    def set_focus(self, role: str) -> None:
        self.trigger_role(role)

    def trigger_role(self, role: str) -> None:
        self.rows[role].start_flash()

    def reset_all(self) -> None:
        self.started_at = time.monotonic()
        for row in self.rows.values():
            row.clear()

    def get_game_time_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def announce_ready(self, role: str) -> None:
        phrase = f"{role} completed"
        try:
            subprocess.Popen(["say", phrase], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.root.bell()

    def _tick(self) -> None:
        current_game_time = self.get_game_time_seconds()
        for row in self.rows.values():
            row.update(current_game_time)
        self.root.after(250, self._tick)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    LeagueOverlayApp().run()
