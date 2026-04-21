from rich.console import Console
from github import Github, GithubException
from github import Auth
from pathlib import Path
from google import genai
from google.genai import errors as genai_errors
import subprocess
import sys
import re
console = Console()

access_token = ""
login_details = Path("auth.dat")
gemini_api = Path("api.dat")

console.print("[green]Welcome to[/green] [bold][red]Gitpanion[/red][/bold][green], the agentic AI designed to make your life working with Git and GitHub easier.")

# Check and install brew and gh
def is_installed(command: str) -> bool:
    return subprocess.run(["which", command], capture_output=True).returncode == 0

if not is_installed("brew"):
    console.print("[yellow]Homebrew not found. Installing...[/yellow]")
    result = subprocess.run(
        '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
        shell=True
    )
    if result.returncode != 0:
        console.print("[red]Failed to install Homebrew. Please install it manually from https://brew.sh[/red]")
        sys.exit(1)
    console.print("[green]Homebrew installed successfully.[/green]")
else:
    console.print("[green]Homebrew is already installed.[/green]")

if not is_installed("gh"):
    console.print("[yellow]GitHub CLI (gh) not found. Installing via Homebrew...[/yellow]")
    result = subprocess.run(["brew", "install", "gh"])
    if result.returncode != 0:
        console.print("[red]Failed to install gh. Please install it manually: https://cli.github.com[/red]")
        sys.exit(1)
    console.print("[green]GitHub CLI installed successfully.[/green]")
else:
    console.print("[green]GitHub CLI is already installed.[/green]")

def attempt_login(access_token: str) -> Github:
    """Return an authenticated Github client; authentication is lazy and won't raise until the first API call."""
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

def get_settings() -> dict:
    """Parse settings.txt into a dict; creates the file with defaults and recurses once if it doesn't exist."""
    file = Path("./settings.txt")
    if file.is_file():
        settings = file.read_text().split("\n")
        settingname = r"^(.*)="
        settingval = r"=(.*)$"

        rules = dict()
        for setting in settings:
            name_match = re.match(settingname, setting)
            val_match = re.search(settingval, setting)
            if name_match and val_match:
                val_str = val_match.group(1)
                if val_str == "TRUE":
                    rules[name_match.group(1)] = True
                elif val_str == "FALSE":
                    rules[name_match.group(1)] = False
                else:
                    rules[name_match.group(1)] = val_str

        return rules
    else:
        file.write_text("autorun=FALSE\nautowrite=FALSE\ndefaultgithubdir=\nautocommit=TRUE")
        return get_settings()