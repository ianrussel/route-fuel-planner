1. Update pyenv and find the latest version

# If using Homebrew on macOS
```brew upgrade pyenv```

# If using Linux/Git clone
```cd ~/.pyenv && git pull```

# List latest stable versions (look near the bottom of the list)
```pyenv install --list | grep -E '^[[:space:]]*[0-9]+\.[0-9]+\.[0-9]+$' | tail -n 10```



2. Install the latest Python version

Run the install command with the specific version number you found (for example, 3.13.0):

```pyenv install 3.13.0```


3. Route pyenv to your project directory

Navigate to your project directory and tell pyenv to use the newly installed version locally:
```
mkdir my-project
cd my-project```

# Sets a local .python-version file in this directory
```pyenv local 3.13.0```



4. Create and activate the venv environment

Now that pyenv has set your local shell to the target Python version, you can invoke the native venv module to create your isolated environment:
bash
# Create the virtual environment (typically named .venv)
python -m venv .venv

# Activate it (macOS / Linux)
source .venv/bin/activate

# Activate it (Windows PowerShell)
# .venv\Scripts\Activate.ps1