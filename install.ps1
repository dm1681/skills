$ErrorActionPreference = "Stop"
$Installer = Join-Path $PSScriptRoot "install.py"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv run --project $PSScriptRoot --python 3.12 $Installer @args
    exit $LASTEXITCODE
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $Installer @args
    exit $LASTEXITCODE
}

if (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 $Installer @args
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $Installer @args
    exit $LASTEXITCODE
}

Write-Error "uv or Python 3.9 or newer is required."
exit 127
