#!/bin/bash
# deploy.sh — первичный деплой на VPS (Debian)
# Запускать от root: bash deploy.sh

set -e

REPO_URL="https://github.com/YOUR_USERNAME/polymarket-bot.git"
APP_DIR="/opt/polymarket-bot"
PYTHON="python3"
PIP="pip3"

echo "================================================"
echo "  Polymarket Paper Bot — деплой"
echo "================================================"

# ── 1. Системные зависимости ─────────────────────────────────────────────────
echo "[1/7] Обновление пакетов..."
apt-get update -qq
apt-get install -y -qq git python3 python3-pip python3-venv

# ── 2. Swap 512MB (страховка от OOM на 1GB RAM) ──────────────────────────────
echo "[2/7] Настройка swap..."
if [ ! -f /swapfile ]; then
    fallocate -l 512M /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "  Swap 512MB создан"
else
    echo "  Swap уже существует, пропускаем"
fi

# ── 3. Клонируем репозиторий ─────────────────────────────────────────────────
echo "[3/7] Клонирование репозитория..."
if [ -d "$APP_DIR" ]; then
    echo "  Директория существует, делаем git pull..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ── 4. Виртуальное окружение + зависимости ───────────────────────────────────
echo "[4/7] Установка зависимостей..."
cd "$APP_DIR"
$PYTHON -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate
echo "  Зависимости установлены"

# ── 5. systemd сервис: бот ───────────────────────────────────────────────────
echo "[5/7] Создание systemd сервиса бота..."
cat > /etc/systemd/system/polymarket-bot.service << EOF
[Unit]
Description=Polymarket Paper Trading Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:$APP_DIR/bot.log
StandardError=append:$APP_DIR/bot.log

[Install]
WantedBy=multi-user.target
EOF

# ── 6. systemd сервис: дашборд ───────────────────────────────────────────────
echo "[6/7] Создание systemd сервиса дашборда..."
cat > /etc/systemd/system/polymarket-dashboard.service << EOF
[Unit]
Description=Polymarket Paper Bot Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/streamlit run dashboard.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
Restart=always
RestartSec=10
StandardOutput=append:$APP_DIR/dashboard.log
StandardError=append:$APP_DIR/dashboard.log

[Install]
WantedBy=multi-user.target
EOF

# ── 7. Запуск ────────────────────────────────────────────────────────────────
echo "[7/7] Запуск сервисов..."
systemctl daemon-reload

systemctl enable polymarket-bot
systemctl enable polymarket-dashboard

systemctl restart polymarket-bot
systemctl restart polymarket-dashboard

sleep 3

echo ""
echo "================================================"
echo "  Готово!"
echo "================================================"
echo ""
echo "  Дашборд:  http://217.60.248.13:8501"
echo ""
echo "  Статус бота:"
systemctl is-active polymarket-bot && echo "  ✅ bot      — running" || echo "  ❌ bot      — failed"
systemctl is-active polymarket-dashboard && echo "  ✅ dashboard — running" || echo "  ❌ dashboard — failed"
echo ""
echo "  Логи бота:      tail -f $APP_DIR/bot.log"
echo "  Логи дашборда:  tail -f $APP_DIR/dashboard.log"
echo ""
