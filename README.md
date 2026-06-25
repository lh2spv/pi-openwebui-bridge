# pi-openwebui-bridge

ふだん使う AI チャット画面（**Open WebUI**）から、**あなたのパソコンの中で実際に
ファイルを作ったり直したりしてくれる AI（コーディングエージェント `pi`）**を
使えるようにする、小さな“橋渡し”プログラムです。

> ⚠️ この AI は、あなたのパソコン上で本当にファイルを書き換えたり、コマンドを実行
> したりします。チャットに書いた内容がそのまま実行されるので、指示の内容には
> 気をつけてください。

---

# パソコンに詳しくない人向け：セットアップ手順（Windows）

**この通りに上から順番にやれば使えるようになります。** 所要 15〜30 分。
むずかしい言葉は出てきますが、書いてある操作だけやればOKです。

## 先に教えてもらうこと

自分一人で全部用意するのは大変なので、ふつうは詳しい人（管理者）が「サーバ」を
用意します。次の2つを教えてもらってください。メモしておきます。

- ① **AI サーバの場所（URL）とモデル名**　例: URL `http://192.168.1.10:8080/v1` ／ モデル名 `gemma4`
- ② **Open WebUI の場所（URL）** とログイン用アカウント　例: `http://192.168.1.10:3000`

> 全部自分でやる場合は、別途 llama.cpp か Ollama（AI本体）と Open WebUI を
> 動かしておく必要があります。これは少し上級者向けです。

## ステップ1：Python（パイソン）を入れる

「橋渡しプログラム」を動かすのに必要です。

1. https://www.python.org/downloads/ を開き、黄色い「**Download Python**」ボタンをクリック。
2. ダウンロードしたファイルを実行。最初の画面で
   **「Add python.exe to PATH」のチェックを必ず入れて**から「Install Now」。 ← ここ重要！
3. 確認：スタートメニューで「**PowerShell**」を開き、`python --version` と打って Enter。
   `Python 3.13.x` のように表示されればOK。

## ステップ2：AI 本体（pi）を入れる

1. https://github.com/earendil-works/pi-mono/releases を開く。
2. 一番上（最新版）の「Assets」を開き、**`pi-windows-x64.zip`** をダウンロード。
3. ダウンロードした ZIP を右クリック →「**すべて展開**」。
4. 出てきたフォルダの中に **`pi.exe`** があります。フォルダごと分かりやすい場所
   （例 `C:\pi`）に移動。**`pi.exe` の場所（例 `C:\pi\pi.exe`）をメモ**しておく。

## ステップ3：この「橋渡しプログラム」を入れる

1. **このページの上のほうにある緑色の「Code」ボタン → 「Download ZIP」**をクリック。
2. ZIP を右クリック →「すべて展開」。出てきたフォルダを分かりやすい場所
   （例 `C:\pi-bridge`）に置く。

## ステップ4：AI に「サーバの場所」を教える

1. **Windows キー + R** を同時押し → `cmd` と入力して Enter（黒い画面が開く）。
2. 黒い画面に次を打って Enter（設定を置くフォルダを作ります）:
   ```
   mkdir %USERPROFILE%\.pi\agent
   ```
3. **Windows キー + R** → `notepad` と入力して Enter（メモ帳が開く）。
4. 下をそのまま貼り付け、`<サーバのURL>` と `<モデル名>`（①で教わった値）を書き換える:
   ```json
   {
     "providers": {
       "myllm": {
         "baseUrl": "<サーバのURL>",
         "api": "openai-completions",
         "apiKey": "dummy",
         "models": [
           { "id": "<モデル名>", "name": "AIサーバ", "input": ["text", "image"],
             "contextWindow": 8192, "maxTokens": 4096 }
         ]
       }
     }
   }
   ```
5. メモ帳で「ファイル → 名前を付けて保存」。
   - 「ファイルの種類」を **「すべてのファイル」** に変更。
   - ファイル名の欄に **`%USERPROFILE%\.pi\agent\models.json`** と入力して保存。

## ステップ5：起動ファイルを用意する

1. `C:\pi-bridge` の中の **`start_bridge.example.bat`** をコピーし、
   名前を **`start_bridge.bat`**（`.example` を消す）に変更。
2. その `start_bridge.bat` を右クリック →「**編集**」（メモ帳で開く）。
3. 次の2行を、自分の値に書き換える:
   ```
   set "PI_BIN=C:\pi\pi.exe"
   set "PI_BRIDGE_MODELS=pi-agent=--provider myllm --model <モデル名>"
   ```
   （`PI_BIN` はステップ2でメモした `pi.exe` の場所、`<モデル名>` は①の値）
4. 上書き保存。**※ 日本語は書き足さないこと**（このファイルは半角英数だけにする）。

## ステップ6：起動する

- **`start_bridge.bat` をダブルクリック**。
- 黒い画面が開いて `listen = http://0.0.0.0:8765/v1` のような行が出れば動いています。
- **この黒い画面は閉じないでおく**（閉じると AI も止まります）。

## ステップ7：Open WebUI に登録する（最後の設定）

1. ブラウザで Open WebUI（②の URL）を開いてログイン。
2. 右上のアイコン → **設定（Settings）→ 接続（Connections）**。
3. **「＋」で「OpenAI API」の接続を追加**。
4. 次を入力して保存:
   - URL（Base URL）: **`http://localhost:8765/v1`**
   - API Key: **`x`**（何でもよい）
5. チャット画面の上にあるモデル選択で **`pi-agent`** を選ぶ。

