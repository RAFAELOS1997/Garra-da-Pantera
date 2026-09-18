$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

function Invoke-Checked([scriptblock]$Command, [string]$Description) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description falhou com código $LASTEXITCODE."
    }
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher não encontrado. Instale Python 3.12 em https://www.python.org/downloads/"
}

Invoke-Checked { py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" } "Verificação do Python 3.12"
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$VenvReady = $false
if (Test-Path -LiteralPath $VenvPython) {
    & $VenvPython -c "import sys; assert sys.version_info[:2] == (3, 12)"
    $VenvReady = ($LASTEXITCODE -eq 0)
}
if (-not $VenvReady) {
    Invoke-Checked { py -3.12 -m venv --clear .venv } "Criação do ambiente virtual"
}
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Atualização do pip falhou com código $LASTEXITCODE." }
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Instalação das dependências falhou com código $LASTEXITCODE." }
& $VenvPython -c "import numpy, trimesh, sklearn, maxflow, torch, transformers, pymeshfix, manifold3d"
if ($LASTEXITCODE -ne 0) { throw "Validação final das dependências falhou com código $LASTEXITCODE." }
Write-Host "Instalação concluída. Execute abrir_programa.bat."
