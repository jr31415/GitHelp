from rich.console import Console
from github import Github, GithubException
from github import Auth
from pathlib import Path
console = Console()

access_token = ""
login_details = Path("auth.dat")

console.print("[green]Welcome to[/green] [bold][red]GitHelp[/red][/bold][green], the agentic AI designed to make your life working with Git and GitHub easier.")

def attempt_login(access_token: str) -> Github:
    auth = Auth.Token(access_token)
    g = Github(auth=auth)
    
    return g

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
            except GithubException:
                console.print("[red]GitHub authentication failed, please reenter credentials[/red]: ")
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
        except GithubException:
            console.input("[red]GitHub authentication failed, please reenter credentials[/red]: ")
            success = False

if not login_details.is_file():
    login_details.write_text(token)

