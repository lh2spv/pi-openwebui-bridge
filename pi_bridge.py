#!/usr/bin/env python3
"""
pi-openwebui-bridge
===================
OpenAI 莠呈鋤縺ｮ阮・＞ HTTP 繧ｷ繝縲０pen WebUI 縺九ｉ縲・繝｢繝・Ν縲阪→縺励※ pi-coding-agent
(@earendil-works/pi, Windows 繝阪う繝・ぅ繝・pi.exe) 繧貞他縺ｳ蜃ｺ縺帙ｋ繧医≧縺ｫ縺吶ｋ縲・
  Open WebUI (WSL2 Docker)
      | OpenAI 謗･邯・ http://host.docker.internal:8765/v1  (key: 菴輔〒繧ょ庄)
      v
  pi_bridge.py (Windows host :8765)
      | spawn: pi.exe -p --mode json @<conv>  ...
      v
  pi.exe -> llama-cpp :8080 / ollama :11434

萓晏ｭ倥↑縺・讓呎ｺ悶Λ繧､繝悶Λ繝ｪ縺ｮ縺ｿ)縲・python pi_bridge.py 縺ｧ襍ｷ蜍輔・
迺ｰ蠅・､画焚縺ｧ謖吝虚繧貞､画峩:
  PI_BIN          pi 螳溯｡後ヵ繧｡繧､繝ｫ (default: pi.exe = PATH上のpi、または絶対パス)
  PI_BRIDGE_HOST  bind host  (default: 0.0.0.0  竊・繧ｳ繝ｳ繝・リ縺九ｉ蛻ｰ驕斐＆縺帙ｋ縺溘ａ)
  PI_BRIDGE_PORT  bind port  (default: 8765)
  PI_BRIDGE_CWD   pi 縺ｮ菴懈･ｭ繝・ぅ繝ｬ繧ｯ繝医Μ=繧ｨ繝ｼ繧ｸ繧ｧ繝ｳ繝医′隗ｦ繧九ヵ繧ｩ繝ｫ繝
                  (default: <縺薙・繧ｹ繧ｯ繝ｪ繝励ヨ縺ｮ繝輔か繝ｫ繝>\\workspace)
  PI_BRIDGE_TOOLS pi 縺ｫ貂｡縺吶ヤ繝ｼ繝ｫ allowlist縲ゆｾ・"read,grep,find,ls" 縺ｧ隱ｭ縺ｿ蜿悶ｊ蟆ら畑縲・                  譛ｪ險ｭ螳壹↑繧・pi 譌｢螳・(read,bash,edit,write = 繝輔Ν/譖ｸ霎ｼ縺ｿ蜿ｯ)縲・  PI_BRIDGE_MODELS  OWUI 縺ｫ蜃ｺ縺吶Δ繝・Ν荳隕ｧ "陦ｨ遉ｺid=pi蠑墓焚 ; ..." 蠖｢蠑上・                    萓・ "pi-gemma-e2b=--model llama-cpp/gemma-4-E2B;pi-gemma-12b=--provider ollama --model gemma4:latest"
                    譛ｪ險ｭ螳壹↑繧・"pi-agent"(=pi 譌｢螳・ 1蛟九・  PI_SHOW_TOOLS   "1" 縺ｧ縲√ヤ繝ｼ繝ｫ螳溯｡後ｒ譛ｬ譁・↓ [tool: ...] 縺ｨ縺励※蟾ｮ縺苓ｾｼ繧(蜿ｯ隕門喧)縲・  PI_THINKING     pi --thinking 繝ｬ繝吶Ν (off/minimal/low/medium/high)縲Ｅefault off縲・"""
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PI_BIN = os.environ.get("PI_BIN", "pi.exe")  # PATH 上の pi、または絶対パスを PI_BIN で指定
HOST = os.environ.get("PI_BRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("PI_BRIDGE_PORT", "8765"))
_HERE = os.path.dirname(os.path.abspath(__file__))
CWD = os.environ.get("PI_BRIDGE_CWD", os.path.join(_HERE, "workspace"))
TOOLS = os.environ.get("PI_BRIDGE_TOOLS", "").strip()
SHOW_TOOLS = os.environ.get("PI_SHOW_TOOLS", "") in ("1", "true", "yes")
THINKING = os.environ.get("PI_THINKING", "off").strip()
# CORS: OWUI 縺ｮ Direct Connection 縺ｯ繝悶Λ繧ｦ繧ｶ逋ｺ菫｡縺ｪ縺ｮ縺ｧ蠢・医０WUI 縺ｮ驟堺ｿ｡繧ｪ繝ｪ繧ｸ繝ｳ繧呈欠螳壽耳螂ｨ
# (萓・ http://owui.example.com:3000)縲よ悴險ｭ螳壹↑繧・"*"縲・ALLOW_ORIGIN = os.environ.get("PI_BRIDGE_ALLOW_ORIGIN", "*").strip()
# 險ｭ螳壹☆繧九→繝ｪ繧ｯ繧ｨ繧ｹ繝医↓ Authorization: Bearer <key> 繧定ｦ∵ｱゅ０WUI 縺ｮ謗･邯・Key 縺ｫ蜷悟､繧貞・繧後ｋ縲・API_KEY = os.environ.get("PI_BRIDGE_API_KEY", "").strip()


def _parse_models():
    raw = os.environ.get("PI_BRIDGE_MODELS", "").strip()
    if not raw:
        return {"pi-agent": []}  # pi 譌｢螳壹・繝ｭ繝舌う繝/繝｢繝・Ν
    out = {}
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            name, args = chunk.split("=", 1)
            out[name.strip()] = shlex.split(args.strip())
        else:
            out[chunk] = []
    return out or {"pi-agent": []}


MODELS = _parse_models()


def _serialize_messages(messages):
    """OWUI 縺ｮ messages[] 繧・(system_text, conversation_text) 縺ｫ螟画鋤縲・""
    sys_parts, convo = [], []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):  # OpenAI 縺ｮ繝槭Ν繝√ヱ繝ｼ繝・content
            content = "".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            )
        content = (content or "").strip()
        if not content:
            continue
        if role == "system":
            sys_parts.append(content)
        elif role == "assistant":
            convo.append(f"Assistant: {content}")
        else:
            convo.append(f"User: {content}")
    return "\n".join(sys_parts), "\n\n".join(convo)


# Windows 縺ｮ繧ｳ繝槭Φ繝峨Λ繧､繝ｳ髟ｷ荳企剞(~32767)縺ｫ蟇ｾ縺吶ｋ螳牙・繝槭・繧ｸ繝ｳ縲・# 縺薙ｌ譛ｪ貅縺ｪ繧我ｼ夊ｩｱ繧堤峩謗･ argv 縺ｧ貂｡縺・@file 縺縺ｨ繝｢繝・Ν縺ｫ繝輔ぃ繧､繝ｫ蜷阪′貍上ｌ縺ｦ豺ｷ荵ｱ縺吶ｋ縺溘ａ)縲・_ARG_LIMIT = 28000


def _build_cmd(model_args, conversation_text, conv_file, sys_file):
    # --approve: 髱槫ｯｾ隧ｱ(-p)縺ｧ繧ゆｽ懈･ｭ繝輔か繝ｫ繝縺ｮ .pi/AGENTS.md/繧ｹ繧ｭ繝ｫ遲峨ｒ菫｡鬆ｼ縺励※隱ｭ縺ｿ霎ｼ繧縲・    # (髱槫ｯｾ隧ｱ繝｢繝ｼ繝峨・繝医Λ繧ｹ繝医・繝励Ο繝ｳ繝励ヨ繧貞・縺輔★縲∵悴蛻､譁ｭ縺縺ｨ譌｢螳壹〒縺薙ｌ繧峨ｒ辟｡隕悶☆繧九◆繧・
    cmd = [PI_BIN, "-p", "--mode", "json", "--no-session", "--offline", "--approve"]
    if THINKING and THINKING != "off":
        cmd += ["--thinking", THINKING]
    if TOOLS:
        cmd += ["--tools", TOOLS]
    if sys_file:
        cmd += ["--append-system-prompt", sys_file]
    cmd += list(model_args)
    if conv_file:  # 髟ｷ縺吶℃繧句ｴ蜷医・縺ｿ繝輔ぃ繧､繝ｫ豺ｻ莉倥↓繝輔か繝ｼ繝ｫ繝舌ャ繧ｯ
        cmd += [f"@{conv_file}"]
    else:
        cmd += [conversation_text]
    return cmd


def _iter_pi_text(model_args, system_text, conversation_text):
    """pi 繧・spawn 縺励√ユ繧ｭ繧ｹ繝域妙迚・縺ｨ莉ｻ諢上〒繝・・繝ｫ逞戊ｷ｡)繧・yield 縺吶ｋ generator縲・""
    os.makedirs(CWD, exist_ok=True)
    conversation_text = conversation_text or "User: (no input)"
    conv_path = None
    sys_path = None
    try:
        if len(conversation_text) >= _ARG_LIMIT:
            cfd, conv_path = tempfile.mkstemp(suffix=".md", prefix="pi_conv_", dir=CWD)
            with os.fdopen(cfd, "w", encoding="utf-8") as f:
                f.write(conversation_text)
        if system_text:
            sfd, sys_path = tempfile.mkstemp(suffix=".md", prefix="pi_sys_", dir=CWD)
            with os.fdopen(sfd, "w", encoding="utf-8") as f:
                f.write(system_text)

        cmd = _build_cmd(model_args, conversation_text, conv_path, sys_path)
        proc = subprocess.Popen(
            cmd, cwd=CWD, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "message_update":
                ame = ev.get("assistantMessageEvent") or {}
                if ame.get("type") == "text_delta":
                    yield ame.get("delta", "")
            elif t == "tool_execution_start" and SHOW_TOOLS:
                yield f"\n`[tool: {ev.get('toolName')}]`\n"
        err = proc.stderr.read()
        proc.wait()
        if proc.returncode != 0:
            yield f"\n\n[pi-bridge error rc={proc.returncode}] {err.strip()[:500]}"
    finally:
        for p in (conv_path, sys_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[pi-bridge] " + (fmt % args) + "\n")

    def _set_cors(self):
        # send_response 縺ｨ end_headers 縺ｮ髢薙〒蜻ｼ縺ｶ縺薙→
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
        # CORS 繝励Μ繝輔Λ繧､繝・        self.send_response(204)
        self._set_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _authorized(self):
        if not API_KEY:
            return True
        auth = self.headers.get("Authorization", "")
        return auth.startswith("Bearer ") and auth[7:].strip() == API_KEY

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self._set_cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            now = int(time.time())
            self._send_json({
                "object": "list",
                "data": [
                    {"id": mid, "object": "model", "created": now, "owned_by": "pi"}
                    for mid in MODELS
                ],
            })
        else:
            self._send_json({"status": "ok", "service": "pi-bridge", "models": list(MODELS)})

    def do_POST(self):
        # 蜈医↓繝懊ョ繧｣繧貞ｿ・★隱ｭ縺ｿ蛻・ｋ (keep-alive 謗･邯壹・蜿悶ｊ縺薙⊂縺・豺ｷ邱壹ｒ髦ｲ縺・
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""

        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send_json({"error": "not found"}, 404)
            return
        if not self._authorized():
            self._send_json({"error": "unauthorized"}, 401)
            return
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": "bad request"}, 400)
            return

        model_id = payload.get("model", "pi-agent")
        model_args = MODELS.get(model_id, MODELS.get("pi-agent", []))
        stream = bool(payload.get("stream", False))
        system_text, conversation_text = _serialize_messages(payload.get("messages", []))
        cid = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(time.time())

        if stream:
            self.send_response(200)
            self._set_cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            def sse(obj):
                self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode("utf-8"))
                self.wfile.flush()

            sse({"id": cid, "object": "chat.completion.chunk", "created": created,
                 "model": model_id,
                 "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
            try:
                for piece in _iter_pi_text(model_args, system_text, conversation_text):
                    if not piece:
                        continue
                    sse({"id": cid, "object": "chat.completion.chunk", "created": created,
                         "model": model_id,
                         "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]})
            except BrokenPipeError:
                return
            sse({"id": cid, "object": "chat.completion.chunk", "created": created,
                 "model": model_id,
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            text = "".join(_iter_pi_text(model_args, system_text, conversation_text))
            self._send_json({
                "id": cid, "object": "chat.completion", "created": created, "model": model_id,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })


def main():
    print(f"[pi-bridge] pi      = {PI_BIN}")
    print(f"[pi-bridge] cwd     = {CWD}")
    print(f"[pi-bridge] tools   = {TOOLS or 'pi default (read,bash,edit,write)'}")
    print(f"[pi-bridge] models  = {dict((k, ' '.join(v) or 'pi-default') for k,v in MODELS.items())}")
    print(f"[pi-bridge] cors    = {ALLOW_ORIGIN}")
    print(f"[pi-bridge] auth    = {'on (API key required)' if API_KEY else 'off'}")
    print(f"[pi-bridge] listen  = http://{HOST}:{PORT}/v1")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
