from rich.console import Console
import re
console = Console()

possiblecommands = ["READONL", "REPOSTRUCTONL", "REPOLIST", "READLOC", "WRITELOC", "STRUCTLOC", "ASK", "TEXT", "RUNCOMMAND"]

def interpret(text: str):
    match = re.match(r"([^:]+):", text)
    if match is None:
        raise ValueError("Gemini model output in incorrect format (no command found)")
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
    
    