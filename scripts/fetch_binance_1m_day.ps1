param(
  [Parameter(Mandatory=$true)][string]$Symbol,
  [Parameter(Mandatory=$true)][string]$Date,
  [Parameter(Mandatory=$true)][string]$OutFile
)

$ErrorActionPreference = "Stop"
$fileName = "$Symbol-1m-$Date.zip"
$archiveUrl = "https://data.binance.vision/data/futures/um/daily/klines/$Symbol/1m/$fileName"

try {
  Write-Host "Downloading $archiveUrl"
  Invoke-WebRequest -Uri $archiveUrl -OutFile $OutFile -UseBasicParsing -ErrorAction Stop
  exit 0
}
catch {
  Write-Host "Daily archive unavailable; falling back to Binance Futures API for $Symbol $Date" -ForegroundColor Yellow
}

$dt = [DateTimeOffset]::ParseExact(
  "$Date 00:00:00",
  "yyyy-MM-dd HH:mm:ss",
  [Globalization.CultureInfo]::InvariantCulture,
  [Globalization.DateTimeStyles]::AssumeUniversal
)
$start = $dt.ToUnixTimeMilliseconds()
$end = $start + 86400000 - 1
$apiUrl = "https://fapi.binance.com/fapi/v1/klines?symbol=$Symbol&interval=1m&startTime=$start&endTime=$end&limit=1500"

$rows = Invoke-RestMethod -Uri $apiUrl -Method Get -ErrorAction Stop
if (-not $rows -or $rows.Count -ne 1440) {
  throw "Expected 1440 completed 1m bars for $Symbol $Date, got $($rows.Count)"
}

$tmpCsv = [IO.Path]::Combine([IO.Path]::GetDirectoryName($OutFile), "$Symbol-1m-$Date.csv")
$lines = foreach ($row in $rows) {
  ($row | ForEach-Object { [string]$_ }) -join ","
}
[IO.File]::WriteAllLines($tmpCsv, $lines, [Text.Encoding]::ASCII)

if (Test-Path $OutFile) { Remove-Item $OutFile -Force }
Compress-Archive -Path $tmpCsv -DestinationPath $OutFile -Force
Remove-Item $tmpCsv -Force
Write-Host "API fallback packaged: $OutFile"
