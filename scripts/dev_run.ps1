param(
  [string]$Config = "configs/dev.yaml",
  [int]$Duration = 20,
  [switch]$Install
)

$ErrorActionPreference = "Stop"

$venvActivate = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
  Write-Error "Missing venv. Create it with: py -3.11 -m venv .venv"
  exit 1
}

& $venvActivate

if ($Install) {
  pip install -r requirements.txt
  pip install -r requirements-dev.txt
}

python apps/dev_run.py --config $Config --duration $Duration
