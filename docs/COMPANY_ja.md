# 会社向け構成: pi を各Windows、OWUI/llama.cpp は共有Ubuntuサーバ

各人が **自分のWindows PCのローカルファイル** を pi エージェントに編集させつつ、
推論は共有サーバの llama.cpp(Gemma 4)、UI は共有サーバの Open WebUI を使う構成。

## 要点（なぜ成立するか）

OWUI の **Direct Connection はブラウザ発信**（サーバ backend を経由しない）。
ブラウザも bridge も同じPC上にあるので、接続先は `http://localhost:8765` でよく、
**「サーバ → 各PC」への通信は一切不要**。社内NWのインバウンド制限を気にしなくてよい。

```
各Windows PC:
  ブラウザ(OWUI画面) ──(localhost)──▶ bridge :8765 ──▶ pi.exe ──┐
                                            ↑ ローカルファイルを操作   │  client→server(通常)
共有Ubuntuサーバ:                                                    ▼
  Open WebUI (Web配信)                              llama.cpp Gemma4 (例 :8082)
```

データの向き:
- ブラウザ → bridge: **同一PC内 localhost**（サーバ不経由）
- pi → llama.cpp: PC → サーバ（通常の client→server。社内NWで普通は通る）
- 編集対象: **pi が動く各PCのローカルファイル**

---

## A. 管理者が一度だけやること（OWUIサーバ）

1. **Direct Connections を有効化**: 管理者設定 → 設定 → 接続（Connections）で
   ユーザの Direct Connections を許可する。
2. llama.cpp をブラウザ…ではなく **pi から** 叩くので、llama.cpp 側は各PCから到達できる
   ように `--host 0.0.0.0 --port 8080` で起動し、社内NWで 8080 を開けておく。
   （Direct Connection の相手は各PCの bridge であって llama.cpp ではない点に注意）

> 本構成の前提ポート: **llama.cpp = 8080**（共有サーバ）、**OWUI = 3000**（共有サーバ）、
> **bridge = 8765**（各PCの localhost）。

## B. 各Windows PCで一度だけやること

### B-1. pi 本体を入れる
- GitHub Releases の `pi-windows-x64.zip` を展開し `pi.exe` を任意の場所へ（例 `C:\tools\pi\`）。

### B-2. pi のプロバイダを「サーバの llama.cpp」に向ける
`%USERPROFILE%\.pi\agent\models.json`:
```json
{
  "providers": {
    "company-llm": {
      "baseUrl": "http://<サーバのIP>:8080/v1",
      "api": "openai-completions",
      "apiKey": "dummy",
      "models": [
        { "id": "gemma4", "name": "Gemma 4 (company server)",
          "input": ["text", "image"], "contextWindow": 8192, "maxTokens": 4096 }
      ]
    }
  }
}
```

### B-3. bridge を起動（localhost 限定＋APIキー）
`start_bridge.ps1` を会社用に設定して実行:
```powershell
$env:PI_BRIDGE_HOST        = "127.0.0.1"          # ★ 他PCから叩けないよう localhost 限定
$env:PI_BRIDGE_API_KEY     = "各自の秘密キー"      # ★ 同値を OWUI の接続Keyに入れる
$env:PI_BRIDGE_ALLOW_ORIGIN= "http://<サーバのIP>:3000" # ★ OWUI の配信オリジン (scheme+host+port)
$env:PI_BRIDGE_MODELS      = "pi-gemma=--provider company-llm --model gemma4"
$env:PI_BRIDGE_CWD         = "C:\work\myproject"  # エージェントが触れる作業フォルダ
$env:PI_BRIDGE_TOOLS       = "read,grep,find,ls,edit,write,bash"  # 必要に応じ絞る
python pi_bridge.py
```
> Windows のログオン時自動起動にしたい場合は、タスクスケジューラで上記を登録。

## C. 各ユーザが OWUI 画面でやること（1回）

1. ユーザ設定 → 接続（Connections）→ ＋ で接続を追加
2. **Base URL**: `http://localhost:8765/v1`
3. **API Key**: B-3 で設定した各自の秘密キー
4. 保存 → モデル `pi-gemma` を選んでチャット

---

## セキュリティ

- bridge は **127.0.0.1 バインド**なので、他PC・社内NWからは到達不可（自分のブラウザのみ）。
- **APIキー必須**化により、同一PC上の別プロセスからの無断利用も防げる。
- ただし `bash`/`write` 有効＝**チャットの指示が自分のPCで実行される**。作業フォルダ
  (`PI_BRIDGE_CWD`) を限定し、不要なら `PI_BRIDGE_TOOLS=read,grep,find,ls` で読み取り専用に。
- `--approve`（既定で有効）は作業フォルダの `.pi`/`AGENTS.md` を信頼して読む。信頼できない
  リポジトリを作業フォルダにする場合は外す。

## 注意・確認事項

- **HTTPS の OWUI** から `http://localhost:8765` への接続: 主要ブラウザ(Chrome/Edge/Firefox)は
  `localhost` を安全なオリジン扱いするため通常は許可されるが、社内ブラウザ設定次第なので
  最初の1台で疎通を確認すること。ダメな場合は OWUI を http で使うか bridge を https 化。
- OWUI の Direct Connection はマルチユーザ環境で版により挙動差の報告あり
  （open-webui Discussion #15516 等）。利用中の OWUI バージョンで1人ぶん先行検証推奨。
- 推論は全員が共有サーバの llama.cpp を叩く＝**同時実行は llama.cpp の並列数次第**。
  人数が多いなら `--parallel` やキューを検討。

## 動作確認の順番（1台で）

1. PC上で bridge 起動 → `curl http://localhost:8765/v1/models`（APIキー付き）でモデルが返る
2. サーバ llama.cpp へ到達確認 → PC から `curl http://<サーバ>:8080/v1/models`
3. OWUI にログイン → 接続追加 → `pi-gemma` で「FizzBuzzを作って」等 → 作業フォルダに生成されるか確認
