from rich.console import Console
import re
import shutil
from github import Github, GithubException
from github import Auth
from pathlib import Path
import subprocess
import shlex
import webbrowser
console = Console()

possiblecommands = ["READONL", "REPOSTRUCTONL", "REPOLIST", "READLOC",
                     "STRUCTLOC", "ASK", "TEXT", "RUNCOMMAND",
                     "AUTHGH", "STATUS", "DIFF", "SETTINGS", "OPENPAGE", "GHNAME",
                     "CURRPROJ", "UPDATEAUTOCOMMITDIR", "DELETE"]

def interpret(text: str) -> tuple[str, tuple, tuple, tuple]:
    match = re.match(r"([^:]+):", text)
    if match is None:
        stripped = text.strip()
        if stripped in possiblecommands:
            aicommand = stripped
        else:
            raise ValueError("No command exists in the Gemini output")
    else:
        aicommand = match.group(1).strip()
    if aicommand not in possiblecommands:
        raise ValueError(f"Command given does not exist (invalid command: {aicommand})")
    
    matches = re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', text)
    while len(matches) < 3:
        matches.append((None, None))

    params = tuple(m[0] for m in matches)
    values = tuple(m[1].replace('\\"', '"') if m[1] is not None else None for m in matches)
    
    out1 = (params[0], values[0])
    out2 = (params[1], values[1])
    out3 = (params[2], values[2])

    return aicommand, out1, out2, out3

def text(*outs: tuple) -> None:
    output = ""
    for out in outs:
        if out[0] == "text":
            output = out[1]
    if output == "":
        raise ValueError("No 'text' command found in Gemimi output")
    
    console.print(f"{output}" + "\n")

def ask(*outs: tuple) -> str:
    output = ""
    for out in outs:
        if out[0] == "text":
            output = out[1]
    if output == "":
        raise ValueError("No 'text' command found in Gemimi output")
    
    val = console.input(f"[green]{output}[/green]\n\n")
    console.print("\n")
    return "User Input: " + val
    
def readonl(g: Github, *outs: tuple) -> str:
    repolink = ""
    file_location = ""
    for out in outs:
        if out[0] == "repo":
            repolink = out[1]
        if out[0] == "file":
            file_location = out[1]
    if file_location == "" or repolink == "":
        raise ValueError("Gemini output requires both repo and file parameters")
    repo = g.get_repo(repolink)
    file_content = repo.get_contents(file_location)

    return file_content.decoded_content.decode('utf-8')
    
def repostructonl(g: Github, *outs: tuple) -> str:
    repolink = ""
    for out in outs:
        if out[0] == "repo":
            repolink = out[1]
    if repolink == "":
        raise ValueError("Gemini output requires a repo parameter")
    repo = g.get_repo(repolink)
    tree = repo.get_git_tree(repo.default_branch, recursive=True)
    
    return "\n".join(element.path for element in tree.tree)

def repolist(g: Github, *_) -> str:
    user = g.get_user()
    repos = {repo.full_name: repo for repo in user.get_repos(type="all")}
    for org in user.get_orgs():
        for repo in org.get_repos(type="all"):
            repos.setdefault(repo.full_name, repo)
    return "\n".join(repos.keys())

def readloc(*outs: tuple) -> str:
    file = ""
    for out in outs:
        if out[0] == "file":
            file = Path(out[1])
    if file == "":
        raise ValueError("Gemini output requires a file parameter")
    if not file.exists():
        raise ValueError(f"{file} does not exist")

    try: #function will return text if able, else will return binary
        output = file.read_text()
    except Exception:
        output = "File could only be read as binary, the following is the file binary: " + str(file.read_bytes())

    return output



def writeloc_direct(file_path: str, contents: str, reason: str, autowrite: bool = False) -> bool:
    file = Path(file_path).resolve()
    action = "overwrite" if file.is_file() else "write"
    if not autowrite:
        authorization = console.input(f"Gitpanion is attempting to {action} a file at location [blue]{str(file)}[/blue] with the following reason: [green][bold]{reason}[/bold][/green] Do you authorize Gitpanion to perform this action? Respond \"[bold]yes[/bold]\" to confirm, or anything else to deny: ")
        console.print("\n")
    else:
        authorization = "yes"
    if authorization.lower() in ("yes", "y", "yes."):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(contents)
        return True
    else:
        return False

def structloc(*outs: tuple) -> str:
    directory = ""
    for out in outs:
        if out[0] == "dir":
            directory = Path(out[1])
    if directory == "":
        raise ValueError("Gemini output requires a dir parameter")
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a valid directory")
    loc = "\n".join(str(p) for p in sorted(directory.rglob("*")))
    if len(loc) > 10000:
        loc = "Directory contents too large to display, only showing top level information (search any directories here to read their subdirectories):\n" + "\n".join(str(p) for p in sorted(directory.glob("*")))
    if len(loc) > 10000:
        loc = "Directory contents too large to display"
    return loc

