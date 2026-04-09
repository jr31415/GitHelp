from rich.console import Console
import re
from github import Github, GithubException
from github import Auth
from pathlib import Path
import subprocess
console = Console()

possiblecommands = ["EXIT", "READONL", "REPOSTRUCTONL", "REPOLIST", "READLOC",
                     "WRITELOC", "STRUCTLOC", "ASK", "TEXT", "RUNCOMMAND"]

def interpret(text: str) -> tuple[str, tuple, tuple, tuple]:
    match = re.match(r"([^:]+):", text)
    if match is None:
        stripped = text.strip()
        if stripped in possiblecommands:
            aicommand = stripped
        else:
            raise ValueError("Gemini model output in incorrect format (no command found)")
    else:
        aicommand = match.group(1)
    if aicommand not in possiblecommands:
        raise ValueError(f"Gemini model output in incorrect format (invalid command: {aicommand})")
    
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
    repos = list(user.get_repos(type="all"))
    orgs = list(user.get_orgs())
    for org in orgs:
        org_repos = list(org.get_repos(type="all"))
        for repo in org_repos:
            if repo not in repos:
                repos.append(repo)
    return "\n".join(repo.full_name for repo in repos)

def readloc(*outs: tuple) -> str:
    file = ""
    for out in outs:
        if out[0] == "file":
            file = Path(out[1])
    if file == "":
        raise ValueError("Gemini output requires a file parameter")
    
    try: #function will return text if able, else will return binary
        output = file.read_text()
    except Exception:
        output = "File could only be read as binary, the following is the file binary: " + str(file.read_bytes())

    return output


def writeloc(*outs: tuple) -> bool:
    file, contents, reason = "", "", ""
    for out in outs:
        if out[0] == "file":
            file = Path(out[1])
        if out[0] == "new_file_contents":
            contents = out[1].replace("\\n", "\n")
        if out[0] == "reason":
            reason = out[1]
    if file == "" or contents == "" or reason == "":
        raise ValueError("Gemini output requires file, new_file_contents, and reason parameters")    
    if file.is_file():
        authorization = console.input(f"Gitpanion is attempting to overwrite a file at location [blue]{str(file)}[/blue] with the following reason: [green][bold]{reason}[/bold][/green] Do you authorize Gitpanion to perform this action? Respond \"[bold]yes[/bold]\" to confirm, or anything else to deny: ")
    else:
        authorization = console.input(f"Gitpanion is attempting to write a file at location [blue]{str(file)}[/blue] with the following reason: [green][bold]{reason}[/bold][/green] Do you authorize Gitpanion to perform this action? Respond \"[bold]yes[/bold]\" to confirm, or anything else to deny: ")    
    console.print("\n")

    if authorization.lower() in ("yes", "y", "yes."):
        file.write_text(contents)
        return True
    else:
        return False

def writeloc_direct(file_path: str, contents: str, reason: str) -> bool:
    file = Path(file_path)
    action = "overwrite" if file.is_file() else "write"
    authorization = console.input(f"Gitpanion is attempting to {action} a file at location [blue]{str(file)}[/blue] with the following reason: [green][bold]{reason}[/bold][/green] Do you authorize Gitpanion to perform this action? Respond \"[bold]yes[/bold]\" to confirm, or anything else to deny: ")
    console.print("\n")
    if authorization.lower() in ("yes", "y", "yes."):
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
    return "\n".join(str(p) for p in sorted(directory.rglob("*")))

def runcommand(*outs: tuple) -> tuple[str, bool]:
    command, reason = "", ""
    for out in outs:
        if out[0] == "command":
            command = out[1]
        if out[0] == "reason":
            reason = out[1]
    if command == "" or reason == "":
        raise ValueError("Gemini output requires command and reason parameters")
    
    authorization = console.input(f"Gitpanion is attempting the bash command [blue]{command}[/blue] with the following reason: [green][bold]{reason}[/bold][/green] Do you authorize Gitpanion to perform this action? Respond \"[bold]yes[/bold]\" to confirm, or anything else to deny: ")
    console.print("\n")

    if authorization.lower() in ("yes", "y", "yes."):
        out = subprocess.run(command, capture_output=True, text=True, shell=True)
        return (out.stdout + out.stderr, True)
    else:
        return (None, False)
    
#def gotoparentdir(*_: tuple) -> str:
#    try:
#        subprocess.run("cd ../", shell=True)
#        return "Successfully went to parent directory"
#    except:
#        return "Failed to go to parent directory"
#
#def currentdir(*_: tuple) -> str:
#    out = subprocess.run("pwd", capture_output=True, text=True, shell=True)
#    return out.stdout + out.stderr
#
#def workspace(*outs: tuple) -> str:
#    directory = ""
#    for out in outs:
#        if out[0] == "dir":
#            directory = Path(out[1])
#    if directory == "":
#        raise ValueError("Gemini output requires a dir parameter")
#    if not directory.is_dir():
#        raise ValueError(f"{directory} is not a valid directory")
#    out = subprocess.run(f"cd {directory}", capture_output=True, text=True, shell=True)
#    return out.strout + out.stderr
    