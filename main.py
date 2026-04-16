import os
import re
import time
import threading
import subprocess
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
autocommit_interval = 30 #default to 30 minutes

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
            elif e.code == 500:
                console.print(f"[red]Internal server error, exiting...[/red]")
                os._exit(1)
            else:
                raise


for required_file in ["auth.dat", "api.dat", "prompt.txt", "autocommitprompt.txt"]:
    if not Path(required_file).is_file():
        console.print(f"[red]Missing required file: {required_file}[/red]")
        os._exit(1)

login_details = Path("auth.dat")
gemini_api = Path("api.dat")
access_token = login_details.read_text().strip()
key = gemini_api.read_text().strip()

github = init.attempt_login(access_token)
gemini = genai.Client(api_key=key)

prompt = Path("prompt.txt").read_text()
autocommit_prompt = Path("autocommitprompt.txt").read_text()
default_dir = rules.get("defaultgithubdir")
autocommit_loc = ""
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

stop_event = threading.Event()

writeloc_pattern = re.compile(
    r'WRITELOC:[^\n]*file="((?:[^"\\]|\\.)*)"[^\n]*reason="((?:[^"\\]|\\.)*)"[^\n]*\n<FILE>\n(.*?)\n</FILE>',
    re.DOTALL
)

def main_loop():
    global autocommit_loc, rules
    response = send_with_retry(chat, "Start")
    MAX_RETRIES = 5

    while True:
        parse_failed = False

        for attempt in range(MAX_RETRIES):
            parse_failed = False
            user_response_parts = []

            writeloc_blocks = []
            def _extract(m):
                writeloc_blocks.append((m.group(1), m.group(2), m.group(3)))
                return '__WRITELOC__'
            processed_text = writeloc_pattern.sub(_extract, response.text.strip())

            writeloc_idx = 0
            lines = [s for l in processed_text.split('\n') if (s := l.strip())]

            for line in lines:
                if rules.get("autocommit") and not autocommit_loc:
                    is_loc = False
                    while not is_loc:
                        autocommit_loc = console.input("[yellow]Please provide a working directory for your current project to enable autocommit features, or type \"[bold]Ignore[/bold]\" to not enable it for this instance:[/yellow] ").strip()
                        if autocommit_loc.lower() in ["ignore", "i"]:
                            console.print("[yellow]Autocommit will not be enabled for this instance.[/yellow]\n")
                            break
                        is_loc = Path(autocommit_loc.strip()).is_dir()
                        if not is_loc:
                            console.print("[red]Provided directory is not valid, please try again.[/red]\n")
                    if not autocommit_loc.lower() in ["i", "ignore"]:
                        console.print(f"[green]Autocommit enabled for {autocommit_loc}[/green]\n")
                if rules.get("debug"):
                    console.print(f"[bold]RECEIVED <- [/bold][orange]{line}[/orange]")
                try:
                    if line == '__WRITELOC__':
                        if rules.get("debug"):
                            console.print("[bold]ATTEMPT COMMAND: [/bold][yellow]__WRITELOC__[/yellow]")
                        if writeloc_idx >= len(writeloc_blocks):
                            user_response_parts.append("Error: mismatched WRITELOC blocks in response.")
                            parse_failed = True
                            break
                        file_path, reason, content = writeloc_blocks[writeloc_idx]
                        writeloc_idx += 1
                        wrote = ai_to_commands.writeloc_direct(file_path, content, reason, autowrite=rules.get("autowrite"))
                        user_response_parts.append("File written successfully." if wrote else "User denied the file write.")
                    else:
                        command, out1, out2, out3 = ai_to_commands.interpret(line)
                        if rules.get("debug"):
                            console.print(f"[bold]ATTEMPT COMMAND: [/bold][yellow]{command}[/yellow]")
                        if command == "TEXT":
                            ai_to_commands.text(out1, out2, out3)
                        elif command == "ASK":
                            user_input = ""
                            user_input = ai_to_commands.ask(out1, out2, out3)
                            if user_input.lower()[12:] in ["exit", "quit", "close", "end", "stop", "exit.", "quit.", "close.", "end.", "stop.",]:
                                console.print("[yellow]Thank you for using Gitpanion, have a great day![/yellow]")
                                os._exit(0)
                            user_response_parts.append(user_input)
                        elif command == "READONL":
                            result = ai_to_commands.readonl(github, out1, out2, out3)
                            user_response_parts.append(f"File contents:\n{result}")
                        elif command == "REPOSTRUCTONL":
                            result = ai_to_commands.repostructonl(github, out1, out2, out3)
                            user_response_parts.append(f"Repo structure:\n{result}")
                        elif command == "REPOLIST":
                            result = ai_to_commands.repolist(github)
                            user_response_parts.append(f"Available repos:\n{result}")
                        elif command == "READLOC":
                            result = ai_to_commands.readloc(out1, out2, out3)
                            user_response_parts.append(f"File contents:\n{result}")
                        elif command == "STRUCTLOC":
                            result = ai_to_commands.structloc(out1, out2, out3)
                            user_response_parts.append(f"Directory structure:\n{result}")
                        elif command == "RUNCOMMAND":
                            output, ran = ai_to_commands.runcommand(out1, out2, out3, autorun=rules.get("autorun"))
                            user_response_parts.append(f"Command output:\n{output}" if ran else "User denied the command.")
                        elif command == "AUTHGH":
                            output = ai_to_commands.authgh(out1, out2, out3)
                            user_response_parts.append(f"Command output:\n{output}")
                        elif command == "STATUS":
                            output = ai_to_commands.status(out1, out2, out3)
                            user_response_parts.append(f"Command output:\n{output}")
                        elif command == "DIFF":
                            output = ai_to_commands.diff(out1, out2, out3)
                            user_response_parts.append(f"Command output:\n{output}")
                        elif command == "UPDATEAUTOCOMMITDIR":
                            output = ai_to_commands.update_autocommit_dir(out1, out2, out3)
                            autocommit_loc = output
                            user_response_parts.append(f"Autocommit directory updated to {autocommit_loc}")
                        elif command == "OPENPAGE":
                            output = ai_to_commands.openpage(github, out1, out2, out3)
                            user_response_parts.append(output)
                        elif command == "GHNAME":
                            output = ai_to_commands.ghname(github, out1, out2, out3)
                            user_response_parts.append(f"GitHub username: {output}")
                        elif command == "CURRPROJ":
                            user_response_parts.append(f"Current GitHub project:\n{autocommit_loc}" if autocommit_loc else "No current GitHub project detected.")
                        elif command == "SETTINGS":
                            ai_to_commands.settings(out1, out2, out3)
                            rules = init.get_settings()
                            if default_dir:
                                user_response_parts.append(f"User updated their settings, default GitHub directory is now {default_dir} ask them what they want to do next.")
                            else:
                                user_response_parts.append(f"User updated their settings, ask them what they want to do next.")
                        else:
                            console.print(f"[yellow]Unhandled command: {command}[/yellow]")
                            os._exit(1)
                except (ValueError, GithubException) as e:
                    parse_failed = True
                    prior_results = "\n".join(user_response_parts)
                    error_msg = f"Command failed: {e}. Please try again."
                    if prior_results:
                        error_msg = f"{prior_results}\n{error_msg}"
                    response = send_with_retry(chat, error_msg)
                    break

            if not parse_failed:
                break

            if attempt < MAX_RETRIES - 1:
                response = send_with_retry(chat,
                    "Your response was not formatted correctly. Please respond using only valid commands: TEXT, ASK, READONL, REPOSTRUCTONL, REPOLIST, READLOC, WRITELOC, STRUCTLOC, RUNCOMMAND, AUTHGH, STATUS, or DIFF."
                )
            else:
                console.print(f"[red]Failed to get a valid response after {MAX_RETRIES} attempts. Exiting.[/red]")
                os._exit(1)


        user_response = "\n".join(user_response_parts) if user_response_parts else None
        if user_response:
            user_response = user_response.replace(access_token, "[REDACTED]user access token[REDACTED]")
            if rules.get("debug"):
                console.print(f"[bold]SEND -> [/bold][magenta]{user_response}[/magenta]")
        response = send_with_retry(chat, user_response if user_response is not None else "Done")



