import io

from bibcheck import cli


class FakeStream(io.StringIO):
    def __init__(self, is_tty: bool) -> None:
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def test_progressbar_auto_disabled_on_non_tty() -> None:
    stream = FakeStream(is_tty=False)
    progress = cli.ProgressBar(total=3, stream=stream, enabled=None)
    progress.update(1)
    progress.finish()
    assert stream.getvalue() == ""


def test_progressbar_outputs_with_eta(monkeypatch) -> None:
    stream = FakeStream(is_tty=True)
    times = [0.0, 1.0]

    def fake_time() -> float:
        return times.pop(0) if times else 1.0

    monkeypatch.setattr(cli.time, "time", fake_time)
    progress = cli.ProgressBar(total=2, stream=stream, enabled=True)
    progress.update(1)
    progress.finish()
    output = stream.getvalue()
    assert "进度" in output
    assert "ETA" in output
    assert "\n" in output
