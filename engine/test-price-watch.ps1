$ErrorActionPreference = 'Stop'

$watcher = Join-Path $PSScriptRoot 'price-watch.ps1'
$bytes = [System.IO.File]::ReadAllBytes($watcher)
if (@($bytes | Where-Object { $_ -gt 127 }).Count -ne 0) {
  throw 'price-watch.ps1 must remain ASCII-only'
}

$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile($watcher, [ref]$tokens, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -ne 0) {
  throw ($parseErrors | ForEach-Object { $_.Message } | Out-String)
}

$root = Join-Path ([System.IO.Path]::GetTempPath()) ("shopbot-watch-test-{0}" -f [guid]::NewGuid().ToString('N'))
$configDir = Join-Path $root 'config'
$logsDir = Join-Path $root 'logs'
$desktopDir = Join-Path $root 'desktop'
[System.IO.Directory]::CreateDirectory($configDir) | Out-Null
[System.IO.Directory]::CreateDirectory($logsDir) | Out-Null
[System.IO.Directory]::CreateDirectory($desktopDir) | Out-Null

$stub = Join-Path $root 'fake-claude.ps1'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $configDir 'watches.json'), '{"watches":[]}', $utf8NoBom)
[System.IO.File]::WriteAllText(
  $stub,
  "param([string]`$p, [string]`$allowedTools)`r`n" +
  "`$visible = @(Get-ChildItem -LiteralPath (Join-Path `$env:SHOPBOT_TEST_REPO 'logs') -Filter 'watch-*.md')`r`n" +
  "if (`$visible.Count -ne 0) { Write-Error 'final report was visible during producer execution'; exit 9 }`r`n" +
  "`$expectedConfig = Join-Path `$env:SHOPBOT_TEST_REPO 'config\watches.json'`r`n" +
  "if (`$p -notlike ('*' + `$expectedConfig + '*')) { Write-Error 'prompt omitted the config path'; exit 10 }`r`n" +
  "if (`$p -match '\{') { Write-Error 'prompt copied config JSON into command arguments'; exit 11 }`r`n" +
  "Write-Output 'NOALERT: isolated ownership regression test'`r`nexit 0`r`n",
  $utf8NoBom
)

$priorRepo = $env:SHOPBOT_TEST_REPO
$priorLocation = Get-Location
try {
  $env:SHOPBOT_TEST_REPO = $root
  & $watcher -RepoRoot $root -DesktopRoot $desktopDir -ClaudeCommand $stub
  $logs = @(Get-ChildItem -LiteralPath $logsDir -Filter 'watch-*.md')
  if ($logs.Count -ne 1) {
    throw "expected exactly one final report, found $($logs.Count)"
  }
  $content = Get-Content -LiteralPath $logs[0].FullName -Raw -Encoding UTF8
  $reportLines = @($content -split "`r?`n" | ForEach-Object { $_.Trim() })
  if ($content -notmatch '(?m)^exit=0 finished ') {
    throw "fake producer contract failed; final report follows:`r`n$content"
  }
  if ($reportLines -notcontains 'NOALERT: isolated ownership regression test') {
    throw "final report did not preserve producer output; final report follows:`r`n$content"
  }
  if (@(Get-ChildItem -LiteralPath $logsDir -Filter '*.tmp').Count -ne 0) {
    throw 'temporary watcher files were not cleaned up'
  }
  if ([System.IO.File]::Exists((Join-Path $desktopDir 'DEAL-ALERT.md'))) {
    throw 'NOALERT test unexpectedly published a deal alert'
  }
  Write-Output 'PASS: final report stayed absent during production and was atomically published after close'
}
finally {
  $env:SHOPBOT_TEST_REPO = $priorRepo
  Set-Location $priorLocation
  if ([System.IO.Directory]::Exists($root)) {
    Remove-Item -LiteralPath $root -Recurse -Force
  }
}
