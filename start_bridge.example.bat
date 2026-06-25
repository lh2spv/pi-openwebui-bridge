@echo off
REM start_bridge.example.bat
REM Copy to start_bridge.bat, edit the two lines below, then double-click to run.
REM Keep this file ASCII-only (do not add Japanese). cmd mis-parses UTF-8 comments.

REM 1) Full path to pi.exe (from the pi-windows-x64.zip you extracted)
set "PI_BIN=C:\pi\pi.exe"

REM 2) Model to show in Open WebUI:  pi-agent=--provider <name in models.json> --model <model id>
set "PI_BRIDGE_MODELS=pi-agent=--provider myllm --model <model-name>"

REM Where the agent saves files (cannot write outside this folder)
set "PI_BRIDGE_CWD=%~dp0workspace"

REM Tools the agent may use. Read-only would be: read,grep,find,ls
set "PI_BRIDGE_TOOLS=read,grep,find,ls,edit,write,bash"

set "PI_BRIDGE_HOST=0.0.0.0"
set "PI_BRIDGE_PORT=8765"

REM ---- For a shared Open WebUI server (each user runs this on their own PC) ----
REM Uncomment and set these. ALLOW_ORIGIN must match your Open WebUI address.
REM set "PI_BRIDGE_HOST=127.0.0.1"
REM set "PI_BRIDGE_API_KEY=your-secret-key"
REM set "PI_BRIDGE_ALLOW_ORIGIN=http://owui.example.com:3000"

python "%~dp0pi_bridge.py"
pause
