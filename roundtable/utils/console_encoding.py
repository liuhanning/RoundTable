"""
Console encoding helpers for Windows development.
"""
import os
import sys


def configure_utf8_console() -> None:
    """Best-effort UTF-8 console setup for Windows terminals."""
    if os.name != "nt":
        return

    stdout = getattr(sys, "stdout", None)
    stderr = getattr(sys, "stderr", None)

    # Keep pipe output on the platform default encoding so subprocess(text=True)
    # readers on Windows can decode it with the locale codec.
    if not all(getattr(stream, "isatty", lambda: False)() for stream in (stdout, stderr)):
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
