# pi-openwebui-bridge

A tiny, dependency-free **OpenAI-compatible HTTP shim** that exposes the
[`pi` coding agent](https://github.com/earendil-works/pi-mono) (`pi-coding-agent`)
as a selectable model inside [Open WebUI](https://github.com/open-webui/open-webui)
— or any OpenAI-compatible client.

It spawns `pi` per request, streams the agent's output back as OpenAI chat
completions (SSE), and exposes the agent's tools (`read`/`edit`/`write`/`bash`),
so you can drive a real coding agent — including file edits and command
execution — straight from an Open WebUI chat, backed by any local LLM
(llama.cpp, Ollama, …) that `pi` is configured to use.

> ⚠️ **This runs an autonomous coding agent with shell and file-write access on
> the machine where the bridge runs.** Read the [Security](#security) section
> before exposing it to anything.

## How it works

```
Open WebUI / OpenAI client
        │  POST /v1/chat/completions  (OpenAI-compatible, SSE)
        ▼
   pi_bridge.py  (:8765)
        │  spawn:  pi -p --mode json --no-session --offline --approve ...
        ▼
      pi (coding agent)
        │  OpenAI-compatible API
        ▼
  LLM backend  (llama.cpp server / Ollama / …)
```

Endpoints:
- `GET /v1/models` — lists the models you configured via `PI_BRIDGE_MODELS`.
- `POST /v1/chat/completions` — serializes the conversation, runs `pi`, parses its
  JSON event stream, and returns the assistant text (streaming or non-streaming).

## Requirements

- **`pi`** (pi-coding-agent) — on `PATH`, or point to it with `PI_BIN`.
  Get it from the [pi-mono releases](https://github.com/earendil-works/pi-mono/releases).
- **Python 3.8+** — standard library only, no `pip install`.
- An **OpenAI-compatible LLM backend** that `pi` talks to, configured in
  `~/.pi/agent/models.json` (e.g. a llama.cpp server or Ollama).

## Quick start

```powershell
# Windows PowerShell (Linux/macOS: use the equivalent env syntax)
$env:PI_BRIDGE_MODELS = "my-agent=--provider <provider> --model <model-id>"
python pi_bridge.py
```

Then point your client at `http://localhost:8765/v1` (any API key works unless
you set `PI_BRIDGE_API_KEY`). In Open WebUI: add an **OpenAI API** connection
with that base URL.

See [`start_bridge.example.ps1`](start_bridge.example.ps1) for a fuller example.

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `PI_BRIDGE_MODELS` | `pi-agent` | Models to expose. `id=<pi args>;id2=<pi args>`. Empty args = pi defaults. |
| `PI_BIN` | `pi.exe` | Path to the `pi` executable (or rely on `PATH`). |
| `PI_BRIDGE_HOST` | `0.0.0.0` | Bind address. Use `127.0.0.1` to restrict to the local machine. |
| `PI_BRIDGE_PORT` | `8765` | Listen port. |
| `PI_BRIDGE_CWD` | `./workspace` | Working dir = where the agent reads/writes. It **cannot write outside this**. |
| `PI_BRIDGE_TOOLS` | pi default (`read,bash,edit,write`) | Tool allowlist. Use `read,grep,find,ls` for read-only. |
| `PI_BRIDGE_API_KEY` | _(off)_ | If set, requires `Authorization: Bearer <key>`. |
| `PI_BRIDGE_ALLOW_ORIGIN` | `*` | CORS `Access-Control-Allow-Origin`. Set to your Open WebUI origin for browser/Direct-Connection use. |
| `PI_SHOW_TOOLS` | _(off)_ | `1` to inline tool activity as `` `[tool: ...]` `` in the reply. |
| `PI_THINKING` | `off` | `pi --thinking` level. |

## Deployment patterns

### A. Single machine

Bridge, `pi`, and your LLM backend all on one box. Point Open WebUI (or any
client) at `http://localhost:8765/v1`. Simplest setup.

### B. Shared Open WebUI server, agent on each user's own PC

Each user runs `pi` + the bridge **on their own machine** (so the agent edits
*their* local files), while a shared Open WebUI server provides the UI.

This works cleanly because Open WebUI's
**[Direct Connections](https://docs.openwebui.com/)** are made **from the
browser**, not the server. The browser and the bridge are on the same PC, so the
connection URL is just `http://localhost:8765/v1` — **no server→client
networking required.**

Requirements for this mode (all handled by the bridge):
- **CORS** — mandatory for browser-origin requests. Set `PI_BRIDGE_ALLOW_ORIGIN`
  to your Open WebUI origin (e.g. `http://owui.example.com:3000`).
- **API key** — set `PI_BRIDGE_API_KEY` and enter the same value as the
  connection's API key in Open WebUI.
- **Bind to `127.0.0.1`** so no other host on the network can reach the agent.

A step-by-step Japanese guide is in [`docs/COMPANY_ja.md`](docs/COMPANY_ja.md).

## Security

The bridge can run an agent with `bash` and `write` access. Anything typed in the
chat may execute on the host.

- Scope the agent: `PI_BRIDGE_TOOLS=read,grep,find,ls` for read-only, and keep
  `PI_BRIDGE_CWD` pointed at a dedicated folder.
- Restrict the network: bind `127.0.0.1` and set `PI_BRIDGE_API_KEY` unless you
  fully trust everything that can reach the port.
- `pi` is launched with `--approve`, which trusts project-local `.pi/` and
  `AGENTS.md` in the working folder. Don't point `PI_BRIDGE_CWD` at untrusted
  repositories, or remove `--approve` from `pi_bridge.py`.

## Implementation notes (the non-obvious bits)

- `pi -p` waits for **stdin EOF**; the bridge spawns it with `stdin=DEVNULL` to
  avoid hanging.
- The conversation is passed as a **CLI argument**, not as an `@file` attachment
  (attachments leak the temp filename into the prompt and confuse the model).
  It falls back to a temp file only for very long inputs.
- `--offline` disables `pi`'s startup network calls (not the LLM call) for faster,
  more reliable spawns.
- `pi`'s `write`/`edit` tools are sandboxed to the working directory — set
  `PI_BRIDGE_CWD` to wherever you want generated files to land.
- One `pi` process is spawned per request (cold start). For heavy use, a resident
  `pi --mode rpc` design would be faster.

## License

[MIT](LICENSE)
