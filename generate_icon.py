"""
Generates NoteNinja.icns (macOS) and icon.png (Windows) from the 🥷 emoji.
Run directly: python generate_icon.py
Called automatically by setup.sh.
"""
import os
import subprocess
import tempfile
from pathlib import Path

DIR = Path(__file__).parent
SIZE = 1024


def make_png(out_path):
    """Resize icon.png to 1024x1024 if needed."""
    from PIL import Image
    src = DIR / "icon.png"
    if not src.exists():
        raise FileNotFoundError(f"icon.png not found at {src}")
    img = Image.open(src).convert("RGBA").resize((SIZE, SIZE), Image.LANCZOS)
    img.save(out_path, "PNG")
    print(f"  Prepared: {out_path}")


def make_icns(png_path, icns_path):
    iconset = Path(tempfile.mkdtemp()) / "NoteNinja.iconset"
    iconset.mkdir()

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for s in sizes:
        out = iconset / f"icon_{s}x{s}.png"
        subprocess.run(["sips", "-z", str(s), str(s), str(png_path), "--out", str(out)],
                       capture_output=True)
        if s <= 512:
            out2x = iconset / f"icon_{s}x{s}@2x.png"
            s2 = s * 2
            subprocess.run(["sips", "-z", str(s2), str(s2), str(png_path), "--out", str(out2x)],
                           capture_output=True)

    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns_path)],
                   capture_output=True)
    print(f"  Generated: {icns_path}")


def apply_to_app(icns_path, app_path):
    resources = Path(app_path) / "Contents" / "Resources"
    if not resources.exists():
        print(f"  App not found at {app_path} — skipping icon apply.")
        return
    dest = resources / "applet.icns"
    import shutil
    shutil.copy(icns_path, dest)
    # Touch the app to force Finder to refresh its icon cache
    subprocess.run(["touch", str(app_path)], capture_output=True)
    subprocess.run(["killall", "Dock"], capture_output=True)
    print(f"  Applied icon to {app_path}")


if __name__ == "__main__":
    import platform
    try:
        png_path = DIR / "icon.png"
        make_png(png_path)

        if platform.system() == "Darwin":
            icns_path = DIR / "NoteNinja.icns"
            make_icns(png_path, icns_path)
            app_path = Path.home() / "Applications" / "NoteNinja.app"
            if app_path.exists():
                apply_to_app(icns_path, app_path)
        print("  Done.")
    except Exception as e:
        print(f"  Icon generation skipped: {e}")
