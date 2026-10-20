$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$ollamaExecutable = Join-Path $projectPath '.tools\ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaExecutable)) { exit 0 }
try {
    Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 | Out-Null
} catch {
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_MODELS = Join-Path $projectPath 'runtime\ollama-models'
    $env:OLLAMA_NO_CLOUD = '1'
    Start-Process -FilePath $ollamaExecutable -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $projectPath
}
