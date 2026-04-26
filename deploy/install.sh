#!/bin/bash
# Xserver VPS への中古10サイト横断リサーチ Web アプリ デプロイスクリプト
# 既存サービスに影響を与えないよう /opt/research-tool/ 配下で隔離して動作させる
#
# 実行: bash install.sh
# 必須: root or sudo 権限

set -euo pipefail

APP_USER=research
APP_DIR=/opt/research-tool
REPO_URL="https://github.com/yoshidatoso2265-alt/research-tool.git"
APP_PORT=8501
SUBDOMAIN="research.irodori-system.com"

echo "=== 1/8: APT パッケージ更新 ==="
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    git curl ca-certificates \
    nginx certbot python3-certbot-nginx \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libxss1 libasound2

echo "=== 2/8: 専用ユーザー $APP_USER 作成 ==="
if ! id -u $APP_USER >/dev/null 2>&1; then
    useradd -r -m -s /bin/bash $APP_USER
fi

echo "=== 3/8: リポジトリ clone ==="
if [ -d "$APP_DIR" ]; then
    cd $APP_DIR && sudo -u $APP_USER git pull
else
    git clone $REPO_URL $APP_DIR
    chown -R $APP_USER:$APP_USER $APP_DIR
fi

echo "=== 4/8: Python venv + 依存関係 ==="
sudo -u $APP_USER bash << EOF
cd $APP_DIR
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
python -m playwright install chromium
EOF

echo "=== 5/8: Streamlit credentials 事前設定 ==="
sudo -u $APP_USER mkdir -p /home/$APP_USER/.streamlit
sudo -u $APP_USER tee /home/$APP_USER/.streamlit/credentials.toml > /dev/null << 'EOF'
[general]
email = ""
EOF
sudo -u $APP_USER tee /home/$APP_USER/.streamlit/config.toml > /dev/null << 'EOF'
[server]
headless = true
port = 8501
address = "127.0.0.1"
[browser]
gatherUsageStats = false
EOF

echo "=== 6/8: systemd service 登録 ==="
cp $APP_DIR/deploy/research-tool.service /etc/systemd/system/research-tool.service
systemctl daemon-reload
systemctl enable research-tool
systemctl restart research-tool

echo "=== 7/8: nginx 設定（既存設定には影響なし）==="
cp $APP_DIR/deploy/nginx-research.conf /etc/nginx/sites-available/research-tool
ln -sf /etc/nginx/sites-available/research-tool /etc/nginx/sites-enabled/research-tool
nginx -t
systemctl reload nginx

echo "=== 8/8: Let's Encrypt SSL ==="
echo "サブドメイン $SUBDOMAIN の DNS A レコードが 162.43.41.97 を指していることを確認してください"
echo "DNS 反映後、以下を手動で実行: certbot --nginx -d $SUBDOMAIN"
echo ""
echo "=== ✅ インストール完了 ==="
echo "URL: http://$SUBDOMAIN  (HTTPS は certbot 後)"
echo "ステータス確認: systemctl status research-tool"
echo "ログ: journalctl -u research-tool -f"
