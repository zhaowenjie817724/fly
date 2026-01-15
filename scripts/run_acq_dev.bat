@echo off
setlocal
set CONFIG=configs\dev.yaml
if not exist .venv\Scripts\python.exe (
  echo Missing venv. Create it with: python -m venv .venv
  exit /b 1
)
call .venv\Scripts\activate.bat
python apps\acquisition\run_acq.py --config %CONFIG%
