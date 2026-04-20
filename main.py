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
autocommit_interval = 15 #default to 15 minutes
def debug_out(msg):
    if rules.get("debug"):
        try:
            console.print(f"[red][bold][DEBUG]: [/bold][/red][yellow]{msg}[/yellow]")
        except Exception: #fallback specifically if there is text in output that would cause rich console to raise an exception, such as [/bold] in a file without a preceeding [bold]
            print(f"[DEBUG]: {msg}")
            console.print("\n\n[red][bold][DEBUG]: [/bold][/red][yellow][italic]Fallback print statement used -- check files that Gitpanion is reading for rich markup errors![/italic][/yellow]\n\n")


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
autocommitsi = Path("autocommitsi.txt").read_text() if Path("autocommitsi.txt").is_file() else "nosi"
autocommit_prompt = Path("autocommitprompt.txt").read_text() if Path("autocommitprompt.txt").is_file() else "noprompt"

if autocommit_prompt == "noprompt":
    raise FileNotFoundError("Missing autocommitprompt.txt, which is required for autcommit features. Please create this file with the appropriate system instruction for autocommits.")
if autocommitsi == "nosi":
    raise FileNotFoundError("Missing autocommitsi.txt, which is required for autocommit features. Please create this file with the appropriate system instruction for autocommits.")

default_dir = rules.get("defaultgithubdir")
autocommit_loc = ""
system_instruction = prompt + f"\n\nUser's default GitHub directory:\"{default_dir}\"" if default_dir else prompt

debug_out(f"Settings: {rules}")
debug_out(f"System Instruction: {system_instruction}")


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
                debug_out(f"RECEIVED <- {line}")
                try:
                    if line == '__WRITELOC__':
                        debug_out(f"ATTEMPT COMMAND: __WRITELOC__")
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
                        debug_out(f"ATTEMPT COMMAND: {command}")
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
                        elif command == "DELETE":
                            output, deleted = ai_to_commands.delete(out1, out2, out3)
                            user_response_parts.append(f"{output}")
                        elif command == "THINK":
                            output = ai_to_commands.think(out1, out2, out3)
                            user_response_parts.append(f"Thought: {output}")
                            debug_out(f"AI Thought: {output}")
                        elif command == "CURRPROJ":
                            user_response_parts.append(f"Current GitHub project:\n{autocommit_loc}" if autocommit_loc else "No current GitHub project detected.")
                        elif command == "CURRENTDIR":
                            output = ai_to_commands.currentdir()
                            user_response_parts.append(f"Current working directory: {output}")
                        elif command == "NEWBRANCH":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output = ai_to_commands.newbranch(autocommit_loc, out1, out2, out3)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "LISTBRANCHES":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output = ai_to_commands.listbranches(autocommit_loc)
                                user_response_parts.append(f"Branches:\n{output}")
                        elif command == "SWITCHBRANCH":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output = ai_to_commands.switchbranch(autocommit_loc, out1, out2, out3)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "MERGE":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output = ai_to_commands.merge(autocommit_loc, out1, out2, out3)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "PR":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output = ai_to_commands.pr(autocommit_loc, out1, out2, out3)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "SETTINGS":
                            ai_to_commands.settings(out1, out2, out3)
                            rules = init.get_settings()
                            new_default_dir = rules.get("defaultgithubdir")
                            if new_default_dir:
                                user_response_parts.append(f"User updated their settings, default GitHub directory is now {new_default_dir} ask them what they want to do next.")
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
                    "Your response was not formatted correctly. Please respond using only valid commands: TEXT, ASK, READONL, REPOSTRUCTONL, REPOLIST, READLOC, WRITELOC, STRUCTLOC, RUNCOMMAND, AUTHGH, STATUS, DIFF, DELETE, SETTINGS, OPENPAGE, GHNAME, CURRPROJ, UPDATEAUTOCOMMITDIR, THINK, CURRENTDIR, NEWBRANCH, LISTBRANCHES, SWITCHBRANCH, MERGE, or PR."
                )
            else:
                console.print(f"[red]Failed to get a valid response after {MAX_RETRIES} attempts. Exiting.[/red]")
                os._exit(1)


        user_response = "\n".join(user_response_parts) if user_response_parts else None
        if user_response:
            user_response = user_response.replace(access_token, "[REDACTED]user access token[REDACTED]").replace(key, "[REDACTED]gemini api key[REDACTED]")
            debug_out(f"SEND -> {user_response}")
        response = send_with_retry(chat, user_response if user_response is not None else "Done")



