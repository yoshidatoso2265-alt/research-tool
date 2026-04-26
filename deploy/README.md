# Xserver VPS デプロイ手順

既存の彩りアプリに**一切影響を与えず**、サブドメインで隔離してデプロイする手順。

## 前提

- Xserver VPS (Ubuntu 22.04, root権限あり)
- IP: 162.43.41.97
- ドメイン: irodori-system.com（既に取得済み）
- サブドメイン: `research.irodori-system.com`（新規）

## 手順

### 1. DNS A レコード追加

XServer VPS パネル → DNS設定 → irodori-system.com の管理画面で：

| ホスト名 | 種別 | 内容 |
|---|---|---|
| `research` | A | `162.43.41.97` |

→ `research.irodori-system.com` が `162.43.41.97` を指すように。
→ DNS反映に最大数時間。

### 2. SSH でサーバへ接続

ローカル PC から：
```bash
ssh root@162.43.41.97
# または ssh -i ~/.ssh/(秘密鍵パス) root@162.43.41.97
```

### 3. インストールスクリプト実行

サーバ上で以下を実行：
```bash
cd /tmp
git clone https://github.com/yoshidatoso2265-alt/research-tool.git
cd research-tool/deploy
sudo bash install.sh
```

これで以下が自動セットアップされる：
- 専用ユーザー `research` 作成
- `/opt/research-tool/` にコード配置（既存ディレクトリと完全分離）
- Python venv + Playwright Chromium インストール
- systemd サービス `research-tool.service` 登録
- nginx 設定（**既存サイト設定には影響なし**、新規 .conf ファイルとして追加）
- Streamlit が `127.0.0.1:8501` で listen、外部からは nginx 経由のみ

### 4. SSL 証明書取得（DNS反映後）

```bash
sudo certbot --nginx -d research.irodori-system.com
```

→ 自動で nginx に 443 ブロックが追加され、HTTPS化される。

### 5. アクセス確認

```
https://research.irodori-system.com
```

## 既存アプリへの影響を防ぐ仕組み

| 項目 | 隔離方法 |
|---|---|
| ファイル | `/opt/research-tool/` 配下のみ（既存 `/var/www/` `/home/` は触らない） |
| ユーザー | 専用 `research` ユーザーで実行 |
| ポート | `127.0.0.1:8501`（外部公開なし、nginx経由のみ） |
| nginx | 新規 `.conf` を `sites-available/research-tool` として追加。既存サイトの `.conf` には触らない |
| systemd | 新規サービスのみ登録 |

## 運用コマンド

```bash
# 状態確認
sudo systemctl status research-tool

# ログ
sudo journalctl -u research-tool -f

# 再起動
sudo systemctl restart research-tool

# 停止
sudo systemctl stop research-tool

# 更新（GitHub の最新を pull → 再起動）
cd /opt/research-tool
sudo -u research git pull
sudo systemctl restart research-tool

# アンインストール（残骸クリーンアップ）
sudo systemctl stop research-tool
sudo systemctl disable research-tool
sudo rm /etc/systemd/system/research-tool.service
sudo rm /etc/nginx/sites-enabled/research-tool /etc/nginx/sites-available/research-tool
sudo systemctl reload nginx
sudo rm -rf /opt/research-tool
sudo userdel -r research
```

## 注意

- **bot 検知**: メルカリ・PayPayフリマ等は サーバ IP からのアクセスをブロックする可能性大。家庭用 IP からと比べてヒット率が下がる場合あり
- **メモリ**: Playwright Chromium は1検索で500MB程度使用。同時実行数は控えめに
- **利用規約**: 各サイトのスクレイピングは個人利用範囲内で