## 動いたか確認する

チャットに次のように送ってみてください:

> 今いるフォルダに memo.txt を作って、中に「テスト」と書いて。

AI が「作りました」と返事をして、実際にファイルができていれば**成功**です 🎉
（作ったファイルは `start_bridge.bat` と同じ場所の `workspace` フォルダにできます。）

---

# うまくいかないとき

| 症状 | 対処 |
|---|---|
| `python` と打っても「認識されません」 | ステップ1の「Add python.exe to PATH」チェックを忘れている。Python を入れ直す。 |
| 黒い画面が一瞬で消える | `start_bridge.bat` をダブルクリックではなく、右クリック→編集で中身を確認。`PI_BIN` のパスが正しいか、`pi.exe` が実在するか確認。 |
| `models.json` が保存できない | ステップ4-2 の `mkdir` を実行したか確認。フォルダ `%USERPROFILE%\.pi\agent` が無いと保存できません。 |
| Open WebUI にモデル `pi-agent` が出ない | 黒い画面（bridge）が起動したままか、接続 URL が `http://localhost:8765/v1` になっているか確認。 |
| 返事はくるがファイルができない | `start_bridge.bat` の `PI_BRIDGE_TOOLS` に `write` が入っているか確認（既定は入っています）。 |
| 返事が来ない／エラー | ①のサーバ（AI本体）が起動しているか、URL・モデル名が正しいか、管理者に確認。 |

---

# 詳しい人・管理者向け

ここからは技術的な説明です。

## これは何か

`pi`（[pi-coding-agent](https://github.com/earendil-works/pi-mono)）を OpenAI 互換 API
として公開する、依存ゼロ（Python 標準ライブラリのみ）の薄い HTTP シムです。
リクエストごとに `pi -p --mode json ...` を起動し、出力を OpenAI のチャット補完
（SSE）に変換して返します。`read`/`edit`/`write`/`bash` ツールに対応。

```
Open WebUI ──▶ pi_bridge.py(:8765) ──▶ pi ──▶ LLM(llama.cpp / Ollama …)
```

## 設定（環境変数）

| 変数 | 既定 | 説明 |
|---|---|---|
| `PI_BRIDGE_MODELS` | `pi-agent` | 公開モデル。`id=<pi 引数>;...` |
| `PI_BIN` | `pi.exe` | pi 実行ファイル（PATH 上なら省略可） |
| `PI_BRIDGE_HOST` | `0.0.0.0` | バインド先。ローカル限定は `127.0.0.1` |
| `PI_BRIDGE_PORT` | `8765` | ポート |
| `PI_BRIDGE_CWD` | `./workspace` | 作業フォルダ＝保存先（この外には書けない） |
| `PI_BRIDGE_TOOLS` | pi 既定 | ツール許可。読み取り専用は `read,grep,find,ls` |
| `PI_BRIDGE_API_KEY` | _(無効)_ | 設定で `Authorization: Bearer <key>` を要求 |
| `PI_BRIDGE_ALLOW_ORIGIN` | `*` | CORS 許可オリジン（ブラウザ Direct Connection 用） |
| `PI_SHOW_TOOLS` | _(無効)_ | `1` でツール実行を本文表示 |
| `PI_THINKING` | `off` | `pi --thinking` レベル |

## 構成パターン

- **A. 単一マシン** — bridge・pi・LLM を1台に。接続先 `http://localhost:8765/v1`。
- **B. 共有 Open WebUI サーバ ＋ 各自 PC でエージェント** — 各自が自分のローカル
  ファイルを編集。OWUI の Direct Connection はブラウザ発信なので接続先は
  `http://localhost:8765/v1` でよく、サーバ→クライアントの通信は不要。
  CORS（`PI_BRIDGE_ALLOW_ORIGIN`）と API キー（`PI_BRIDGE_API_KEY`）、`127.0.0.1`
  バインドを使う。手順は [`docs/COMPANY_ja.md`](docs/COMPANY_ja.md)。

## セキュリティ

bridge は `bash`/`write` 可能なエージェントを動かせます。読み取り専用にするなら
`PI_BRIDGE_TOOLS=read,grep,find,ls`、ネットワークを絞るなら `127.0.0.1` バインド＋
`PI_BRIDGE_API_KEY`。`pi` は `--approve` 付き起動で作業フォルダの `.pi/`・`AGENTS.md`
を信頼読み込みするため、信頼できないフォルダを `PI_BRIDGE_CWD` にしないこと。

## 実装メモ（ハマりどころ）

- `pi -p` は **stdin の EOF を待つ**ため `stdin=DEVNULL` で起動。
- 会話は **CLI 引数**で渡す（`@file` 添付だと一時ファイル名が漏れてモデルが混乱）。
- **画像入力**対応: OWUI から添付された画像（最新ユーザーメッセージ分）を一時ファイルに
  保存し `pi @画像` で渡す。利用には vision 対応モデル＋llama.cpp なら `--mmproj` 付き起動が
  必要。**音声は pi 自体が非対応**（`input` は `text`/`image` のみ）。
- `--offline` は起動時ネットワーク処理のみ無効化（LLM 呼び出しには影響なし）。
- `.bat` は **ASCII で保存**する（cmd は UTF-8 コメントを誤解析する）。
- リクエストごとに pi を1プロセス起動（コールドスタート）。高頻度なら `pi --mode rpc` 常駐型が速い。

## ライセンス

[MIT](LICENSE)
