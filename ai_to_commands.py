from rich.console import Console
import re
from github import Github, GithubException
from github import Auth
console = Console()

possiblecommands = ["READONL", "REPOSTRUCTONL", "REPOLIST", "READLOC", "WRITELOC", "STRUCTLOC", "ASK", "TEXT", "RUNCOMMAND"]

def interpret(text: str):
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
    
    matches = re.findall(r'(\w+)="([^"]*)"', text)
    while len(matches) < 3:
        matches.append((None, None))

    params = tuple(m[0] for m in matches)
    values = tuple(m[1] for m in matches)
    
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
    
    print(output)

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

    return file_content
    
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