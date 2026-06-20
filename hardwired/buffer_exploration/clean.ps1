$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Remove generated simulation outputs and generated comparison artifacts.
# Keep source inputs and scripts (e.g., simple_ab_buffer.sp, run.ps1, clean.ps1,
# run_spice.py, generate_plots.py, summary.md, README.md).
$patterns = @(
    "sim_output_*.txt",
    "sim_output_*.csv",
    "compare_*.sp",
    "compare_*.svg",
    "compare_*.png"
)

$deleted = @()
foreach ($pattern in $patterns) {
    Get-ChildItem -Path . -Filter $pattern -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
            $deleted += $_.Name
        }
}

if ($deleted.Count -eq 0) {
    Write-Host "Nothing to clean."
} else {
    Write-Host "Deleted generated artifacts:"
    $deleted | Sort-Object | ForEach-Object { Write-Host " - $_" }
}
