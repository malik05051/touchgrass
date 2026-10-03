#!/usr/bin/env sh
# Builds dist/TouchGrass (a single, self-contained Linux executable).
set -e
python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --noconfirm --onefile --windowed --name TouchGrass touchgrass.py
echo "Done! Your game is at dist/TouchGrass"
