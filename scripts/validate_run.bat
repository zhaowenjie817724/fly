@echo off
setlocal
if exist .venv\Scripts\python.exe (
  call .venv\Scripts\activate.bat
)
python tools\validate_run.py --run latest
