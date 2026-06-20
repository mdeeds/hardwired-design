$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} else {
    throw "No Python executable found."
}

Write-Host "Using Python: $pythonExe"
Write-Host "Running SPICE deck..."
& $pythonExe ".\run_spice.py" ".\simple_ab_buffer.sp"

Write-Host "Generating comparison SVG plots..."
& $pythonExe ".\generate_plots.py"

Write-Host "Pipeline complete."
