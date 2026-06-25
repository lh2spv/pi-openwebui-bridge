#!/usr/bin/env python3
"""
pi-openwebui-bridge
===================
OpenAI 互換の薄い HTTP シム。Open WebUI から「1モデル」として pi-coding-agent
(@earendil-works/pi, Windows ネイティブ pi.exe) を呼び出せるようにする。

  Open WebUI (WSL2 Docker)
      | OpenAI 接続: http://host.docker.internal:8765/v1  (key: 何でも可)
      v
  pi_bridge.py (Windows host :8765)
      | spawn: pi.exe -p --mode json @<conv>  ...
      v
  pi.exe -> llama-cpp :8080 / ollama :11434

依存なし(標準ライブラリのみ)。 python pi_bridge.py で起動。

環境変数で挙動を変更:
  PI_BIN          pi 実行ファイル (default: pi.exe = PATH 上の pi、または絶対パス指定)
  PI_BRIDGE_HOST  bind host  (default: 0.0.0.0  ← コンテナから到達させるため)
  PI_BRIDGE_PORT  bind port  (default: 8765)
  PI_BRIDGE_CWD   pi の作業ディレクトリ=エージェントが触るフォルダ
                  (default: <このスクリプトのフォルダ>\\workspace)
  PI_BRIDGE_TOOLS pi に渡すツール allowlist。例 "read,grep,find,ls" で読み取り専用。
                  未設定なら pi 既定 (read,bash,edit,write = フル/書込み可)。
  PI_BRIDGE_MODELS  OWUI に出すモデル一覧 "表示id=pi引数 ; ..." 形式。
                    例: "pi-gemma-e2b=--model llama-cpp/gemma-4-E2B;pi-gemma-12b=--provider ollama --model gemma4:latest"
                    未設定なら "pi-agent"(=pi 既定) 1個。
  PI_SHOW_TOOLS   "1" で、ツール実行を本文に [tool: ...] として差し込む(可視化)。
  PI_THINKING     pi --thinking レベル (off/minimal/low/medium/high)。default off。
"""
import base64
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
# CORS: OWUI の Direct Connection はブラウザ発信なので必須。OWUI の配信オリジンを指定推奨
# (例: http://owui.example.com:3000)。未設定なら "*"。
ALLOW_ORIGIN = os.environ.get("PI_BRIDGE_ALLOW_ORIGIN", "*").strip()
# 設定するとリクエストに Authorization: Bearer <key> を要求。OWUI の接続 Key に同値を入れる。
API_KEY = os.environ.get("PI_BRIDGE_API_KEY", "").strip()


def _parse_models():
    raw = os.environ.get("PI_BRIDGE_MODELS", "").strip()
    if not raw:
        return {"pi-agent": []}  # pi 既定プロバイダ/モデル
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


_IMG_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
            "image/gif": "gif", "image/webp": "webp"}


def _parse_data_url(url):
    """data:image/png;base64,XXXX -> (bytes, ext)。それ以外は None。"""
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    try:
        header, b64 = url.split(",", 1)
    except ValueError:
        return None
    mime = header[5:].split(";")[0].lower()
    try:
        return base64.b64decode(b64), _IMG_EXT.get(mime, "png")
    except Exception:
        return None


def _serialize_messages(messages):
    """OWUI の messages[] を (system_text, conversation_text, images) に変換。
    images は最後の user メッセージに添付された画像 [(bytes, ext), ...]
    (pi は -p では会話を1プロンプトに直列化するため、画像は最新ターン分のみ添付する)。"""
    sys_parts, convo = [], []
    last_user_images = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        msg_images = []
        if isinstance(content, list):  # OpenAI のマルチパート content
            texts = []
            for p in content:
                if not isinstance(p, dict):
                    continue
                t = p.get("type")
                if t == "text":
                    texts.append(p.get("text", ""))
                elif t == "image_url":
                    iu = p.get("image_url")
                    url = iu.get("url") if isinstance(iu, dict) else iu
                    img = _parse_data_url(url)
                    if img:
                        msg_images.append(img)
            content = "".join(texts)
        content = (content or "").strip()
        if role == "user" and msg_images:
            last_user_images = msg_images  # 最新の user 画像で上書き
        if not content and not msg_images:
            continue
        if not content:
            content = "(image)"
        if role == "system":
            sys_parts.append(content)
        elif role == "assistant":
            convo.append(f"Assistant: {content}")
        else:
            convo.append(f"User: {content}")
    return "\n".join(sys_parts), "\n\n".join(convo), last_user_images


# Windows のコマンドライン長上限(~32767)に対する安全マージン。
# これ未満なら会話を直接 argv で渡す(@file だとモデルにファイル名が漏れて混乱するため)。
_ARG_LIMIT = 28000


def _build_cmd(model_args, conversation_text, conv_file, sys_file, image_files=()):
    # --approve: 非対話(-p)でも作業フォルダの .pi/AGENTS.md/スキル等を信頼して読み込む。
    # (非対話モードはトラストのプロンプトを出さず、未判断だと既定でこれらを無視するため)
    cmd = [PI_BIN, "-p", "--mode", "json", "--no-session", "--offline", "--approve"]
    if THINKING and THINKING != "off":
        cmd += ["--thinking", THINKING]
    if TOOLS:
        cmd += ["--tools", TOOLS]
    if sys_file:
        cmd += ["--append-system-prompt", sys_file]
    cmd += list(model_args)
    for img in image_files:  # 画像は @ファイルで添付 (pi の画像入力方式)
        cmd += [f"@{img}"]
    if conv_file:  # 長すぎる場合のみ会話をファイル添付にフォールバック
        cmd += [f"@{conv_file}"]
    else:
        cmd += [conversation_text]
    return cmd


def _iter_pi_text(model_args, system_text, conversation_text, images=()):
    """pi を spawn し、テキスト断片(と任意でツール痕跡)を yield する generator。"""
    os.makedirs(CWD, exist_ok=True)
    conversation_text = conversation_text or "User: (no input)"
    conv_path = None
    sys_path = None
    img_paths = []
    try:
        for data, ext in images:  # 画像を一時ファイルに保存して pi に @ で渡す
            ifd, ipath = tempfile.mkstemp(suffix="." + ext, prefix="pi_img_", dir=CWD)
            with os.fdopen(ifd, "wb") as f:
                f.write(data)
            img_paths.append(ipath)
        if len(conversation_text) >= _ARG_LIMIT:
            cfd, conv_path = tempfile.mkstemp(suffix=".md", prefix="pi_conv_", dir=CWD)
            with os.fdopen(cfd, "w", encoding="utf-8") as f:
                f.write(conversation_text)
        if system_text:
            sfd, sys_path = tempfile.mkstemp(suffix=".md", prefix="pi_sys_", dir=CWD)
            with os.fdopen(sfd, "w", encoding="utf-8") as f:
                f.write(system_text)

        cmd = _build_cmd(model_args, conversation_text, conv_path, sys_path, img_paths)
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
        for p in (conv_path, sys_path, *img_paths):
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
        # send_response と end_headers の間で呼ぶこと
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
        # CORS プリフライト
        self.send_response(204)
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
        # 先にボディを必ず読み切る (keep-alive 接続の取りこぼし/混線を防ぐ)
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
        system_text, conversation_text, images = _serialize_messages(payload.get("messages", []))
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
                for piece in _iter_pi_text(model_args, system_text, conversation_text, images):
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
            text = "".join(_iter_pi_text(model_args, system_text, conversation_text, images))
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
