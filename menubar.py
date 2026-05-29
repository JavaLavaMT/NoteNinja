"""
NoteNinja menu bar / system tray app.
  macOS   — 🥷 icon in the menu bar (rumps)
  Windows — NJ icon in the system tray (pystray)
"""
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

# Hide from dock immediately — before any UI framework initializes
if platform.system() == "Darwin":
    try:
        import AppKit
        _app = AppKit.NSApplication.sharedApplication()
        _app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    except Exception:
        pass

# Single-instance guard — exit silently if already running
import sys, atexit
_LOCK = Path.home() / ".noteninja.lock"

def _acquire_lock():
    if _LOCK.exists():
        try:
            pid = int(_LOCK.read_text().strip())
            os.kill(pid, 0)  # raises if process doesn't exist
            print("NoteNinja is already running.")
            sys.exit(0)
        except (ProcessLookupError, ValueError, OSError):
            pass  # stale lock — take it over
    _LOCK.write_text(str(os.getpid()))
    atexit.register(lambda: _LOCK.unlink(missing_ok=True))

_acquire_lock()

DIR = str(Path(__file__).parent)
NOTES_DIR = Path.home() / "meeting-notes"
SYSTEM = platform.system()
POLL_INTERVAL = 10
CALL_AUDIO_THRESHOLD = 300
ALERT_COOLDOWN = 60
RECENT_COUNT = 5

# ── Shared state ────────────────────────────────────────────────────────────

_watching = True
_last_alerted = 0
_teams_alert_active = False


def _open_folder():
    """Open the notes directory in Finder/Explorer."""
    NOTES_DIR.mkdir(exist_ok=True)
    if SYSTEM == "Darwin":
        subprocess.run(["open", str(NOTES_DIR)])
    else:
        subprocess.Popen(["explorer", str(NOTES_DIR)])


def _open_file(path):
    """Open a file in the default app."""
    if SYSTEM == "Darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.Popen(["start", "", str(path)], shell=True)


