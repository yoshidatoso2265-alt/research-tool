# デプロイ最終ステップ（ユーザー実行）

## ✅ 完了済み（Claude側）

1. **GitHub リポジトリ作成**: https://github.com/yoshidatoso2265-alt/research-tool （プライベート）
2. **コード push**: 2 コミット
3. **DNS A レコード追加**: `research.irodori-system.com` → `162.43.41.97`
4. **デプロイスクリプト作成**: `deploy/install.sh`, `deploy/research-tool.service`, `deploy/nginx-research.conf`
5. **Web app icon 設定**: `77fb3257-fbd1-42b8-adf9-94b19e8812fe.png` を Streamlit のページアイコンに

## 📋 残りのステップ（あなたが実行）

サーバ側は SSH 鍵を使った root アクセスがあなたしか持っていないので、以下を実行してください。

### 方法A: ローカルPCのターミナルから（推奨・速い）

```bash
ssh root@162.43.41.97
```
（SSH鍵 `irodori` を使うので、~/.ssh/config か -i で指定）

ログイン後、サーバ上で以下を1回コピペ実行：

```bash
# 1. リポジトリ取得 + デプロイスクリプト実行（プライベートリポなので gh CLI で認証）
cd /tmp

# プライベートリポ clone のために PAT (Personal Access Token) を使うか、
# SSH key を deploy key として GitHub に登録するのが必要です。
# 一番簡単なのは、ローカルPCで cloneしたコードを scp で上げる方法：

# ローカルPCで:
#   cd ~/OneDrive/デスクトップ
#   tar czf research-tool.tar.gz リサーチ
#   scp research-tool.tar.gz root@162.43.41.97:/tmp/
#
# その後サーバで:
#   cd /tmp && tar xzf research-tool.tar.gz && mv リサーチ research-tool
#   sudo bash research-tool/deploy/install.sh
```

### 方法B: GitHub repo を一時的に Public にする（最速）

1. https://github.com/yoshidatoso2265-alt/research-tool/settings → Change visibility → Public
2. SSH ログイン後、サーバで：
```bash
cd /tmp
git clone https://github.com/yoshidatoso2265-alt/research-tool.git
cd research-tool/deploy
sudo bash install.sh
```
3. デプロイ完了後、もう一度 Settings → Private に戻す

### 方法C: GitHub PAT（Personal Access Token）を使う

1. GitHub → Settings → Developer settings → Personal access tokens → Generate new token (classic)
2. `repo` スコープを付与してトークン取得
3. SSH ログイン後：
```bash
cd /tmp
git clone https://<YOUR_PAT>@github.com/yoshidatoso2265-alt/research-tool.git
cd research-tool/deploy
sudo bash install.sh
```

---

## install.sh が自動でやること

1. apt update + 必要パッケージ (Python, nginx, certbot, Playwright依存ライブラリ)
2. 専用ユーザー `research` 作成（既存ユーザーには影響なし）
3. `/opt/research-tool/` に配置（既存ファイルには触れない）
4. Python venv 作成 + pip install + Playwright Chromium インストール
5. systemd サービス `research-tool.service` 登録（既存サービスには影響なし）
6. nginx 設定追加（**新規 .conf ファイルとして追加、既存サイトには触れない**）
7. SSL は別途 `certbot --nginx -d research.irodori-system.com` で取得

## DNS 反映確認（5分〜数時間）

ローカルPCで：
```bash
nslookup research.irodori-system.com
```
→ `162.43.41.97` が返ってきたらDNS反映済み。

## SSL（HTTPS）取得

DNS反映後、サーバで：
```bash
sudo certbot --nginx -d research.irodori-system.com
```

メールアドレスを聞かれたら入力、規約は agree、HTTPS強制リダイレクトは Yes 推奨。

## アクセス確認

```
https://research.irodori-system.com
```

---

## 既存彩りアプリへの影響を防ぐ仕組み（再掲）

| 隔離項目 | 方法 |
|---|---|
| ファイル | `/opt/research-tool/` のみに配置 |
| ユーザー | 専用 `research` ユーザーで実行 |
| ポート | `127.0.0.1:8501`（外部公開なし、nginx経由のみ） |
| nginx | 既存の `.conf` には触らず、新規 `sites-available/research-tool` を追加 |
| systemd | 新規サービスのみ登録 |
| DNS | 新規 A レコード `research.` のみ追加（既存 `irodori-system.com` `material.` `gencho.` には触らない） |

## トラブル時のロールバック（完全削除）

```bash
sudo systemctl stop research-tool
sudo systemctl disable research-tool
sudo rm /etc/systemd/system/research-tool.service
sudo rm /etc/nginx/sites-enabled/research-tool /etc/nginx/sites-available/research-tool
sudo systemctl reload nginx
sudo rm -rf /opt/research-tool
sudo userdel -r research
```

DNS は VPSパネルから research.irodori-system.com の A レコードを削除。