def runcommand(*outs: tuple, autorun: bool = False) -> tuple[str, bool]:
    command, reason = "", ""
    for out in outs:
        if out[0] == "command":
            command = out[1]
        if out[0] == "reason":
            reason = out[1]
    if command == "" or reason == "":
        raise ValueError("Gemini output requires command and reason parameters")
    if not autorun:
        authorization = console.input(f"Gitpanion is attempting the bash command [blue]{command}[/blue] with the following reason: [green][bold]{reason}[/bold][/green] Do you authorize Gitpanion to perform this action? Respond \"[bold]yes[/bold]\" to confirm, or anything else to deny: ")
        console.print("\n")
    else:
        authorization = "yes"

    if authorization.lower() in ("yes", "y", "yes."):
        out = subprocess.run(command, capture_output=True, text=True, shell=True)
        return (out.stdout + out.stderr, True)
    else:
        return (None, False)
    
def authgh(*_: tuple) -> str:
    out = subprocess.run("gh auth login --with-token < ./auth.dat", capture_output=True, text=True, shell=True)
    return out.stdout + out.stderr

def status(*outs: tuple) -> str:
    directory = ""
    for out in outs:
        if out[0] == "dir":
            directory = Path(out[1])
    if directory == "":
        raise ValueError("Gemini output requires a dir parameter")
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a valid directory")
    out = subprocess.run(["git", "-C", str(directory), "status"], capture_output=True, text=True)
    return out.stdout + out.stderr

def diff(*outs: tuple) -> str:
    directory = ""
    for out in outs:
        if out[0] == "dir":
            directory = Path(out[1])
    if directory == "":
        raise ValueError("Gemini output requires a dir parameter")
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a valid directory")
    out = subprocess.run(["git", "-C", str(directory), "diff"], capture_output=True, text=True)
    return out.stdout + out.stderr

def update_autocommit_dir(*outs: tuple) -> str:
    directory = ""
    for out in outs:
        if out[0] == "dir":
            directory = Path(out[1])
    if directory == "":
        raise ValueError("Gemini output requires a dir parameter")
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a valid directory")
    return str(directory)

def openpage(g = Github, *outs: tuple) -> str:
    url = ""
    username = ""
    for out in outs:
        if out[0] == "url":
            url = out[1]
        if out[0] == "username":
            username = out[1]
    if url == "":
        raise ValueError("Gemini output requires a url parameter")
    if username == "":
        raise ValueError("Gemini output requires a username parameter, rerun this command after running GHNAME")
    user = g.get_user()
    if user.login != username:
        raise ValueError(f"GitHub username provided ({username}) does not match authenticated user ({user.login}), try again with the correct username.")

    webbrowser.open(url)
    return f"Opened {url} in web browser"

def ghname(g = Github, *_: tuple) -> str:
    out = g.get_user()
    return out.login
    
def currproj(*_: tuple) -> str:
    return "Functionality defined in main.py loop"

def delete(*outs: tuple) -> tuple[str, bool]:
    filepath = ""
    for out in outs:
        if out[0] == "path":
            filepath = Path(out[1])
    if filepath == "":
        raise ValueError("Gemini output requires a path parameter")
    if not filepath.exists():
        raise ValueError(f"{filepath} does not exist")
    is_dir = filepath.is_dir()
    kind = "folder" if is_dir else "file"
    authorization = console.input(f"Gitpanion is attempting to delete the {kind} at location [blue]{str(filepath)}[/blue]. Do you authorize Gitpanion to perform this action? Respond \"[bold]yes[/bold]\" to confirm, or anything else to deny: ")
    console.print("\n")
    if authorization.lower() in ("yes", "y", "yes."):
        if is_dir:
            shutil.rmtree(filepath)
        else:
            filepath.unlink()
        return f"{filepath} deleted successfully", True
    else:
        return f"User denied deletion of {filepath}", False

def settings(*_: tuple) -> None:
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
    else:
        file.write_text("autorun=FALSE\nautowrite=FALSE\ndefaultgithubdir=\nautocommit=TRUE")
        console.print("Settings file created, reask Githelp about settings to edit settings")
        return
    for setting in rules.keys():
        if setting in ["autorun", "autowrite", "debug", "autocommit"]:
            newrule = console.input(f"Would you like to enable {setting}? Type \"yes\" or \"no\" (all other inputs will be treated as a no): ")
            if newrule.lower() in ["yes", "yes.", "y"]:
                console.print(f"{setting} [green]enabled[/green]")
                rules[setting] = "TRUE"
            else:
                console.print(f"{setting} [red]disabled[/red]")
                rules[setting] = "FALSE"
        elif setting == "defaultgithubdir":
            while True:
                newrule = console.input("Please drag and drop/paste the location of your default GitHub directory into the terminal, keep the line blank to not change the setting or type \"none\" to have no default directory: ").strip(" ")
                if not newrule:
                    rules["defaultgithubdir"] = rules.get("defaultgithubdir")
                    console.print(f"Default GitHub directory unchanged")
                    break
                if newrule.lower() in ["n", "none", "none."]:
                    break
                newrule = Path(newrule)
                if newrule.is_dir():
                    rules["defaultgithubdir"] = newrule
                    console.print(f"{newrule} set as default directory for Gitpanion")
                    break
                else:
                    console.print("[red]Error! Directory not found, please try again.[/red]")
                    continue
    newrules = []
    for itm in rules.items():
        newrules.append(f"{itm[0]}={itm[1]}")
    
    file.write_text("\n".join(newrules))