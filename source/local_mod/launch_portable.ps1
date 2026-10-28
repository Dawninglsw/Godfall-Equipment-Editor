param([switch]$GroundLoot)
$ErrorActionPreference = 'Stop'
$toolRoot = $PSScriptRoot
try {
$bundlePython = Join-Path (Split-Path -Parent $toolRoot) 'runtime\python\pythonw.exe'
$pythonExe = $null
if (Test-Path -LiteralPath $bundlePython -PathType Leaf) { $pythonExe = $bundlePython }
if (-not $pythonExe) {
    $settingsFile = Join-Path $toolRoot 'application_settings.json'
    if (Test-Path -LiteralPath $settingsFile -PathType Leaf) {
        $saved = Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.python_executable -and (Test-Path -LiteralPath $saved.python_executable -PathType Leaf)) {
            $pythonExe = $saved.python_executable
            $windowless = Join-Path (Split-Path -Parent $pythonExe) 'pythonw.exe'
            if (Test-Path -LiteralPath $windowless -PathType Leaf) { $pythonExe = $windowless }
        }
    }
}
if (-not $pythonExe) {
    throw 'The bundled runtime is missing. Extract the complete portable package again. / 运行环境缺失，请重新完整解压免安装包。'
}
$entry = Join-Path $toolRoot 'startup.py'
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { throw 'startup.py is missing. Extract the complete portable package again.' }
$launchArgs = @('"' + $entry + '"')
if ($GroundLoot) { $launchArgs += '--ground-loot' }
Start-Process -FilePath $pythonExe -ArgumentList $launchArgs -WorkingDirectory $toolRoot -WindowStyle Normal | Out-Null
exit 0
} catch {
    $errorMessage = $_.Exception.Message
    $logFile = Join-Path $toolRoot 'launcher_error.log'
    try { ($_ | Out-String) | Set-Content -LiteralPath $logFile -Encoding UTF8 } catch {}
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show("$errorMessage`r`n`r`nSee launcher_error.log / 请查看 launcher_error.log",'Godfall Equipment Editor') | Out-Null
    } catch { Write-Error $errorMessage }
    exit 1
}
