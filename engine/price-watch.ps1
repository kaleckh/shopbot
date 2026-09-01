# shopbot watcher layer - checks config/watches.json via headless Claude and
# drops DEAL-ALERT.md on the Desktop when a target hits.
# Scheduled as Windows task 'ClaudePriceWatch' (9:23 AM + 4:23 PM daily).
# KEEP THIS FILE PURE ASCII - PS 5.1 reads BOM-less .ps1 as ANSI and
# multi-byte characters parse-break the script.
param(
  [string]$RepoRoot = (Join-Path $env:USERPROFILE 'shopbot'),
  [string]$DesktopRoot = [Environment]::GetFolderPath('Desktop'),
  [string]$ClaudeCommand = 'claude'
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $env:USERPROFILE

$repo = $RepoRoot
$configPath = Join-Path $repo 'config\watches.json'
$configText = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 -ErrorAction Stop
$null = $configText | ConvertFrom-Json -ErrorAction Stop
$logDir = Join-Path $repo 'logs'
[System.IO.Directory]::CreateDirectory($logDir) | Out-Null
$runId = "{0}-{1}-{2}" -f (Get-Date -Format 'yyyy-MM-dd_HHmmss'), $PID, ([guid]::NewGuid().ToString('N').Substring(0, 8))
$log = Join-Path $logDir ("watch-{0}.md" -f $runId)
$capture = Join-Path $logDir (".watch-{0}.capture.tmp" -f $runId)
$stagedLog = Join-Path $logDir (".watch-{0}.publish.tmp" -f $runId)

$prompt = @"
You are the watcher layer of Kale's shopbot. You are unattended; do not ask questions.

Read the complete JSON config from this exact local file before doing any research:
$configPath

Do not rely on a config copied into this prompt; the file is the source of truth. For EACH watch:
1. WebFetch the checkUrls (some may block bots - that's fine, note it and move on).
2. WebSearch for current in-stock prices matching the goal (include the current month/year in queries).
3. Judge against maxPriceUSD and the goal text. Only count offers that appear genuinely IN STOCK at a reputable US retailer or brand-direct store. Marketplace third-party gouging does not count. A price tracker or deal article is a LEAD, not truth - verify on an actual retailer page before counting it (trackers have been caught 2.5x stale).

End your report with EXACTLY one line per triggered watch, at the very end:
ALERT: <watch id> - <product> at `$<price> at <retailer>, <direct URL>
or, if no watch qualified, a single line:
NOALERT: <one-line closest-miss summary (best real price seen and where)>
"@

try {
  # Capture to a private path. The final report must not exist or be held open
  # while the child producer is running.
  & $ClaudeCommand -p $prompt --allowedTools "WebSearch,WebFetch,Read" *> $capture
  $producerExit = $LASTEXITCODE
  if ($null -eq $producerExit) {
    $producerExit = 0
  }
  $producerOutput = ''
  if ([System.IO.File]::Exists($capture)) {
    $producerOutput = [System.IO.File]::ReadAllText($capture, [System.Text.Encoding]::UTF8)
  }
  $content = "# Price watch run $(Get-Date -Format s)`r`n$producerOutput`r`n---`r`nexit=$producerExit finished $(Get-Date -Format s)`r`n"
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($stagedLog, $content, $utf8NoBom)
  [System.IO.File]::Move($stagedLog, $log)
}
finally {
  foreach ($temporaryPath in @($capture, $stagedLog)) {
    if ([System.IO.File]::Exists($temporaryPath)) {
      Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
  }
}

$content = Get-Content $log -Raw -Encoding UTF8
if ($content -match '(?m)^ALERT:') {
  $banner = "# DEAL ALERT - $(Get-Date -Format 'yyyy-MM-dd HH:mm')`n`nA price-watch target hit. Buy fast - shortage restocks sell out in hours.`n`n"
  $alertPath = Join-Path $DesktopRoot 'DEAL-ALERT.md'
  [System.IO.File]::WriteAllText($alertPath, ($banner + $content), (New-Object System.Text.UTF8Encoding($false)))
}

# keep the 20 most recent logs
Get-ChildItem -LiteralPath $logDir -Filter 'watch-*.md' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -Skip 20 |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -Confirm:$false }
