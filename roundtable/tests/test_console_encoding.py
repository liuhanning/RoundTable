import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.console_encoding import configure_utf8_console


class _FakeStream:
    def __init__(self):
        self.calls = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)

    def isatty(self):
        return True


def test_configure_utf8_console_reconfigures_standard_streams(monkeypatch):
    fake_stdout = _FakeStream()
    fake_stderr = _FakeStream()

    monkeypatch.setattr("utils.console_encoding.os.name", "nt")
    monkeypatch.setattr("utils.console_encoding.sys.stdout", fake_stdout)
    monkeypatch.setattr("utils.console_encoding.sys.stderr", fake_stderr)

    configure_utf8_console()

    assert fake_stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert fake_stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]
