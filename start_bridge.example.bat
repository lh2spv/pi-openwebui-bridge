@echo off
REM start_bridge.example.bat
REM Copy to start_bridge.bat, edit the values, then double-click to run.
REM NOTE: keep .bat files ASCII-only (cmd mis-parses UTF-8 comments).

REM Models shown in Open WebUI:  "<display-id>=<pi args>;<display-id2>=<pi args>"
set "PI_BRIDGE_MODELS=pi-agent=--provider <provider> --model <model-id>"

REM Path to pi executable (omit to use PATH)
REM set "PI_BIN=C:\path\to\pi\pi.exe"

REM Agent working folder = where it reads/writes (cannot write outside it)
set "PI_BRIDGE_CWD=%~dp0workspace"

REM Tools: omit for full (read,bash,edit,write). Read-only example:
REM set "PI_BRIDGE_TOOLS=read,grep,find,ls"

REM ---- Pattern A: single machine ----
set "PI_BRIDGE_HOST=0.0.0.0"
set "PI_BRIDGE_PORT=8765"

REM ---- Pattern B: shared Open WebUI server + agent on each user's PC ----
REM (Direct Connection is made from the browser = same PC as the bridge)
REM set "PI_BRIDGE_HOST=127.0.0.1"
REM set "PI_BRIDGE_API_KEY=your-secret-key"
REM set "PI_BRIDGE_ALLOW_ORIGIN=http://owui.example.com:3000"

python "%~dp0pi_bridge.py"
pause
