# pi-openwebui-bridge

[`pi` コーディングエージェント](https://github.com/earendil-works/pi-mono)
（`pi-coding-agent`）を [Open WebUI](https://github.com/open-webui/open-webui)
（や任意の OpenAI 互換クライアント）から **1つのモデルとして選べるようにする**、
依存ゼロの **OpenAI 互換 HTTP シム**です。

リクエストごとに `pi` を起動し、エージェントの出力を OpenAI のチャット補完
（SSE ストリーミング）として返します。エージェントのツール
（`read`/`edit`/`write`/`bash`）も使えるので、**ファイル編集やコマンド実行を伴う
本物のコーディングエージェントを、Open WebUI のチャットからそのまま動かせます**。
推論には `pi` が向いている任意のローカル LLM（llama.cpp、Ollama など）を使います。

> ⚠️ **これは shell とファイル書き込み権限を持つ自律エージェントを、bridge を動かした
> マシン上で実行します。** 公開・共有する前に必ず [セキュリティ](#セキュリティ) を読んでください。

## 仕組み

```
Open WebUI / OpenAI クライアント
        │  POST /v1/chat/completions  (OpenAI互換, SSE)
        ▼
   pi_bridge.py  (:8765)
        │  spawn:  pi -p --mode json --no-session --offline --approve ...
        ▼
      pi (コーディングエージェント)
        │  OpenAI互換API
        ▼
  LLM バックエンド  (llama.cpp サーバ / Ollama / …)
```

エンドポイント:
- `GET /v1/models` — `PI_BRIDGE_MODELS` で定義したモデル一覧を返す。
- `POST /v1/chat/completions` — 会話を直列化し `pi` を実行、その JSON イベント列を
  解析してアシスタントのテキストを返す（ストリーミング／非ストリーミング両対応）。

## 必要なもの

- **`pi`**（pi-coding-agent） — `PATH` 上に置くか `PI_BIN` でパス指定。
  [pi-mono のリリース](https://github.com/earendil-works/pi-mono/releases)から入手。
- **Python 3.8 以上** — 標準ライブラリのみ。`pip install` 不要。
- **OpenAI 互換の LLM バックエンド** — `pi` が `~/.pi/agent/models.json` で参照する
  もの（例: llama.cpp サーバ、Ollama）。

## クイックスタート

```powershell
# Windows PowerShell（Linux/macOS は環境変数の書き方を適宜読み替え）
$env:PI_BRIDGE_MODELS = "my-agent=--provider <provider> --model <model-id>"
python pi_bridge.py
```

クライアントの接続先を `http://localhost:8765/v1` にするだけ（`PI_BRIDGE_API_KEY` を
設定しない限り API キーは何でも可）。Open WebUI では **OpenAI API 接続**としてこの
Base URL を追加します。

より詳しい例は [`start_bridge.example.ps1`](start_bridge.example.ps1) を参照。

## 設定（環境変数）

設定はすべて環境変数で行います:

| 変数 | 既定値 | 説明 |
|---|---|---|
| `PI_BRIDGE_MODELS` | `pi-agent` | 公開するモデル。`id=<pi の引数>;id2=<pi の引数>`。引数が空なら pi 既定。 |
| `PI_BIN` | `pi.exe` | `pi` 実行ファイルのパス（`PATH` 上にあるなら省略可）。 |
| `PI_BRIDGE_HOST` | `0.0.0.0` | バインド先。`127.0.0.1` でローカル限定。 |
| `PI_BRIDGE_PORT` | `8765` | 待ち受けポート。 |
| `PI_BRIDGE_CWD` | `./workspace` | エージェントの作業フォルダ＝読み書き先。**この外には書けない。** |
| `PI_BRIDGE_TOOLS` | pi 既定 (`read,bash,edit,write`) | ツールの許可リスト。読み取り専用は `read,grep,find,ls`。 |
| `PI_BRIDGE_API_KEY` | _(無効)_ | 設定すると `Authorization: Bearer <key>` を要求。 |
| `PI_BRIDGE_ALLOW_ORIGIN` | `*` | CORS の `Access-Control-Allow-Origin`。ブラウザ/Direct Connection では OWUI のオリジンを指定。 |
| `PI_SHOW_TOOLS` | _(無効)_ | `1` でツール実行を `` `[tool: ...]` `` として本文に表示。 |
| `PI_THINKING` | `off` | `pi --thinking` のレベル。 |

## 構成パターン

### A. 単一マシン

bridge・`pi`・LLM バックエンドを1台に。Open WebUI（や任意のクライアント）の接続先を
`http://localhost:8765/v1` にするだけ。最もシンプル。

### B. 共有 Open WebUI サーバ ＋ 各自の PC でエージェント

各ユーザが **自分のマシン**で `pi` ＋ bridge を動かし（＝エージェントが**自分の**ローカル
ファイルを編集）、UI は共有の Open WebUI サーバを使う構成。

これがうまくいくのは、Open WebUI の
**[Direct Connections](https://docs.openwebui.com/)** が
**サーバではなくブラウザから**接続するため。ブラウザと bridge は同じ PC 上にあるので、
接続 URL は `http://localhost:8765/v1` でよく、**サーバ→クライアント方向の通信が一切不要**。

このモードに必要なこと（すべて bridge 側で対応済み）:
- **CORS** — ブラウザ発信のため必須。`PI_BRIDGE_ALLOW_ORIGIN` を Open WebUI の
  オリジン（例 `http://owui.example.com:3000`）に設定。
- **API キー** — `PI_BRIDGE_API_KEY` を設定し、同じ値を Open WebUI の接続キーに入れる。
- **`127.0.0.1` バインド** — NW 上の他ホストからエージェントに到達させない。

ステップごとの手順は [`docs/COMPANY_ja.md`](docs/COMPANY_ja.md) にあります。

## セキュリティ

bridge は `bash`・`write` 権限を持つエージェントを動かせます。チャットに書いた内容が
ホスト上で実行されうる、という前提で扱ってください。

- エージェントを絞る: 読み取り専用は `PI_BRIDGE_TOOLS=read,grep,find,ls`、
  `PI_BRIDGE_CWD` は専用フォルダに限定。
- ネットワークを絞る: `127.0.0.1` バインド＋`PI_BRIDGE_API_KEY`（ポートに到達できる
  すべてを信頼できる場合を除く）。
- `pi` は `--approve` 付きで起動し、作業フォルダの `.pi/` と `AGENTS.md` を信頼して
  読み込みます。信頼できないリポジトリを `PI_BRIDGE_CWD` にしない、または
  `pi_bridge.py` から `--approve` を外してください。

## 実装メモ（ハマりどころ）

- `pi -p` は **stdin の EOF を待つ**。ハング回避のため bridge は `stdin=DEVNULL` で起動。
- 会話は **コマンドライン引数**で渡す（`@file` 添付だと一時ファイル名がプロンプトに
  漏れてモデルが混乱する）。非常に長い入力のときだけ一時ファイルにフォールバック。
- `--offline` は `pi` の起動時ネットワーク処理だけを無効化（LLM 呼び出しには影響なし）。
  起動を速く・安定させる。
- `pi` の `write`/`edit` は作業フォルダにサンドボックス化されている。生成物を置きたい
  場所を `PI_BRIDGE_CWD` で指定する。
- リクエストごとに `pi` を1プロセス起動（コールドスタート）。高頻度なら常駐型の
  `pi --mode rpc` 設計の方が速い。

## ライセンス

[MIT](LICENSE)
