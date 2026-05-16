#!/bin/bash
# update.sh — обновление бота с GitHub
# Запускать от root: bash update.sh

set -e

APP_DIR="/opt/polymarket-bot"

echo "[1/3] Git pull..."
cd "$APP_DIR"
git pull

echo "[2/3] Обновление зависимостей..."
source venv/bin/activate
pip install -r requirements.txt -q
deactivate

echo "[3/3] Перезапуск сервисов..."
systemctl restart polymarket-bot
systemctl restart polymarket-dashboard

sleep 2

echo ""
systemctl is-active polymarket-bot      && echo "✅ bot       — running" || echo "❌ bot       — failed"
systemctl is-active polymarket-dashboard && echo "✅ dashboard — running" || echo "❌ dashboard — failed"
echo ""
echo "Обновление завершено."
