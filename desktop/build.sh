#!/usr/bin/env bash
# Packages the desktop app into a standalone executable with PyInstaller.
# Output lands in dist/Assistant (or dist/Assistant.exe on Windows).
set -e

pip install --quiet pyinstaller

pyinstaller \
  --name "Robert" \
  --windowed \
  --onefile \
  --icon "desktop/assets/icon.ico" \
  --add-data "app/prompts:app/prompts" \
  --add-data "desktop/assets:desktop/assets" \
  --hidden-import customtkinter \
  --hidden-import pystray._darwin \
  --hidden-import pystray._xorg \
  --hidden-import pystray._win32 \
  desktop/main.py

echo ""
echo "Build complete. Executable is in dist/"
echo "Note: the packaged app still reads GROQ_API_KEY from the environment"
echo "or a .env file placed next to the executable -- it is NOT embedded in the build."
