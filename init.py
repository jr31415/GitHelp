from rich.console import Console
from github import Github, GithubException
from github import Auth
from pathlib import Path
from google import genai
from google.genai import errors as genai_errors
console = Console()

access_token = ""
login_details = Path("auth.dat")
gemini_api = Path("api.dat")

console.print("[green]Welcome to[/green] [bold][red]Gitpanion[/red][/bold][green], the agentic AI designed to make your life working with Git and GitHub easier.")

def attempt_login(access_token: str) -> Github:
    auth = Auth.Token(access_token)
    g = Github(auth=auth)
    
    return g

#Verify/Add GitHub login credentials
if login_details.is_file():
    console.print("It appears that you already have setup GitHub authentication, verifying login details...")
    access_token = login_details.read_text().strip()
    try:
        g = attempt_login(access_token)
        user = g.get_user()
        console.print(f"Logged in as [bold]{user.login}[/bold]")
    except GithubException:
        console.print("[red]GitHub authentication failed, credentials must be reentered[/red]")
        success = False
        while not success:
            token = console.input("Please enter GitHub access_token: ")
            try:
                g = attempt_login(token)
                user = g.get_user()
                success = True
                console.print(f"[green]Logged in as[/green] [bold]{user.login}[/bold]")
                login_details.write_text(token)
            except GithubException:
                console.print("[red]GitHub authentication failed, please reenter credentials[/red]: ")
                success = False
else:
    console.print("It appears that you have not setup GitHub authentication")
    success = False
    token = console.input("Please enter GitHub access_token: ")
    while not success:
        try:
            g = attempt_login(token)
            user = g.get_user()
            success = True
            console.print(f"Logged in as [bold]{user.login}[/bold]")
            login_details.write_text(token)
        except GithubException:
            console.input("[red]GitHub authentication failed, please reenter credentials[/red]: ")
            success = False

#Verify/Add Gemini API key
if gemini_api.is_file():
    console.print("\nIt appears you already have setup Gemini API access, verifying...")
    key = gemini_api.read_text().strip()
else:
    key = console.input("Please enter Gemini API key: ")

success = False
while not success:
    try:
        client = genai.Client(api_key=key)
        client.models.list()
        console.print("[green]Gemini API successfully set up![/green]")
        gemini_api.write_text(key)
        success = True
    except genai_errors.APIError:
        console.print("[red]Authentication failed, please enter Gemini API key[/red]")
        key = console.input("Gemini API key: ")