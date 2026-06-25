# start_bridge.example.ps1
# Copy to start_bridge.ps1 and edit for your setup, then run:
#   powershell -ExecutionPolicy Bypass -File start_bridge.ps1

# Models shown in Open WebUI:  "<display-id>=<pi args>;<display-id2>=<pi args>"
# (the pi args pick the provider/model defined in ~/.pi/agent/models.json)
$env:PI_BRIDGE_MODELS = "pi-agent=--provider <provider> --model <model-id>"

# Path to the pi executable (omit to use PATH)
# $env:PI_BIN = "C:\path\to\pi\pi.exe"

# Working folder the agent reads/writes. It CANNOT write outside this.
$env:PI_BRIDGE_CWD = "$PSScriptRoot\workspace"

# Tools: omit for full (read,bash,edit,write). Read-only example:
# $env:PI_BRIDGE_TOOLS = "read,grep,find,ls"

# ---- Pattern A: single machine (client and bridge on the same box) ----
$env:PI_BRIDGE_HOST = "0.0.0.0"
$env:PI_BRIDGE_PORT = "8765"

# ---- Pattern B: shared Open WebUI server + agent on each user's PC ----
# (Open WebUI "Direct Connection" is made from the browser = same PC as the bridge)
# $env:PI_BRIDGE_HOST         = "127.0.0.1"                    # local only
# $env:PI_BRIDGE_API_KEY      = "your-secret-key"              # same value as the OWUI connection key
# $env:PI_BRIDGE_ALLOW_ORIGIN = "http://owui.example.com:3000" # your Open WebUI origin (CORS)

python "$PSScriptRoot\pi_bridge.py"
