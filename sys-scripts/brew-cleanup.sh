#!/bin/zsh
set -o pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
brew cleanup --prune=30 2>&1
