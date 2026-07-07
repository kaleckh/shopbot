# shopbot watcher layer - checks config/watches.json via headless Claude and
# drops DEAL-ALERT.md on the Desktop when a target hits.
# Scheduled as Windows task 'ClaudePriceWatch' (9:23 AM + 4:23 PM daily).
# KEEP THIS FILE PURE ASCII - PS 5.1 reads BOM-less .ps1 as ANSI and
# multi-byte characters parse-break the script.
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $env:USERPROFILE

$repo = Join-Path $env:USERPROFILE 'shopbot'
$cfg = Get-Content (Join-Path $repo 'config\watches.json') -Raw -Encoding UTF8
$logDir = Join-Path $repo 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("watch-{0}.md" -f (Get-Date -Format 'yyyy-MM-dd_HHmm'))

$prompt = @"
You are the watcher layer of Kale's shopbot. You are unattended; do not ask questions.

Below is a JSON config of watches. For EACH watch:
1. WebFetch the checkUrls (some may block bots - that's fine, note it and move on).
2. WebSearch for current in-stock prices matching the goal (include the current month/year in queries).
3. Judge against maxPriceUSD and the goal text. Only count offers that appear genuinely IN STOCK at a reputable US retailer or brand-direct store. Marketplace third-party gouging does not count. A price tracker or deal article is a LEAD, not truth - verify on an actual retailer page before counting it (trackers have been caught 2.5x stale).

CONFIG:
$cfg

End your report with EXACTLY one line per triggered watch, at the very end:
ALERT: <watch id> - <product> at `$<price> at <retailer>, <direct URL>
or, if no watch qualified, a single line:
NOALERT: <one-line closest-miss summary (best real price seen and where)>
"@

"# Price watch run $(Get-Date -Format s)" | Out-File $log -Encoding utf8
& claude -p $prompt --allowedTools "WebSearch,WebFetch,Read" 2>&1 |
  Out-File -Append $log -Encoding utf8
"`n---`nexit=$LASTEXITCODE finished $(Get-Date -Format s)" | Out-File -Append $log -Encoding utf8

$content = Get-Content $log -Raw -Encoding UTF8
if ($content -match '(?m)^ALERT:') {
  $desktop = [Environment]::GetFolderPath('Desktop')
  $banner = "# DEAL ALERT - $(Get-Date -Format 'yyyy-MM-dd HH:mm')`n`nA price-watch target hit. Buy fast - shortage restocks sell out in hours.`n`n"
  ($banner + $content) | Out-File (Join-Path $desktop 'DEAL-ALERT.md') -Encoding utf8
}

# keep the 20 most recent logs
Get-ChildItem $logDir -Filter 'watch-*.md' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -Skip 20 |
  Remove-Item -Force -Confirm:$false
