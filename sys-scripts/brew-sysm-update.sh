#!/bin/zsh
set -o pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
brew update --quiet && brew upgrade sysm 2>&1 || true
