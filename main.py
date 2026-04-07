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


login_details = Path("auth.dat")
gemini_api = Path("api.dat")
access_token = login_details.read_text().strip()
key = gemini_api.read_text().strip()

github = init.attempt_login(access_token)
gemini = genai.Client(api_key=key)

chat = gemini.chats.create(
    model=model,
    
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low"),
        system_instruction=Path("prompt.txt").read_text()
    )
)

response = chat.send_message("Start")

MAX_RETRIES = 5

exit = False
while not exit:
    user_response = None
    parse_failed = False

    for attempt in range(MAX_RETRIES):
        parse_failed = False
        lines = [l.strip() for l in response.text.strip().split('\n') if l.strip()]
        

        for line in lines:    
            try:
                command, out1, out2, out3 = ai_to_commands.interpret(line)
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
                elif command == "WRITELOC":
                    wrote = ai_to_commands.writeloc(out1, out2, out3)
                    user_response = "File written successfully." if wrote else "User denied the file write."
                elif command == "STRUCTLOC":
                    result = ai_to_commands.structloc(out1, out2, out3)
                    user_response = f"Directory structure:\n{result}"
                elif command == "RUNCOMMAND":
                    output, ran = ai_to_commands.runcommand(out1, out2, out3)
                    user_response = f"Command output:\n{output}" if ran else "User denied the command."
                elif command == "EXIT":
                    exit = True
                    break
                else:
                    console.print(f"[yellow]Unhandled command: {command}[/yellow]")
                    exit = True
                    break
            except (ValueError, GithubException) as e:
                parse_failed = True
                response = chat.send_message(f"Command failed: {e}. Please try again.")
                break

        if exit or not parse_failed:
            break

        if attempt < MAX_RETRIES - 1:
            response = chat.send_message(
                "Your response was not formatted correctly. Please respond using only valid commands: TEXT, ASK, READONL, REPOSTRUCTONL, REPOLIST, READLOC, WRITELOC, STRUCTLOC, or RUNCOMMAND."
            )
        else:
            console.print(f"[red]Failed to get a valid response after {MAX_RETRIES} attempts. Exiting.[/red]")
            exit = True

    if exit:
        break

    response = chat.send_message(user_response if user_response is not None else "Done")

