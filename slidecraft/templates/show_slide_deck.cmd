@echo off
REM ==========================================================================
REM  Slidecraft - view this deck
REM  Double-click to render slides.md with Slidev and open it in your browser.
REM  First run installs Slidev + the theme into this folder's node_modules
REM  (one-time, needs internet & Node.js). Close this window / Ctrl+C to stop.
REM ==========================================================================

cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found on your PATH.
  echo Please install it from https://nodejs.org  then double-click this file again.
  echo.
  pause
  exit /b 1
)

if not exist "slides.md" (
  echo No slides.md found next to this launcher.
  echo Run /draft-deck first to build the deck, then try again.
  echo.
  pause
  exit /b 1
)

REM Slidev resolves its theme from a local node_modules, so it must be installed.
REM /init-deck usually installs it in the background during the interview; check
REM for the actual slidev binary (not just the folder) so a half-finished install
REM is completed rather than skipped.
if not exist "node_modules\.bin\slidev.cmd" (
  echo Installing Slidev and the theme into this deck ^(one-time^)...
  echo.
  call npm install --no-audit --no-fund
  if errorlevel 1 (
    echo.
    echo npm install failed - check your internet connection and try again.
    pause
    exit /b 1
  )
)

echo.
echo Starting Slidev...  a clickable link will appear below and your browser will open.
echo (Leave this window open while presenting; close it to stop.)
echo.

call npx slidev slides.md --open

if errorlevel 1 (
  echo.
  echo Slidev exited with an error - see the message above.
  pause
)
