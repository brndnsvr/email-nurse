#!/bin/zsh
set -o pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
brew update --quiet && brew upgrade 2>&1
