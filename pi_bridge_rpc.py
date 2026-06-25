#!/usr/bin/env python3
"""
pi-openwebui-bridge (RPC 常駐版・実験)
=====================================
pi_bridge.py の派生。リクエストごとに pi を起動する代わりに、
`pi --mode rpc` を常駐させて使い回し、プロセス起動コスト(コールドスタート)を消す。

  - モデルごとに 1 常駐プロセス。起動時にウォームアップ。
  - リクエスト処理: new_session でリセット → prompt 送信 → text_delta を集めて
    agent_end まで。OWUI は毎回フル履歴を送るのでセッションは毎回リセットする。
  - 画像は RPC の images(base64) で直接渡す(一時ファイル不要)。
  - 同時リクエストはプロセス単位の Lock で直列化(各PC1ユーザ想定)。

環境変数は pi_bridge.py と同じ。ただし既定ポートは 8766(-p 版 8765 と並走比較用)。
"""
import base64
import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PI_BIN = os.environ.get("PI_BIN", "pi.exe")  # PATH 上の pi、または絶対パスを PI_BIN で指定
HOST = os.environ.get("PI_BRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("PI_BRIDGE_PORT", "8766"))
_HERE = os.path.dirname(os.path.abspath(__file__))
CWD = os.environ.get("PI_BRIDGE_CWD", os.path.join(_HERE, "workspace"))
TOOLS = os.environ.get("PI_BRIDGE_TOOLS", "").strip()
SHOW_TOOLS = os.environ.get("PI_SHOW_TOOLS", "") in ("1", "true", "yes")
THINKING = os.environ.get("PI_THINKING", "off").strip()
ALLOW_ORIGIN = os.environ.get("PI_BRIDGE_ALLOW_ORIGIN", "*").strip()
API_KEY = os.environ.get("PI_BRIDGE_API_KEY", "").strip()

_MIME = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
_IMG_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
            "image/gif": "gif", "image/webp": "webp"}


def _parse_models():
    raw = os.environ.get("PI_BRIDGE_MODELS", "").strip()
    if not raw:
        return {"pi-agent": []}
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


def _parse_data_url(url):
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    try:
        header, b64 = url.split(",", 1)
    except ValueError:
        return None
    mime = header[5:].split(";")[0].lower()
    try:
        base64.b64decode(b64)  # 妥当性確認のみ
    except Exception:
        return None
    return b64, _IMG_EXT.get(mime, "png")  # (base64文字列, ext)


def _serialize_messages(messages):
    sys_parts, convo = [], []
    last_user_images = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        msg_images = []
        if isinstance(content, list):
            texts = []
            for p in content:
                if not isinstance(p, dict):
                    continue
                t = p.get("type")
                if t == "text":
                    texts.append(p.get("text", ""))
                elif t == "image_url":
                    iu = p.get("image_url")
                    u = iu.get("url") if isinstance(iu, dict) else iu
                    img = _parse_data_url(u)
                    if img:
                        msg_images.append(img)
            content = "".join(texts)
        content = (content or "").strip()
        if role == "user" and msg_images:
            last_user_images = msg_images
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


