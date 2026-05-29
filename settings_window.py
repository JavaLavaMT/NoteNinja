"""
NoteNinja Settings window.
Launched as a subprocess from the menu bar — runs independently.
"""
import json
import os
import platform
import subprocess
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path


DEFAULT_ENV_PATH = Path(__file__).parent / ".env"
CONFIG_PATH      = Path(__file__).parent / "config.json"

# Default env var names — users can override these in Settings
FIELDS = [
    ("OpenAI API Key",    "OPENAI_API_KEY",    "Listens to your audio and converts speech → text  (~$0.006/min)",  "https://platform.openai.com/api-keys"),
    ("Anthropic API Key", "ANTHROPIC_API_KEY", "Reads the transcript and writes structured notes  (~$0.01/meeting)", "https://console.anthropic.com/settings/keys"),
    ("HuggingFace Token", "HUGGINGFACE_TOKEN", "Optional — labels who said what (Speaker A, Speaker B...)",         "https://huggingface.co/settings/tokens"),
]
DEFAULT_KEY_NAMES = {default: default for _, default, _, _url in FIELDS}


def load_config():
    defaults = {**DEFAULT_KEY_NAMES, "env_file": str(DEFAULT_ENV_PATH)}
    if CONFIG_PATH.exists():
        try:
            return {**defaults, **json.loads(CONFIG_PATH.read_text())}
        except Exception:
            pass
    return defaults


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


def get_env_path(config):
    return Path(config.get("env_file", str(DEFAULT_ENV_PATH))).expanduser()


