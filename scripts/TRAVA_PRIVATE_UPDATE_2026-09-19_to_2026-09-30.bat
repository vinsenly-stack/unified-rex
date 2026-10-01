@echo off
setlocal EnableDelayedExpansion

REM Trava Private / Unified REX v0.25 data extension
REM Downloads Binance USD-M Futures 1m klines for Sep 19-30, 2026
REM Assets: HYPE, AAVE, TAO, UNI, APT, ONDO, PENDLE, AKE, USELESS

set OUT=TRAVA_PRIVATE_1M_UPDATE_2026-09-19_to_2026-09-30
if not exist "%OUT%" mkdir "%OUT%"

set SYMBOLS=HYPEUSDT AAVEUSDT TAOUSDT UNIUSDT APTUSDT ONDOUSDT PENDLEUSDT AKEUSDT USELESSUSDT

for %%S in (%SYMBOLS%) do (
  if not exist "%OUT%\%%S" mkdir "%OUT%\%%S"
  for /L %%D in (19,1,30) do (
    set DD=%%D
    if %%D LSS 10 set DD=0%%D
    set FILE=%%S-1m-2026-09-!DD!.zip
    set URL=https://data.binance.vision/data/futures/um/daily/klines/%%S/1m/!FILE!
    echo Downloading !URL!
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '!URL!' -OutFile '%OUT%\%%S\!FILE!' -UseBasicParsing -ErrorAction Stop } catch { Write-Host 'FAILED: !URL!' -ForegroundColor Red; exit 1 }"
    if errorlevel 1 goto :fail
  )
)

echo.
echo Verifying downloaded ZIP files...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$bad=0; Get-ChildItem '%OUT%' -Recurse -Filter *.zip | ForEach-Object { try { Add-Type -AssemblyName System.IO.Compression.FileSystem; $z=[IO.Compression.ZipFile]::OpenRead($_.FullName); if($z.Entries.Count -lt 1){throw 'empty'}; $z.Dispose() } catch { Write-Host ('BAD ZIP: '+$_.FullName) -ForegroundColor Red; $bad=1 } }; if($bad){exit 1}"
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%OUT%\*' -DestinationPath '%OUT%.zip' -Force"
if errorlevel 1 goto :fail

echo.
echo DONE: %OUT%.zip
exit /b 0

:fail
echo.
echo DOWNLOAD FAILED. Check the last URL above and rerun the BAT.
exit /b 1
