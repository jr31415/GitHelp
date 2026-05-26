import os
import re
import time
import threading
import subprocess
import concurrent.futures
import init
import ai_to_commands
from console_proxy import ConsoleProxy
import console_proxy
from github import GithubException
from pathlib import Path
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
console = ConsoleProxy()

model = "gemini-3-flash-preview"
autocommit_interval = 15

# Globals populated by run() before threads start
rules = {}
autocommit_loc = ""
chat = None
github = None
gemini = None
access_token = ""
key = ""
autocommitsi = ""
autocommit_prompt = ""

tasks = []

def _debug_out(msg: str) -> None: #will only print to console if debug mode is on
    if rules.get("debug"):
        try:
            console.print(f"[red][bold][DEBUG]: [/bold][/red][yellow]{msg}[/yellow]")
        except Exception: #fallback specifically if there is text in output that would cause rich console to raise an exception, such as [/bold] in a file without a preceeding [bold]
            print(f"[DEBUG]: {msg}")
            console.print("\n\n[red][bold][DEBUG]: [/bold][/red][yellow][italic]Fallback print statement used -- check files that Gitpanion is reading for rich markup errors![/italic][/yellow]\n\n")


def __send_with_retry(chat, message, max_retries=10): #handles rate limiting and server errors
    """Retry on 429/500 API errors with exponential backoff. Pass max_retries=None to retry indefinitely (used during THINK loops so the model isn't killed by a transient rate limit)."""
    delay = 5
    attempt = 0
    console_proxy.show_thinking()
    try:
        while max_retries is None or attempt < max_retries:
            try:
                return chat.send_message(message)
            except genai_errors.APIError as e:
                if e.code == 429 and (max_retries is None or attempt < max_retries - 1):
                    console.print(f"[yellow]Rate limited, retrying in {delay}s...[/yellow]")
                    time.sleep(delay)
                    delay *= 2
                elif e.code == 500:
                    console.print(f"[red]Internal server error, exiting...[/red]")
                    os._exit(1)
                else:
                    raise
            attempt += 1
    finally:
        console_proxy.hide_thinking()



writeloc_pattern = re.compile(
    r'WRITELOC:[^\n]*file="((?:[^"\\]|\\.)*)"[^\n]*reason="((?:[^"\\]|\\.)*)"[^\n]*\n<FILE>\n(.*?)\n</FILE>',
    re.DOTALL
)

