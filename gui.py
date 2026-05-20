import threading
from textual.app import App, ComposeResult
from textual.events import Paste
from textual.widgets import RichLog, Input, Header
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
    Input {
        dock: bottom;
        border: tall $accent;
        margin: 0 1 1 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Input(placeholder="Message Gitpanion...", id="input")

    def on_mount(self) -> None:
        console_proxy.set_app(self)
        self.query_one("#input", Input).focus()
        threading.Thread(target=self._run, daemon=True).start()

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