def parse_env_file(path):
    """Parse KEY=VALUE or export KEY=VALUE from any env/shell config file."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            # Strip surrounding quotes
            v = v.strip().strip('"').strip("'")
            values[k.strip()] = v
    return values


def load_env(config=None):
    if config is None:
        config = load_config()
    env_path = get_env_path(config)
    values = parse_env_file(env_path)
    # Fall back to os.environ for anything missing
    for _, default_key, *_ in FIELDS:
        if not values.get(config.get(default_key, default_key)) and os.environ.get(default_key):
            values[default_key] = os.environ[default_key]
    return values


def save_env(values_by_custom_key, env_path, keys_to_remove=None):
    """Write key=value pairs, removing any stale/renamed keys."""
    is_shell_config = env_path.name.startswith(".") and \
                      env_path.suffix not in (".env",)

    existing_lines = env_path.read_text().splitlines() if env_path.exists() else []
    remove = set(keys_to_remove or [])
    updated_keys = set()
    new_lines = []

    for line in existing_lines:
        stripped = line.strip()
        export_prefix = "export " if stripped.startswith("export ") else ""
        check = stripped[7:] if export_prefix else stripped
        if "=" in check and not check.startswith("#"):
            k = check.partition("=")[0].strip()
            if k in remove:
                continue  # drop stale key entirely
            if k in values_by_custom_key and values_by_custom_key[k]:
                new_lines.append(f"{export_prefix}{k}={values_by_custom_key[k]}")
                updated_keys.add(k)
                continue
        new_lines.append(line)

    # Append brand-new keys
    for k, v in values_by_custom_key.items():
        if k and v and k not in updated_keys:
            prefix = "export " if is_shell_config else ""
            new_lines.append(f"{prefix}{k}={v}")

    env_path.write_text("\n".join(new_lines) + "\n")


def main():
    root = tk.Tk()
    root.title("NoteNinja Settings")
    root.resizable(False, False)

    # Set ninja icon in dock — must happen after tk.Tk() to avoid AppKit/Tk conflict
    if platform.system() == "Darwin":
        try:
            import AppKit
            ns_app = AppKit.NSApplication.sharedApplication()
            ns_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
            icon_path = str(Path(__file__).parent / "icon.png")
            if os.path.exists(icon_path):
                ns_img = AppKit.NSImage.alloc().initWithContentsOfFile_(icon_path)
                if ns_img:
                    ns_app.setApplicationIconImage_(ns_img)
        except Exception:
            pass

    # ── Fonts & colours ──────────────────────────────────────────────────────
    BG      = "#1e1e2e"
    CARD    = "#2a2a3e"
    FG      = "#e0e0f0"
    SUBTLE  = "#888899"
    ACCENT  = "#5b8dee"
    DANGER  = "#e05b5b"
    RADIUS  = 8

    root.configure(bg=BG)

    title_font  = tkfont.Font(family="Helvetica Neue", size=16, weight="bold")
    label_font  = tkfont.Font(family="Helvetica Neue", size=12, weight="bold")
    hint_font   = tkfont.Font(family="Helvetica Neue", size=10)
    entry_font  = tkfont.Font(family="Menlo",          size=12)
    btn_font    = tkfont.Font(family="Helvetica Neue", size=12, weight="bold")

    # ── Header ───────────────────────────────────────────────────────────────
    header = tk.Frame(root, bg=BG)
    header.pack(fill="x", padx=28, pady=(24, 8))
    tk.Label(header, text="⚙  NoteNinja Settings",
             font=title_font, bg=BG, fg=FG).pack(anchor="w")
    tk.Label(header, text="Keys are saved to .env — never shared or uploaded.",
             font=hint_font, bg=BG, fg=SUBTLE).pack(anchor="w", pady=(2, 0))

    tk.Frame(root, bg=CARD, height=1).pack(fill="x", padx=28, pady=(8, 16))

    # ── Fields ───────────────────────────────────────────────────────────────
    existing = load_env()
    from tkinter import filedialog

    entries       = {}
    key_name_vars = {}
    config        = load_config()

    # ── Env file location ─────────────────────────────────────────────────────
    tk.Frame(root, bg=CARD, height=1).pack(fill="x", padx=28, pady=(8, 0))
    file_row = tk.Frame(root, bg=BG)
    file_row.pack(fill="x", padx=28, pady=(10, 4))
    tk.Label(file_row, text="Env file", font=label_font, bg=BG, fg=FG).pack(side="left")
    tk.Label(file_row, text="  Where your API keys are stored",
             font=hint_font, bg=BG, fg=SUBTLE).pack(side="left")

    env_file_var = tk.StringVar(value=config.get("env_file", str(DEFAULT_ENV_PATH)))
    env_file_entry = tk.Entry(file_row, textvariable=env_file_var, font=hint_font,
                              bg=CARD, fg=FG, insertbackground=FG,
                              relief="flat", bd=0, width=36)
    env_file_entry.pack(side="left", padx=(12, 0), ipady=4, ipadx=6)

    def browse():
        path = filedialog.askopenfilename(
            title="Select env file",
            initialdir=Path.home(),
            filetypes=[("Env / shell files", "*.env *.zprofile *.zshrc *.bashrc *.bash_profile *"),
                       ("All files", "*")]
        )
        if path:
            env_file_var.set(path)
            reload_values()

    browse_frame = tk.Frame(file_row, bg=ACCENT, cursor="hand2")
    browse_lbl   = tk.Label(browse_frame, text="Browse", font=hint_font,
                            bg=ACCENT, fg="white", padx=8, pady=4)
    browse_lbl.pack()
    for w in (browse_frame, browse_lbl):
        w.bind("<Button-1>", lambda e: browse())
        w.bind("<Enter>", lambda e: (browse_frame.config(bg="#4a7de0"), browse_lbl.config(bg="#4a7de0")))
        w.bind("<Leave>", lambda e: (browse_frame.config(bg=ACCENT),    browse_lbl.config(bg=ACCENT)))
    browse_frame.pack(side="left", padx=(8, 0))

    tk.Frame(root, bg=CARD, height=1).pack(fill="x", padx=28, pady=(10, 0))

    env_values = load_env(config)

    for key, default_key, hint, token_url in FIELDS:
        custom_key = config.get(default_key, default_key)
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=28, pady=6)

        lbl_row = tk.Frame(row, bg=BG)
        lbl_row.pack(anchor="w")
        tk.Label(lbl_row, text=key, font=label_font, bg=BG, fg=FG).pack(side="left")

        # Editable env var name
        key_var = tk.StringVar(value=custom_key)
        key_name_vars[default_key] = key_var
        key_entry = tk.Entry(lbl_row, textvariable=key_var, font=hint_font,
                             bg=CARD, fg=SUBTLE, insertbackground=SUBTLE,
                             relief="flat", bd=0, width=24)
        key_entry.pack(side="left", padx=(8, 0), ipady=2, ipadx=4)
        hint_row = tk.Frame(row, bg=BG)
        hint_row.pack(anchor="w", pady=(1, 4))
        tk.Label(hint_row, text=hint, font=hint_font, bg=BG, fg=SUBTLE).pack(side="left")
        link = tk.Label(hint_row, text="  Get key →", font=hint_font, bg=BG, fg=ACCENT, cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e, url=token_url: __import__("webbrowser").open(url))
        link.bind("<Enter>", lambda e, l=link: l.config(fg="#4a7de0"))
        link.bind("<Leave>", lambda e, l=link: l.config(fg=ACCENT))

        field_row = tk.Frame(row, bg=BG)
        field_row.pack(fill="x")

        # Load value using custom key name, fall back to default key name
        stored_value = env_values.get(custom_key) or env_values.get(default_key, "")
        var = tk.StringVar(value=stored_value)
        entry = tk.Entry(field_row, textvariable=var, font=entry_font,
                         bg=CARD, fg=FG, insertbackground=FG,
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=CARD, highlightcolor=ACCENT,
                         show="•", width=44)
        entry.pack(side="left", ipady=8, ipadx=8)
        entries[default_key] = var

        # Show / Hide toggle button
        showing = tk.BooleanVar(value=False)
        tog_frame = tk.Frame(field_row, bg=CARD, cursor="hand2")
        tog_label = tk.Label(tog_frame, text="Show", font=hint_font,
                             bg=CARD, fg=SUBTLE, padx=8, pady=4)
        tog_label.pack()

        def make_toggle(e, sv, tf, tl):
            def toggle(event=None):
                sv.set(not sv.get())
                if sv.get():
                    e.config(show="")
                    tl.config(text="Hide", fg=FG)
                else:
                    e.config(show="•")
                    tl.config(text="Show", fg=SUBTLE)
            for w in (tf, tl):
                w.bind("<Button-1>", toggle)
                w.bind("<Enter>", lambda e, f=tf, l=tl: (f.config(bg="#3a3a50"), l.config(bg="#3a3a50")))
                w.bind("<Leave>", lambda e, f=tf, l=tl: (f.config(bg=CARD),      l.config(bg=CARD)))
            return toggle

        make_toggle(entry, showing, tog_frame, tog_label)
        tog_frame.pack(side="left", padx=(8, 0))

    # ── Buttons ───────────────────────────────────────────────────────────────
    # ── Dependencies (macOS only) ─────────────────────────────────────────────
    if platform.system() == "Darwin":
        tk.Frame(root, bg=CARD, height=1).pack(fill="x", padx=28, pady=(16, 0))

        dep_header = tk.Frame(root, bg=BG)
        dep_header.pack(fill="x", padx=28, pady=(12, 4))
        tk.Label(dep_header, text="Audio Dependencies", font=label_font,
                 bg=BG, fg=FG).pack(anchor="w")

        DEPS = [
            ("BlackHole 2ch", "blackhole-2ch", "Required for recording Teams / phone calls"),
        ]

        def check_brew(pkg):
            r = subprocess.run(["brew", "list", pkg], capture_output=True)
            return r.returncode == 0

        def open_terminal_install(pkg, btn, status_lbl):
            btn.config(state="disabled")
            status_lbl.config(text="Opening terminal...", fg=SUBTLE)
            cmd = f"brew install {pkg} && echo '✓ Done — reboot to activate'"
            script = f'tell application "Terminal" to do script "{cmd}"'
            subprocess.run(["osascript", "-e", script])
            status_lbl.config(text="Check terminal to complete install", fg="#f0c040")

        for dep_name, pkg, dep_hint in DEPS:
            row = tk.Frame(root, bg=BG)
            row.pack(fill="x", padx=28, pady=3)

            installed = check_brew(pkg)
            status_text = "✓ Installed" if installed else "✗ Not installed"
            status_color = "#5ecf7a" if installed else DANGER

            tk.Label(row, text=dep_name, font=hint_font, bg=BG, fg=FG,
                     width=18, anchor="w").pack(side="left")
            status_lbl = tk.Label(row, text=status_text, font=hint_font,
                                  bg=BG, fg=status_color, width=16, anchor="w")
            status_lbl.pack(side="left")
            tk.Label(row, text=dep_hint, font=hint_font, bg=BG,
                     fg=SUBTLE).pack(side="left", padx=(8, 0))

            if not installed:
                btn_frame = tk.Frame(row, bg=ACCENT, cursor="hand2")
                btn_label = tk.Label(btn_frame, text="Install", font=hint_font,
                                     bg=ACCENT, fg="white", padx=10, pady=3)
                btn_label.pack()

                def make_install(p, bf, bl, sl):
                    def do_install(e=None):
                        bf.config(bg=SUBTLE); bl.config(bg=SUBTLE)
                        open_terminal_install(p, bf, sl)
                    def on_enter(e): bf.config(bg="#4a7de0"); bl.config(bg="#4a7de0")
                    def on_leave(e): bf.config(bg=ACCENT);    bl.config(bg=ACCENT)
                    for w in (bf, bl):
                        w.bind("<Button-1>", do_install)
                        w.bind("<Enter>",    on_enter)
                        w.bind("<Leave>",    on_leave)
                make_install(pkg, btn_frame, btn_label, status_lbl)
                btn_frame.pack(side="right")

    tk.Frame(root, bg=CARD, height=1).pack(fill="x", padx=28, pady=(20, 0))

    btn_row = tk.Frame(root, bg=BG)
    btn_row.pack(fill="x", padx=28, pady=16)

    saved_label = tk.Label(btn_row, text="", font=hint_font, bg=BG, fg="#5ecf7a")
    saved_label.pack(side="left")

    def cancel():
        root.destroy()

    def reload_values():
        fresh = load_env({**config, "env_file": env_file_var.get()})
        for dk, var in entries.items():
            custom = key_name_vars[dk].get().strip() or dk
            var.set(fresh.get(custom) or fresh.get(dk, ""))

    def save():
        new_config = {dk: key_name_vars[dk].get().strip() or dk
                      for dk in key_name_vars}
        new_config["env_file"] = env_file_var.get().strip()

        # Find old key names that were renamed so we can remove them
        stale_keys = [config[dk] for dk in key_name_vars
                      if config.get(dk) and config[dk] != new_config[dk]]

        save_config(new_config)
        env_path = Path(new_config["env_file"]).expanduser()
        save_env({new_config[dk]: entries[dk].get().strip() for dk in entries},
                 env_path, keys_to_remove=stale_keys)
        saved_label.config(text="✓ Saved")
        root.after(1500, root.destroy)

    def make_btn(parent, text, command, bg, fg, hover_bg):
        f = tk.Frame(parent, bg=bg, cursor="hand2")
        l = tk.Label(f, text=text, bg=bg, fg=fg, font=btn_font, padx=18, pady=8)
        l.pack()
        def enter(e): f.config(bg=hover_bg); l.config(bg=hover_bg)
        def leave(e): f.config(bg=bg);       l.config(bg=bg)
        def click(e): command()
        for w in (f, l):
            w.bind("<Enter>",    enter)
            w.bind("<Leave>",    leave)
            w.bind("<Button-1>", click)
        return f

    make_btn(btn_row, "Cancel", cancel, CARD,   SUBTLE,  "#3a3a50").pack(side="right", padx=(8, 0))
    make_btn(btn_row, "Save",   save,   ACCENT, "white", "#4a7de0").pack(side="right")

    # ── Center on screen ──────────────────────────────────────────────────────
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth()  - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"+{x}+{y}")

    root.mainloop()


if __name__ == "__main__":
    main()