def _recent_notes():
    """Return the most recent notes .md files, newest first."""
    if not NOTES_DIR.exists():
        return []
    files = sorted(NOTES_DIR.glob("*_notes.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:RECENT_COUNT]


def _open_terminal(command):
    """Open a terminal window and run a NoteNinja command."""
    if SYSTEM == "Darwin":
        script = f"""
            set ninjaDir to "{DIR}"
            set theCmd to "cd " & quoted form of ninjaDir & " && {command}"
            if application "iTerm" exists then
                tell application "iTerm"
                    activate
                    create window with default profile
                    tell current session of current window
                        write text theCmd
                    end tell
                end tell
            else
                tell application "Terminal"
                    activate
                    do script theCmd
                end tell
            end if
        """
        subprocess.run(["osascript", "-e", script], capture_output=True)
    else:
        # Try Windows Terminal, fall back to cmd
        try:
            subprocess.Popen(f'wt -d "{DIR}" cmd /k "{command}"')
        except FileNotFoundError:
            subprocess.Popen(f'cmd /k "cd /d "{DIR}" && {command}"', shell=True)


def _send_notification(title, message):
    try:
        if SYSTEM == "Darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}" sound name "Glass"'],
                capture_output=True
            )
        else:
            from plyer import notification
            notification.notify(title=title, message=message, app_name="NoteNinja", timeout=10)
    except Exception:
        pass


def _watch_loop(on_call_detected, on_call_ended, on_status):
    """Background thread: polls for Teams call activity."""
    from main import teams_is_running, audio_level, find_aggregate_device
    import recorder

    global _watching, _last_alerted, _teams_alert_active

    devices = recorder.list_input_devices()
    agg = find_aggregate_device(devices)

    while True:
        try:
            if _watching and agg and teams_is_running():
                level = audio_level(agg[0])
                now = time.time()
                if level > CALL_AUDIO_THRESHOLD and (now - _last_alerted) > ALERT_COOLDOWN:
                    _last_alerted = now
                    _teams_alert_active = True
                    on_call_detected()
                    _send_notification("NoteNinja", "Teams call detected — click the icon to record")
            else:
                if _teams_alert_active:
                    _teams_alert_active = False
                    on_call_ended()
                on_status("Watching paused" if not _watching else "Watching for calls...")
        except Exception:
            pass

        time.sleep(POLL_INTERVAL)


# ── macOS — rumps ────────────────────────────────────────────────────────────

def _run_mac():
    import rumps

    icon_path = str(Path(__file__).parent / "icon.png")
    menu_icon = icon_path if os.path.exists(icon_path) else None

    class NoteNinjaApp(rumps.App):
        def __init__(self):
            super().__init__("", icon=menu_icon, template=False, quit_button=None)

            self._status = rumps.MenuItem("Watching for calls...")
            self._status.set_callback(None)
            self._alert = rumps.MenuItem("⚡ Teams call detected — record now",
                                         callback=self._on_alert_clicked)
            self._alert.hidden = True
            self._toggle = rumps.MenuItem("⏸ Pause watching", callback=self._toggle_watching)

            self._recent_menu = rumps.MenuItem("Recent meetings")
            # Populate inline — can't call clear() before menu is attached to the app
            notes = _recent_notes()
            if notes:
                for f in notes:
                    label = f.stem.replace("_notes", "").replace("_", " ").strip()
                    self._recent_menu[label] = rumps.MenuItem(
                        label, callback=lambda _, p=f: _open_file(p)
                    )
            else:
                self._recent_menu["No meetings yet"] = rumps.MenuItem(
                    "No meetings yet", callback=None
                )

            self.menu = [
                self._status,
                self._alert,
                None,
                rumps.MenuItem("Record in-person meeting", callback=lambda _: _open_terminal("./nj mic")),
                rumps.MenuItem("Record Teams call",        callback=lambda _: _open_terminal("./nj teams")),
                None,
                self._recent_menu,
                rumps.MenuItem("Open notes folder", callback=lambda _: _open_folder()),
                None,
                self._toggle,
                rumps.MenuItem("Settings...", callback=self._open_settings),
                rumps.MenuItem("Quit", callback=rumps.quit_application),
            ]

            threading.Thread(
                target=_watch_loop,
                args=(self._call_detected, self._call_ended, self._update_status),
                daemon=True
            ).start()

        def _refresh_recent(self):
            self._recent_menu.clear()
            notes = _recent_notes()
            if notes:
                for f in notes:
                    # Trim the _notes suffix for a cleaner label
                    label = f.stem.replace("_notes", "").replace("_", " ").strip()
                    self._recent_menu[label] = rumps.MenuItem(
                        label, callback=lambda _, p=f: _open_file(p)
                    )
            else:
                self._recent_menu["No meetings yet"] = rumps.MenuItem(
                    "No meetings yet", callback=None
                )

        def _call_detected(self):
            self.title = "🔴"
            self._status.title = "Teams call active"
            self._alert.hidden = False

        def _call_ended(self):
            self._alert.hidden = True
            self.title = "" if _watching else "⏸"
            self._refresh_recent()

        def _update_status(self, text):
            self._status.title = text

        def _open_settings(self, _):
            import sys
            subprocess.Popen([sys.executable, str(Path(__file__).parent / "settings_window.py")])

        def _on_alert_clicked(self, _):
            self._alert.hidden = True
            self.title = "🥷"
            _open_terminal("./nj teams")

        def _toggle_watching(self, _):
            global _watching
            _watching = not _watching
            if _watching:
                self._toggle.title = "⏸ Pause watching"
                self._status.title = "Watching for calls..."
                self.title = ""
            else:
                self._toggle.title = "▶ Resume watching"
                self._status.title = "Watching paused"
                self._alert.hidden = True
                self.title = "⏸"

    NoteNinjaApp().run()


# ── Windows — pystray ────────────────────────────────────────────────────────

def _open_settings_win():
    import sys
    subprocess.Popen([sys.executable, str(Path(__file__).parent / "settings_window.py")])


def _run_windows():
    import pystray
    from PIL import Image, ImageDraw, ImageFont

    def _make_icon(alert=False):
        bg = (180, 30, 30) if alert else (26, 26, 46)
        img = Image.new("RGBA", (64, 64), bg)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 26)
        except Exception:
            font = ImageFont.load_default()
        draw.text((10, 16), "NJ", fill="white", font=font)
        return img

    icon_holder = [None]

    def _recent_submenu():
        notes = _recent_notes()
        if not notes:
            return pystray.Menu(pystray.MenuItem("No meetings yet", None, enabled=False))
        return pystray.Menu(*[
            pystray.MenuItem(
                f.stem.replace("_notes", "").replace("_", " ").strip(),
                lambda _, p=f: _open_file(p)
            ) for f in notes
        ])

    def _build_menu():
        items = []
        if _teams_alert_active:
            items.append(pystray.MenuItem(
                "⚡ Teams call detected — record now",
                lambda: _open_terminal("nj.bat teams")
            ))
            items.append(pystray.Menu.SEPARATOR)
        items += [
            pystray.MenuItem("Record in-person meeting", lambda: _open_terminal("nj.bat mic")),
            pystray.MenuItem("Record Teams call",        lambda: _open_terminal("nj.bat teams")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Recent meetings", _recent_submenu()),
            pystray.MenuItem("Open notes folder", lambda: _open_folder()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: "▶ Resume watching" if not _watching else "⏸ Pause watching",
                _toggle
            ),
            pystray.MenuItem("Settings...", lambda: _open_settings_win()),
            pystray.MenuItem("Quit", lambda: icon_holder[0].stop()),
        ]
        return pystray.Menu(*items)

    def _toggle(icon, item):
        global _watching
        _watching = not _watching
        icon.menu = _build_menu()

    def _call_detected():
        if icon_holder[0]:
            icon_holder[0].icon = _make_icon(alert=True)
            icon_holder[0].menu = _build_menu()

    def _call_ended():
        if icon_holder[0]:
            icon_holder[0].icon = _make_icon(alert=False)
            icon_holder[0].menu = _build_menu()

    def _update_status(text):
        if icon_holder[0]:
            icon_holder[0].title = text

    threading.Thread(
        target=_watch_loop,
        args=(_call_detected, _call_ended, _update_status),
        daemon=True
    ).start()

    icon = pystray.Icon(
        "NoteNinja",
        _make_icon(),
        "NoteNinja — Watching for calls...",
        menu=_build_menu()
    )
    icon_holder[0] = icon
    icon.run()


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if SYSTEM == "Darwin":
        _run_mac()
    elif SYSTEM == "Windows":
        _run_windows()
    else:
        print("Menu bar is only supported on macOS and Windows.")
