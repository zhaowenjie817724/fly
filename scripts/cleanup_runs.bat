@echo off
setlocal
if exist .venv\Scripts\python.exe (
  call .venv\Scripts\activate.bat
)
python tools\cleanup_runs.py --keep-last 5 --dry-run
