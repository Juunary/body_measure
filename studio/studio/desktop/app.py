"""Windows application entry point."""
import multiprocessing
from pathlib import Path
import sys


def asset(name):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "static" / name


def main():
    import webview
    from .bridge import DesktopBridge
    bridge = DesktopBridge()
    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    window = webview.create_window("Maß-DPP Polo Simulator", str(asset("desktop.html")),
                                   js_api=bridge, width=1280, height=820,
                                   min_size=(980, 680), maximized=True)
    bridge._window = window
    webview.start(gui="edgechromium", debug=False, private_mode=True)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