class PiRpc:
    """1モデル分の常駐 pi --mode rpc プロセス。"""

    def __init__(self, model_args):
        self.model_args = model_args
        self.lock = threading.Lock()
        self.events = queue.Queue()
        self.proc = None
        self._start()

    def _cmd(self):
        cmd = [PI_BIN, "--mode", "rpc", "--no-session", "--offline", "--approve"]
        if THINKING and THINKING != "off":
            cmd += ["--thinking", THINKING]
        if TOOLS:
            cmd += ["--tools", TOOLS]
        return cmd + list(self.model_args)

    def _start(self):
        os.makedirs(CWD, exist_ok=True)
        self.proc = subprocess.Popen(
            self._cmd(), cwd=CWD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        p = self.proc
        threading.Thread(target=self._reader, args=(p,), daemon=True).start()
        sys.stderr.write(f"[pi-bridge-rpc] started pid={p.pid} args={' '.join(self.model_args) or 'pi-default'}\n")

    def _reader(self, proc):
        buf = b""
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:                       # JSONL: \n のみで分割
                line, buf = buf.split(b"\n", 1)
                if line.endswith(b"\r"):
                    line = line[:-1]
                line = line.strip()
                if not line:
                    continue
                try:
                    self.events.put(json.loads(line))
                except Exception:
                    pass

    def _send(self, obj):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def _drain(self):
        try:
            while True:
                self.events.get_nowait()
        except queue.Empty:
            pass

    def _await(self, pred, timeout):
        end = time.time() + timeout
        while time.time() < end:
            try:
                ev = self.events.get(timeout=end - time.time())
            except queue.Empty:
                return False
            if pred(ev):
                return True
        return False

    def run(self, system_text, conversation_text, images):
        """テキスト断片を yield する generator。"""
        self.lock.acquire()
        try:
            if self.proc.poll() is not None:          # 死んでいたら再起動
                self._start()
            self._drain()
            self._send({"type": "new_session"})
            if not self._await(lambda e: e.get("type") == "response" and e.get("command") == "new_session", 30):
                yield "[pi-bridge-rpc] new_session timeout"
                return
            msg = f"{system_text}\n\n{conversation_text}" if system_text else conversation_text
            cmd = {"type": "prompt", "message": msg or "(no input)"}
            if images:
                cmd["images"] = [{"type": "image", "data": b64, "mimeType": _MIME.get(ext, "image/png")}
                                 for b64, ext in images]
            self._send(cmd)
            while True:
                try:
                    ev = self.events.get(timeout=300)
                except queue.Empty:
                    self._send({"type": "abort"})
                    yield "\n[pi-bridge-rpc] timeout"
                    return
                t = ev.get("type")
                if t == "message_update":
                    ame = ev.get("assistantMessageEvent") or {}
                    if ame.get("type") == "text_delta":
                        yield ame.get("delta", "")
                elif t == "tool_execution_start" and SHOW_TOOLS:
                    yield f"\n`[tool: {ev.get('toolName')}]`\n"
                elif t == "response" and ev.get("command") == "prompt" and not ev.get("success", True):
                    yield f"\n[pi-bridge-rpc error] {ev.get('error', '')}"
                    return
                elif t == "agent_end":
                    return
        finally:
            self.lock.release()


_POOL = {}
_POOL_LOCK = threading.Lock()


def _get_rpc(model_id):
    with _POOL_LOCK:
        if model_id not in _POOL:
            _POOL[model_id] = PiRpc(MODELS.get(model_id, MODELS.get("pi-agent", [])))
        return _POOL[model_id]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[pi-bridge-rpc] " + (fmt % args) + "\n")

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
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
            self._send_json({"object": "list", "data": [
                {"id": mid, "object": "model", "created": now, "owned_by": "pi"} for mid in MODELS]})
        else:
            self._send_json({"status": "ok", "service": "pi-bridge-rpc", "models": list(MODELS)})

    def do_POST(self):
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
        rpc = _get_rpc(model_id)
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

            sse({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model_id,
                 "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
            try:
                for piece in rpc.run(system_text, conversation_text, images):
                    if not piece:
                        continue
                    sse({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model_id,
                         "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]})
            except BrokenPipeError:
                return
            sse({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model_id,
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            text = "".join(rpc.run(system_text, conversation_text, images))
            self._send_json({
                "id": cid, "object": "chat.completion", "created": created, "model": model_id,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})


def main():
    print(f"[pi-bridge-rpc] pi      = {PI_BIN}")
    print(f"[pi-bridge-rpc] cwd     = {CWD}")
    print(f"[pi-bridge-rpc] tools   = {TOOLS or 'pi default'}")
    print(f"[pi-bridge-rpc] models  = {dict((k, ' '.join(v) or 'pi-default') for k, v in MODELS.items())}")
    print(f"[pi-bridge-rpc] cors    = {ALLOW_ORIGIN}   auth = {'on' if API_KEY else 'off'}")
    print(f"[pi-bridge-rpc] listen  = http://{HOST}:{PORT}/v1")
    for mid in MODELS:                # 起動時ウォームアップ(初回もコールドにしない)
        _get_rpc(mid)
    print("[pi-bridge-rpc] warmed up resident pi process(es).")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