def _main_loop():
    global autocommit_loc, rules
    response = __send_with_retry(chat, "Start")
    MAX_RETRIES = 5

    while True:
        parse_failed = False

        for attempt in range(MAX_RETRIES):
            parse_failed = False
            only_thinking = True
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
                _debug_out(f"RECEIVED <- {line}")
                try:
                    if line == '__WRITELOC__':
                        _debug_out(f"ATTEMPT COMMAND: __WRITELOC__")
                        if writeloc_idx >= len(writeloc_blocks):
                            user_response_parts.append("Error: mismatched WRITELOC blocks in response.")
                            parse_failed = True
                            break
                        file_path, reason, content = writeloc_blocks[writeloc_idx]
                        writeloc_idx += 1
                        task = ai_to_commands.writeloc_direct(file_path, content, reason, autowrite=rules.get("write without confirmation"))
                        tasks.append(task)
                        user_response_parts.append("File written successfully." if task.excecuted else "User denied the file write.")
                    else:
                        command, out1, out2, out3 = ai_to_commands.interpret(line)
                        _debug_out(f"ATTEMPT COMMAND: {command}")
                        if command != "THINK":
                            only_thinking = False
                        if command == "TEXT":
                            ai_to_commands.text(out1, out2, out3)
                        elif command == "ASK":
                            user_input = ""
                            user_input = ai_to_commands.ask(out1, out2, out3)
                            if user_input.lower()[12:] in ["exit", "quit", "close", "end", "stop", "exit.", "quit.", "close.", "end.", "stop.",]:
                                console.print("[yellow]Thank you for using Gitpanion, have a great day![/yellow]")
                                console_proxy.exit_app(0)
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
                            output, task = ai_to_commands.runcommand(out1, out2, out3, autorun=rules.get("run without confirmation"))
                            tasks.append(task)
                            user_response_parts.append(f"Command output:\n{output}" if task.excecuted == True else "User denied the command.")
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
                            output, task = ai_to_commands.delete(out1, out2, out3)
                            tasks.append(task)
                            user_response_parts.append(f"{output}")
                        elif command == "THINK":
                            output = ai_to_commands.think(out1, out2, out3)
                            user_response_parts.append(f"Thought: {output}")
                            _debug_out(f"AI Thought: {output}")
                        elif command == "CURRPROJ":
                            user_response_parts.append(f"Current GitHub project:\n{autocommit_loc}" if autocommit_loc else "No current GitHub project detected.")
                        elif command == "CURRENTDIR":
                            output = ai_to_commands.currentdir()
                            user_response_parts.append(f"Current working directory: {output}")
                        elif command == "NEWBRANCH":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output, task = ai_to_commands.newbranch(autocommit_loc, out1, out2, out3)
                                tasks.append(task)
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
                                output, task = ai_to_commands.switchbranch(autocommit_loc, out1, out2, out3)
                                tasks.append(task)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "MERGE":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output, task = ai_to_commands.merge(autocommit_loc, out1, out2, out3)
                                tasks.append(task)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "REBASE":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output, task = ai_to_commands.rebase(autocommit_loc, out1, out2, out3)
                                tasks.append(task)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "ADD":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output, task = ai_to_commands.add(autocommit_loc, out1, out2, out3)
                                tasks.append(task)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "COMMIT":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output, task = ai_to_commands.commit(autocommit_loc, out1, out2, out3)
                                tasks.append(task)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "PUSH":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output, task = ai_to_commands.push(autocommit_loc, out1, out2, out3, autopush=rules.get("push without confirmation"))
                                tasks.append(task)
                                user_response_parts.append(f"Command output:\n{output}" if output is not None else "User denied the push.")
                        elif command == "PR":
                            if not autocommit_loc:
                                user_response_parts.append("No current project set. Please activate a project first.")
                            else:
                                output, task = ai_to_commands.pr(autocommit_loc, out1, out2, out3)
                                tasks.append(task)
                                user_response_parts.append(f"Command output:\n{output}")
                        elif command == "SETTINGS":
                            ai_to_commands.settings(out1, out2, out3)
                            rules = init.get_settings()
                            new_default_dir = rules.get("defaultgithubdir")
                            if new_default_dir:
                                user_response_parts.append(f"User updated their settings, default GitHub directory is now {new_default_dir} ask them what they want to do next.")
                            else:
                                user_response_parts.append(f"User updated their settings, ask them what they want to do next.")
                        elif command == "TASKS":
                            ai_to_commands.tasks(tasks)

                        else:
                            console.print(f"[yellow]Unhandled command: {command}[/yellow]")
                            os._exit(1)
                except (ValueError, GithubException) as e:
                    parse_failed = True
                    prior_results = "\n".join(user_response_parts)
                    error_msg = f"Command failed: {e}. Please try again."
                    if prior_results:
                        error_msg = f"{prior_results}\n{error_msg}"
                    response = _send_with_retry(chat, error_msg)
                    break

            if not parse_failed:
                break

            if attempt < MAX_RETRIES - 1:
                response = _send_with_retry(chat,
                    "Your response was not formatted correctly. Please respond using only valid commands: TEXT, ASK, READONL, REPOSTRUCTONL, REPOLIST, READLOC, WRITELOC, STRUCTLOC, RUNCOMMAND, AUTHGH, STATUS, DIFF, DELETE, SETTINGS, OPENPAGE, GHNAME, CURRPROJ, UPDATEAUTOCOMMITDIR, THINK, CURRENTDIR, NEWBRANCH, LISTBRANCHES, SWITCHBRANCH, MERGE, PR, PUSH, COMMIT, REBASE, or ADD."
                )
            else:
                console.print(f"[red]Failed to get a valid response after {MAX_RETRIES} attempts. Exiting.[/red]")
                os._exit(1)


        user_response = "\n".join(user_response_parts) if user_response_parts else None
        if user_response:
            user_response = user_response.replace(access_token, "[REDACTED]user access token[REDACTED]").replace(key, "[REDACTED]gemini api key[REDACTED]")
            _debug_out(f"SEND -> {user_response}")
        response = _send_with_retry(chat, user_response if user_response is not None else "Done", max_retries=None if only_thinking else 5)



