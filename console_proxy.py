import queue
import threading
from io import StringIO
from rich.console import Console as RichConsole
from rich.text import Text

_app = None
_input_queue: queue.Queue = queue.Queue()


def set_app(app) -> None:
    global _app
    _app = app


def submit_input(value: str) -> None:
    _input_queue.put(value)


def show_thinking() -> None:
    if _app is not None:
        _app.call_from_thread(_app.show_thinking)


def hide_thinking() -> None:
    if _app is not None:
        _app.call_from_thread(_app.hide_thinking)


def exit_app(return_code: int = 0) -> None:
    if _app is not None:
        _app.call_from_thread(_app.exit, return_code)
        threading.Event().wait()  # block this thread; process exits when Textual finishes cleanup
    import os
    os._exit(return_code)


def _only_sgr(text: str) -> str:
    """Strip all ANSI escape sequences except SGR color/style codes (ESC[...m)."""
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\x1b' and i + 1 < len(text):
            if text[i + 1] == '[':
                j = i + 2
                while j < len(text) and (text[j].isdigit() or text[j] == ';'):
                    j += 1
                if j < len(text) and text[j] == 'm':
                    result.append(text[i:j + 1])  # keep SGR
                i = j + 1
            else:
                i += 2  # skip 2-char non-CSI escape sequence
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


class ConsoleProxy:
    def __init__(self):
        self._fallback = RichConsole()

    def print(self, *args, **kwargs) -> None:
        if _app is None:
            self._fallback.print(*args, **kwargs)
            return
        sio = StringIO()
        tmp = RichConsole(file=sio, force_terminal=True, highlight=False, width=120)
        tmp.print(*args, **kwargs)
        rendered = Text.from_ansi(_only_sgr(sio.getvalue().rstrip('\n')))
        _app.call_from_thread(_app.query_one("#log").write, rendered)

    def input(self, prompt: str = "") -> str:
        if prompt:
            self.print(prompt, end="")
        return _input_queue.get()

    def clear(self) -> None:
        pass
