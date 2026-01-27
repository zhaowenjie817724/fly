param(
  [string]$Run = "latest",
  [switch]$Strict
)

$ErrorActionPreference = "Stop"

$venvActivate = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
  & $venvActivate
}

$argsList = @("--run", $Run)
if ($Strict) {
  $argsList += "--strict"
}

python tools\validate_run.py @argsList