def _autocommit():
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
            def _git(*args):
                return subprocess.run(["git", "-C", loc] + list(args), capture_output=True, text=True)

            with concurrent.futures.ThreadPoolExecutor() as executor:
                f_diff = executor.submit(_git, "diff", "HEAD")
                f_log = executor.submit(_git, "log", "-1", "--format=%s")
                f_head = executor.submit(_git, "rev-parse", "HEAD")
                f_remote = executor.submit(_git, "rev-parse", "--verify", "@{u}")
                f_history = executor.submit(_git, "log", "--format=%H", f"-{len(autocommit_shas) + 5}") if autocommit_shas else None

            diff = f_diff.result().stdout
            last_commit_msg = f_log.result().stdout.strip()
            current_head = f_head.result().stdout.strip()
            remote_check = f_remote.result()

            # Validate tracked SHAs are still in git history (user may have rebased/reset)
            if autocommit_shas and f_history:
                history = f_history.result().stdout.strip().split()
                autocommit_shas = [sha for sha in autocommit_shas if sha in history]

            if remote_check.returncode == 0:
                unpushed = set(_git("log", "--format=%H", "@{u}..HEAD").stdout.strip().split())
            else:
                unpushed = set(autocommit_shas)

            can_amend = bool(autocommit_shas) and current_head == autocommit_shas[-1] and autocommit_shas[-1] in unpushed
            can_squash = len(autocommit_shas) >= 2 and current_head == autocommit_shas[-1] and all(sha in unpushed for sha in autocommit_shas)

            context = (
                f"The following is the Git diff:\n{diff}\n\n"
                f"Last commit message: {last_commit_msg}\n"
                f"Recent autocommit count: {len(autocommit_shas)}"
            )
            output = _send_with_retry(autocommit_chat, f"{context}\n\n{autocommit_prompt}").text
            _debug_out(f"Autocommit output: {output}")

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
                        tasks.append(ai_to_commands.TaskObject("c", f"git commit -m {commit_message}", True))
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
                        tasks.append(ai_to_commands.TaskObject("c", f"git commit --amend -m {commit_message}", True))
                        console.print(f"[green]Autocommit amended with message:[/green] [bold]{commit_message}[/bold]")
                    else:
                        console.print(f"[red]Autocommit amend failed[/red]")
                elif commit_message:
                    # Amend not eligible (last commit wasn't an autocommit), fall back to new commit
                    _debug_out("Amend requested but not eligible, falling back to new commit")
                    add_result = subprocess.run(["git", "-C", loc, "add", "."])
                    if add_result.returncode != 0:
                        console.print(f"[red]Autocommit failed: git add failed[/red]")
                        continue
                    result = subprocess.run(["git", "-C", loc, "commit", "-m", commit_message])
                    if result.returncode == 0:
                        new_sha = subprocess.run(["git", "-C", loc, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                        autocommit_shas.append(new_sha)
                        tasks.append(ai_to_commands.TaskObject("c", f"git commit -m {commit_message}", True))
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
                        tasks.append(ai_to_commands.TaskObject("c", f"git commit (squash {n}) -m {commit_message}", True))
                        console.print(f"[green]Autocommit squashed {n} commits with message:[/green] [bold]{commit_message}[/bold]")
                    else:
                        console.print(f"[red]Autocommit squash failed[/red]")
                elif commit_message:
                    # Squash not eligible (fewer than 2 autocommits), fall back to new commit
                    _debug_out("Squash requested but not eligible, falling back to new commit")
                    add_result = subprocess.run(["git", "-C", loc, "add", "."])
                    if add_result.returncode != 0:
                        console.print(f"[red]Autocommit failed: git add failed[/red]")
                        continue
                    result = subprocess.run(["git", "-C", loc, "commit", "-m", commit_message])
                    if result.returncode == 0:
                        new_sha = subprocess.run(["git", "-C", loc, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                        autocommit_shas.append(new_sha)
                        tasks.append(ai_to_commands.TaskObject("c", f"git commit -m {commit_message}", True))
                        console.print(f"[green]Autocommit successful with message:[/green] [bold]{commit_message}[/bold]")

            elif lower.startswith("wait"):
                time.sleep(60) #wait a minute and then check again
                avert = True
                _debug_out("Autocommit delayed")
            else:
                _debug_out("Autocommit denied")

def run() -> None:
    global rules, chat, github, gemini, access_token, key, autocommitsi, autocommit_prompt

    init.run()
    rules = init.get_settings()

    for required_file in ["auth.dat", "api.dat", "prompt.txt", "autocommitprompt.txt"]:
        if not Path(required_file).is_file():
            console.print(f"[red]Missing required file: {required_file}[/red]")
            os._exit(1)

    login_details = Path("auth.dat")
    gemini_api_file = Path("api.dat")
    access_token = login_details.read_text().strip()
    key = gemini_api_file.read_text().strip()
    os.environ["GH_TOKEN"] = access_token

    github = init.attempt_login(access_token)
    gemini = genai.Client(api_key=key)

    prompt = Path("prompt.txt").read_text()
    autocommitsi = Path("autocommitsi.txt").read_text() if Path("autocommitsi.txt").is_file() else "nosi"
    autocommit_prompt = Path("autocommitprompt.txt").read_text() if Path("autocommitprompt.txt").is_file() else "noprompt"

    if autocommit_prompt == "noprompt":
        raise FileNotFoundError("Missing autocommitprompt.txt, which is required for autocommit features.")
    if autocommitsi == "nosi":
        raise FileNotFoundError("Missing autocommitsi.txt, which is required for autocommit features.")

    default_dir = rules.get("defaultgithubdir")
    system_instruction = prompt + f"\n\nUser's default GitHub directory:\"{default_dir}\"" if default_dir else prompt

    _debug_out(f"Settings: {rules}")
    _debug_out(f"System Instruction: {system_instruction}")

    chat = gemini.chats.create(
        model=model,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            system_instruction=system_instruction
        )
    )

    autocommit_thread = threading.Thread(target=_autocommit, name="autocommit", daemon=True)
    main_thread = threading.Thread(target=_main_loop, name="main-loop", daemon=True)
    main_thread.start()
    autocommit_thread.start()
    autocommit_thread.join()
    main_thread.join()


if __name__ == "__main__":
    run()