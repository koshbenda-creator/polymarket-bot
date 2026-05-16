# Polymarket Paper Trading Bot

Paper trading бот для Polymarket. Мониторит киберспортивные рынки, симулирует покупку аутсайдеров до матча и продажу при росте цены в лайве.

## Стратегия

- Вход: аутсайдер с вероятностью **< 15%** за **до 24 часов** до матча
- Выход TP: цена выросла на **+200–300%**
- Выход SL: цена упала на **-50%**
- Все рынки киберспорта: CS2, Dota 2, Valorant, LoL и др.

---

## Быстрый старт (VPS)

### 1. Залить код на GitHub

```bash
# Локально
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/polymarket-bot.git
git push -u origin main
```

### 2. Деплой на VPS

```bash
# Подключиться к серверу
ssh root@217.60.248.13

# Скачать и запустить скрипт деплоя
curl -o deploy.sh https://raw.githubusercontent.com/YOUR_USERNAME/polymarket-bot/main/deploy.sh
# Отредактировать REPO_URL внутри deploy.sh
nano deploy.sh  # меняем YOUR_USERNAME на свой

bash deploy.sh
```

### 3. Открыть дашборд

```
http://217.60.248.13:8501
```

---

## Управление сервисами

```bash
# Статус
systemctl status polymarket-bot
systemctl status polymarket-dashboard

# Остановить / запустить
systemctl stop polymarket-bot
systemctl start polymarket-bot

# Логи в реальном времени
tail -f /opt/polymarket-bot/bot.log
tail -f /opt/polymarket-bot/dashboard.log
```

## Обновление после изменений

```bash
# Локально — пушим изменения
git add .
git commit -m "update"
git push

# На сервере
ssh root@217.60.248.13
cd /opt/polymarket-bot
bash update.sh
```

---

## Структура проекта

```
polymarket-bot/
├── main.py          # Точка входа, планировщик
├── scanner.py       # Поиск аутсайдеров (Gamma + CLOB API)
├── tracker.py       # Лайв мониторинг TP/SL (1 Hz)
├── db.py            # SQLite: стратегии, сделки, история
├── dashboard.py     # Streamlit веб-дашборд
├── config.py        # Все параметры
├── requirements.txt
├── deploy.sh        # Первичный деплой
├── update.sh        # Обновление
└── .gitignore
```

---

## Параметры (config.py)

| Параметр | По умолчанию | Описание |
|---|---|---|
| `entry_max_prob` | 0.15 | Макс. вероятность аутсайдера для входа |
| `entry_hours_before` | 24 | За сколько часов до матча входим |
| `take_profit` | 2.0 | TP множитель (2.0 = +200%) |
| `stop_loss` | 0.50 | SL (-50%) |
| `paper_deposit` | 1000 | Стартовый paper баланс |
| `bet_size` | 50 | Размер одной ставки |
| `SCANNER_INTERVAL_SECONDS` | 60 | Частота сканирования |
| `TRACKER_INTERVAL_SECONDS` | 1 | Частота трекинга (лайв) |

---

## Дашборд

Открывается по `http://IP:8501` с любого устройства.

- **Вкладка стратегии** — метрики, графики, таблица сделок, настройки
- **Мониторинг** — все предстоящие события с ценами
- **Сравнение** — A/B тест стратегий на одном экране
- **+ Стратегия** — создать новую стратегию прямо из браузера

Параметры (TP, SL, порог входа, депозит) меняются через дашборд без редактирования кода.
