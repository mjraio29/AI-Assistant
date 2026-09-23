# Packages the desktop app into a standalone Robert.exe with PyInstaller.
# Run from the project root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File desktop\build.ps1
# Output lands in dist\Robert.exe

pip install --quiet pyinstaller

pyinstaller `
  --name "Robert" `
  --windowed `
  --onefile `
  --icon "desktop\assets\icon.ico" `
  --add-data "app\prompts;app\prompts" `
  --add-data "desktop\assets;desktop\assets" `
  --hidden-import customtkinter `
  --hidden-import pystray._win32 `
  desktop\main.py

Write-Host ""
Write-Host "Build complete. Robert.exe is in the dist folder."
Write-Host "Copy your .env file into dist\ next to Robert.exe -- the exe reads"
Write-Host "GROQ_API_KEY from a .env file placed next to it, not from the project folder."
