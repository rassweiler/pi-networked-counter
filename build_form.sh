#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE}")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate

pyuic6 form.ui -o MainWindow.py