def autocommit():
    avert = False #avert the 15 minute cooldown should the AI want to wait a minute to avoid committing mid-edit, will reset after one loop so it doesn't cause issues if they want to wait multiple times in a row
    autocommit_shas = [] # track consecutive autocommit SHAs (for amend/squash eligibility)
    while True:
        if not avert:
            time.sleep(60 * autocommit_interval) #default is 15 minutes
        avert = False
        loc = autocommit_loc.strip()
        if rules.get("autocommit") and loc and Path(loc).is_dir():
            autocommit_chat = gemini.chats.create(
                model=model,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                    system_instruction=autocommitsi
                )
            )
            diff = subprocess.run(["git", "-C", loc, "diff", "HEAD"], capture_output=True, text=True).stdout
            last_commit_msg = subprocess.run(["git", "-C", loc, "log", "-1", "--format=%s"], capture_output=True, text=True).stdout.strip()
            current_head = subprocess.run(["git", "-C", loc, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

            # Validate tracked SHAs are still in git history (user may have rebased/reset)
            if autocommit_shas:
                history = subprocess.run(
                    ["git", "-C", loc, "log", "--format=%H", f"-{len(autocommit_shas) + 5}"],
                    capture_output=True, text=True
                ).stdout.strip().split()
                autocommit_shas = [sha for sha in autocommit_shas if sha in history]

            can_amend = bool(autocommit_shas) and current_head == autocommit_shas[-1]
            can_squash = len(autocommit_shas) >= 2 and current_head == autocommit_shas[-1]

            context = (
                f"The following is the Git diff:\n{diff}\n\n"
                f"Last commit message: {last_commit_msg}\n"
                f"Recent autocommit count: {len(autocommit_shas)}"
            )
            output = send_with_retry(autocommit_chat, f"{context}\n\n{autocommit_prompt}").text
            debug_out(f"Autocommit output: {output}")

            stripped = output.strip()
            lower = stripped.lower()
            parts = stripped.split(None, 1)
            commit_message = parts[1].strip() if len(parts) > 1 else ""

            if lower.startswith("yes"):
                if commit_message:
                    add_result = subprocess.run(["git", "-C", loc, "add", "."])
                    if add_result.returncode != 0:
                        console.print(f"[red]Autocommit failed: git add failed[/red]")
                        continue
                    result = subprocess.run(["git", "-C", loc, "commit", "-m", commit_message])
                    if result.returncode == 0:
                        new_sha = subprocess.run(["git", "-C", loc, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                        autocommit_shas.append(new_sha)
                        console.print(f"[green]Autocommit successful with message:[/green] [bold]{commit_message}[/bold]")
                    else:
                        console.print(f"[red]Autocommit failed[/red]")

            elif lower.startswith("amend"):
                if can_amend and commit_message:
                    add_result = subprocess.run(["git", "-C", loc, "add", "."])
                    if add_result.returncode != 0:
                        console.print(f"[red]Autocommit amend failed: git add failed[/red]")
                        continue
                    result = subprocess.run(["git", "-C", loc, "commit", "--amend", "-m", commit_message])
                    if result.returncode == 0:
                        new_sha = subprocess.run(["git", "-C", loc, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                        autocommit_shas[-1] = new_sha
                        console.print(f"[green]Autocommit amended with message:[/green] [bold]{commit_message}[/bold]")
                    else:
                        console.print(f"[red]Autocommit amend failed[/red]")
                elif commit_message:
                    # Amend not eligible (last commit wasn't an autocommit), fall back to new commit
                    debug_out("Amend requested but not eligible, falling back to new commit")
                    add_result = subprocess.run(["git", "-C", loc, "add", "."])
                    if add_result.returncode != 0:
                        console.print(f"[red]Autocommit failed: git add failed[/red]")
                        continue
                    result = subprocess.run(["git", "-C", loc, "commit", "-m", commit_message])
                    if result.returncode == 0:
                        new_sha = subprocess.run(["git", "-C", loc, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                        autocommit_shas.append(new_sha)
                        console.print(f"[green]Autocommit successful with message:[/green] [bold]{commit_message}[/bold]")

            elif lower.startswith("squash"):
                if can_squash and commit_message:
                    n = len(autocommit_shas)
                    add_result = subprocess.run(["git", "-C", loc, "add", "."])
                    if add_result.returncode != 0:
                        console.print(f"[red]Autocommit squash failed: git add failed[/red]")
                        continue
                    reset_result = subprocess.run(["git", "-C", loc, "reset", "--soft", f"HEAD~{n}"])
                    if reset_result.returncode != 0:
                        console.print(f"[red]Autocommit squash failed: git reset failed[/red]")
                        continue
                    result = subprocess.run(["git", "-C", loc, "commit", "-m", commit_message])
                    if result.returncode == 0:
                        new_sha = subprocess.run(["git", "-C", loc, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                        autocommit_shas = [new_sha]
                        console.print(f"[green]Autocommit squashed {n} commits with message:[/green] [bold]{commit_message}[/bold]")
                    else:
                        console.print(f"[red]Autocommit squash failed[/red]")
                elif commit_message:
                    # Squash not eligible (fewer than 2 autocommits), fall back to new commit
                    debug_out("Squash requested but not eligible, falling back to new commit")
                    add_result = subprocess.run(["git", "-C", loc, "add", "."])
                    if add_result.returncode != 0:
                        console.print(f"[red]Autocommit failed: git add failed[/red]")
                        continue
                    result = subprocess.run(["git", "-C", loc, "commit", "-m", commit_message])
                    if result.returncode == 0:
                        new_sha = subprocess.run(["git", "-C", loc, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                        autocommit_shas.append(new_sha)
                        console.print(f"[green]Autocommit successful with message:[/green] [bold]{commit_message}[/bold]")

            elif lower.startswith("wait"):
                time.sleep(60) #wait a minute and then check again
                avert = True
                debug_out("Autocommit delayed")
            else:
                debug_out("Autocommit denied")

autocommit_thread = threading.Thread(target=autocommit, name="autocommit", daemon=True)


main_thread = threading.Thread(target=main_loop, name="main-loop", daemon=True)
main_thread.start()
autocommit_thread.start()
autocommit_thread.join()
main_thread.join()