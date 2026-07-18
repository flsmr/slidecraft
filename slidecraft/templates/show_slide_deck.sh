#!/usr/bin/env bash
# ==========================================================================
#  Slidecraft - view this deck  (macOS / Linux)
#  Run this to render slides.md with Slidev and open it in your browser.
#    Terminal:  ./show_slide_deck.sh
#    macOS:     make it double-clickable by renaming to show_slide_deck.command,
#               or: chmod +x show_slide_deck.sh  then double-click / run.
#  First run installs Slidev + the theme into this folder's node_modules
#  (one-time, needs internet & Node.js). Press Ctrl+C to stop.
# ==========================================================================
set -e

# cd to this script's own folder (the deck root), regardless of where it's run from.
cd "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js was not found on your PATH."
  echo "Install it from https://nodejs.org  then run this again."
  read -r -p "Press Enter to close..." _
  exit 1
fi

if [ ! -f slides.md ]; then
  echo "No slides.md found next to this launcher."
  echo "Run /draft-deck first to build the deck, then try again."
  read -r -p "Press Enter to close..." _
  exit 1
fi

# Slidev resolves its theme from a local node_modules, so it must be installed.
# /init-deck usually installs it in the background during the interview; check for
# the actual slidev binary (not just the folder) so a half-finished install is
# completed rather than skipped.
if [ ! -x node_modules/.bin/slidev ]; then
  echo "Installing Slidev and the theme into this deck (one-time)..."
  echo
  npm install --no-audit --no-fund
fi

echo
echo "Starting Slidev...  a clickable link will appear below and your browser will open."
echo "(Leave this window open while presenting; press Ctrl+C to stop.)"
echo

npx slidev slides.md --open
