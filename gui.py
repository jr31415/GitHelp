import threading
from textual.app import App, ComposeResult
from textual.events import Paste
from textual.widgets import RichLog, Input, Header, Static
import console_proxy


class GitpanionApp(App):
    CSS = """
    Header {
        background: $primary;
    }
    RichLog {
        height: 1fr;
        scrollbar-gutter: stable;
        padding: 0 1;
        background: $surface;
    }
    #thinking {
        display: none;
        color: $text-muted;
        padding: 0 1;
        height: 1;
    }
    #thinking.active {
        display: block;
    }
    Input {
        dock: bottom;
        border: tall $accent;
        margin: 0 1 1 1;
    }
    """

    THINKING_FRAMES = ["Thinking", "Thinking.", "Thinking..", "Thinking..."]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Static("", id="thinking")
        yield Input(placeholder="Message Gitpanion...", id="input")

    def on_mount(self) -> None:
        console_proxy.set_app(self)
        self.query_one("#input", Input).focus()
        self._thinking_timer = None
        self._thinking_frame = 0
        threading.Thread(target=self._run, daemon=True).start()

    def show_thinking(self) -> None:
        widget = self.query_one("#thinking", Static)
        widget.add_class("active")
        self._thinking_frame = 0
        widget.update(self.THINKING_FRAMES[0])
        self._thinking_timer = self.set_interval(0.4, self._animate_thinking)

    def hide_thinking(self) -> None:
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None
        widget = self.query_one("#thinking", Static)
        widget.remove_class("active")
        widget.update("")

    def _animate_thinking(self) -> None:
        self._thinking_frame = (self._thinking_frame + 1) % len(self.THINKING_FRAMES)
        self.query_one("#thinking", Static).update(self.THINKING_FRAMES[self._thinking_frame])

    def _run(self) -> None:
        import main
        main.run()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        event.input.clear()
        event.input.focus()
        if value:
            self.query_one("#log", RichLog).write(f"[bold]>[/bold] {value}")
        console_proxy.submit_input(value)

    def on_paste(self, event: Paste) -> None:
        input_widget = self.query_one("#input", Input)
        input_widget.focus()
        input_widget.insert_text_at_cursor(event.text)


if __name__ == "__main__":
    GitpanionApp().run()
