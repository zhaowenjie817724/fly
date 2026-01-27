param(
  [int]$KeepLast = 5,
  [int]$MaxAgeDays = 0,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$venvActivate = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
  & $venvActivate
}

$argsList = @("--keep-last", $KeepLast)
if ($MaxAgeDays -gt 0) {
  $argsList += @("--max-age-days", $MaxAgeDays)
}
if ($DryRun) {
  $argsList += "--dry-run"
}

python tools\cleanup_runs.py @argsList
