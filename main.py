import re
import time
import init
import ai_to_commands
from rich.console import Console
from github import Github, GithubException
from github import Auth
from pathlib import Path
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
console = Console()
console.clear()

#Settings for Gemini
model="gemini-3-flash-preview"

rules = init.get_settings()

print(rules)

def send_with_retry(chat, message, max_retries=5):
    delay = 5
    for attempt in range(max_retries):
        try:
            return chat.send_message(message)
        except genai_errors.APIError as e:
            if e.code == 429 and attempt < max_retries - 1:
                console.print(f"[yellow]Rate limited, retrying in {delay}s...[/yellow]")
                time.sleep(delay)
                delay *= 2
            else:
                raise


login_details = Path("auth.dat")
gemini_api = Path("api.dat")
access_token = login_details.read_text().strip()
key = gemini_api.read_text().strip()

github = init.attempt_login(access_token)
gemini = genai.Client(api_key=key)

prompt = Path("prompt.txt").read_text()
default_dir = rules.get("defaultgithubdir")
system_instruction = prompt + f"\n\nUser's default GitHub directory:\"{default_dir}\"" if default_dir else prompt

if rules.get("debug"):
    console.print(f"[bold]Settings: [/bold]{rules}")
    console.print(f"[bold]System Instruction: [/bold]{system_instruction}")


chat = gemini.chats.create(
    model=model,
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low"),
        system_instruction=system_instruction
    )
)

response = send_with_retry(chat, "Start")

MAX_RETRIES = 5

exit = False
while not exit:
    user_response = None
    parse_failed = False

    writeloc_pattern = re.compile(
        r'WRITELOC:[^\n]*file="((?:[^"\\]|\\.)*)"[^\n]*reason="((?:[^"\\]|\\.)*)"[^\n]*\n<FILE>\n(.*?)\n</FILE>',
        re.DOTALL
    )

    for attempt in range(MAX_RETRIES):
        parse_failed = False

        writeloc_blocks = []
        def _extract(m):
            writeloc_blocks.append((m.group(1), m.group(2), m.group(3)))
            return '__WRITELOC__'
        processed_text = writeloc_pattern.sub(_extract, response.text.strip())

        writeloc_idx = 0
        lines = [l.strip() for l in processed_text.split('\n') if l.strip()]

        for line in lines:
            if rules.get("debug"):
                console.print(f"[bold]RECEIVED <- [/bold][orange]{line}[/orange]")
            try:
                if line == '__WRITELOC__':
                    if rules.get("debug"):
                        console.print("[bold]ATTEMPT COMMAND: [/bold][yellow]__WRITELOC__[/yellow]")
                    file_path, reason, content = writeloc_blocks[writeloc_idx]
                    writeloc_idx += 1
                    wrote = ai_to_commands.writeloc_direct(file_path, content, reason, autowrite=rules.get("autowrite"))
                    user_response = "File written successfully." if wrote else "User denied the file write."
                else:
                    command, out1, out2, out3 = ai_to_commands.interpret(line)
                    if rules.get("debug"):
                        console.print(f"[bold]ATTEMPT COMMAND: [/bold][yellow]{command}[/yellow]")
                    if command == "TEXT":
                        ai_to_commands.text(out1, out2, out3)
                    elif command == "ASK":
                        user_input = ""
                        while not user_input:
                            user_input = ai_to_commands.ask(out1, out2, out3)
                        user_response = user_input
                    elif command == "READONL":
                        result = ai_to_commands.readonl(github, out1, out2, out3)
                        user_response = f"File contents:\n{result}"
                    elif command == "REPOSTRUCTONL":
                        result = ai_to_commands.repostructonl(github, out1, out2, out3)
                        user_response = f"Repo structure:\n{result}"
                    elif command == "REPOLIST":
                        result = ai_to_commands.repolist(github)
                        user_response = f"Available repos:\n{result}"
                    elif command == "READLOC":
                        result = ai_to_commands.readloc(out1, out2, out3)
                        user_response = f"File contents:\n{result}"
                    elif command == "STRUCTLOC":
                        result = ai_to_commands.structloc(out1, out2, out3)
                        user_response = f"Directory structure:\n{result}"
                    elif command == "RUNCOMMAND":
                        output, ran = ai_to_commands.runcommand(out1, out2, out3, autorun=rules.get("autorun"))
                        user_response = f"Command output:\n{output}" if ran else "User denied the command."
                    elif command == "AUTHGH":
                        output = ai_to_commands.authgh(out1, out2, out3)
                        user_response = f"Command output:\n{output}"
                    elif command == "STATUS":
                        output = ai_to_commands.status(out1, out2, out3)
                        user_response = f"Command output:\n{output}"
                    elif command == "DIFF":
                        output = ai_to_commands.diff(out1, out2, out3)
                        user_response = f"Command output:\n{output}"
                    elif command == "SETTINGS":
                        ai_to_commands.settings(out1, out2, out3)
                        rules = init.get_settings()
                        if default_dir:
                            user_response = f"User updated their settings, default GitHub directory is now {default_dir} ask them what they want to do next."
                        else: 
                            user_response = f"User updated their settings, ask them what they want to do next."
                    elif command == "EXIT":
                        exit = True
                        break
                    else:
                        console.print(f"[yellow]Unhandled command: {command}[/yellow]")
                        exit = True
                        break
            except (ValueError, GithubException) as e:
                parse_failed = True
                response = send_with_retry(chat, f"Command failed: {e}. Please try again.")
                break

        if exit or not parse_failed:
            break

        if attempt < MAX_RETRIES - 1:
            response = send_with_retry(chat,
                "Your response was not formatted correctly. Please respond using only valid commands: TEXT, ASK, READONL, REPOSTRUCTONL, REPOLIST, READLOC, WRITELOC, STRUCTLOC, RUNCOMMAND, AUTHGH, STATUS, or DIFF."
            )
        else:
            console.print(f"[red]Failed to get a valid response after {MAX_RETRIES} attempts. Exiting.[/red]")
            exit = True

    if exit:
        break
    
    if user_response:
        user_response = user_response.replace(access_token, "[REDACTED]user access token[REDACTED]")
        if rules.get("debug"):
                console.print(f"[bold]SEND -> [/bold][magenta]{user_response}[/magenta]")
    response = send_with_retry(chat, user_response if user_response is not None else "Done")