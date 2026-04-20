# Gitpanion Technical Documentation

Gitpanion is a command-line interface (CLI) tool that integrates Large Language Models (LLMs) with Git and the GitHub CLI (gh). It functions by parsing natural language input and executing a series of predefined operational procedures.

## Core Capabilities
- **Contextual Awareness**: Utilizes local and remote repository metadata to inform command execution.
- **File System Operations**: Direct manipulation of local files and directory structures.
- **GitHub API Integration**: Facilitates repository listing, structure inspection, and authentication via the GitHub CLI.

## Autocommit Functionality
Gitpanion includes an autocommit feature designed for continuous synchronization. When enabled for a specific directory, the system monitors for changes and can automatically stage, commit, and push updates

## File Manifest
- `main.py`: Entry point for the execution loop.
- `ai_to_commands.py`: Logic layer for token parsing and command execution.
- `init.py`: Configuration and environment initialization.
- `prompt.txt`: System instructions for the primary LLM agent.
- `autocommitprompt.txt`: Prompt for autocommit
- `autocommitsi.txt`: System instructions specifically for the autocommit routine.
- `requirements.txt`: List of Python dependencies.

## Installation and Execution
1. Clone the repository: `git clone https://github.com/jr31415/gitpanion.git`
2. Initialize virtual environment: `python -m venv .venv`
3. Activate environment: `source .venv/bin/activate`
4. Install requirements: `pip install -r requirements.txt`
5. Execute: `python main.py`

## Operational Safety
The tool requires manual confirmation for destructive operations such as deleting files or running commands. Security-sensitive files like `auth.dat` and `api.dat` are excluded from read operations.
