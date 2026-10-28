param([string]$IconPath, [string]$ShortcutPath, [string]$Launcher)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) { throw 'Bundled application icon is missing.' }
if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) { throw 'Application launcher is missing.' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $Launcher
$shortcut.WorkingDirectory = Split-Path -Parent $Launcher
$shortcut.IconLocation = $IconPath + ',0'
$shortcut.Description = 'Godfall Equipment Editor'
$shortcut.Save()