def autocommit():
    while True:
        time.sleep(60 * autocommit_interval) #default is 30 minutes
        loc = autocommit_loc.strip()
        if rules.get("autocommit") and loc and Path(loc).is_dir():
            autocommit_chat = gemini.chats.create(
                model=model,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                    system_instruction=autocommit_prompt
                )
            )
            diff = subprocess.run(["git", "-C", loc, "diff", "HEAD"], capture_output=True, text=True).stdout
            output = send_with_retry(autocommit_chat, f"The following is the Git diff:\n{diff}\n\n. To approve, respond \"YES\" followed by the commit message, otherwise respond with \"no\" followed by the reason why you aren't commiting.").text
            if rules.get("debug"):
                console.print(f"[red]Autocommit output[/red]: {output}")
            if output.strip().lower().startswith("yes"):
                commit_message = output.strip()[4:].strip()
                subprocess.run(["git", "-C", loc, "add", "."])
                subprocess.run(["git", "-C", loc, "commit", "-m", commit_message])
                console.print(f"[green]Autocommit successful with message:[/green] [bold]{commit_message}[/bold]")
            else:
                console.print("[yellow]Autocommit skipped.[/yellow]")


autocommit_thread = threading.Thread(target=autocommit, name="autocommit", daemon=True)


main_thread = threading.Thread(target=main_loop, name="main-loop", daemon=True)
main_thread.start()
autocommit_thread.start()
autocommit_thread.join()
main_thread.join()