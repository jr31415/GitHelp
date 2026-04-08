# gitpanion

An AI-driven assistant for managing Git and GitHub workflows through a natural language interface.

## Functionality
This tool uses a LLM backend to interpret user intent and execute corresponding Git commands, local file operations, or GitHub API calls. It automates repetitive tasks like creating documentation, managing branches, and inspecting repository structures.

## Project Structure
- `main.py`: Main execution loop and user interface.
- `ai_to_commands.py`: Parser that maps AI-generated tokens to system executions.
- `init.py`: Setup and configuration initialization.
- `prompt.txt`: System instructions for the LLM logic.
- `auth.dat` / `api.dat`: Local storage for GitHub and API credentials (not included in repo).

## Installation
1. Clone the repo:
   ```bash
   git clone https://github.com/jr31415/gitpanion.git
   cd gitpanion
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run:
   ```bash
   python main.py
   ```