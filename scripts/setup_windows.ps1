# PowerShell helper for setting up self-operating-computer on Windows 10/11
# Uses Python 3.11, creates .venv, upgrades pip, installs requirements, and reminds the user what to run next.

Write-Host "Creating Python 3.11 virtual environment (.venv)..."
py -3.11 -m venv .venv

Write-Host "Activating virtual environment and upgrading pip..."
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

Write-Host "Installing requirements..."
pip install -r requirements.txt
# If you need the console script directly, uncomment the next line:
# pip install self-operating-computer

Write-Host "Setup complete. Next steps:"
Write-Host "1) .\\.venv\\Scripts\\Activate.ps1"
Write-Host "2) python task_runner.py (configure model/API key/voice/delay in the Settings tab)"
Write-Host "3) operate --help"
