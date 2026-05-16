# config.py — все параметры бота в одном месте

# === Polymarket API ===
POLYMARKET_HOST = "https://clob.polymarket.com"
POLYMARKET_CHAIN_ID = 137  # Polygon

# === Параметры по умолчанию для новой стратегии ===
DEFAULT_STRATEGY = {
    "entry_max_prob": 0.15,      # максимальная вероятность аутсайдера для входа (15%)
    "entry_hours_before": 24,    # за сколько часов до матча входим
    "take_profit": 2.0,          # TP: цена выросла в 2x (200%)
    "stop_loss": 0.50,           # SL: цена упала на 50%
    "paper_deposit": 1000.0,     # стартовый paper баланс в USD
    "bet_size": 50.0,            # размер одной ставки в USD
}

# === Фильтры рынков по умолчанию ===
DEFAULT_MARKET_FILTERS = {
    "games": ["CS2", "Dota 2", "Valorant", "LoL", "Rainbow Six", "Rocket League"],
    "market_types": ["match_winner", "map1", "map2", "map3"],  # map4/map5 выключены
}

# === Мониторинг ===
SCANNER_INTERVAL_SECONDS = 60       # как часто ищем новые позиции
TRACKER_INTERVAL_SECONDS = 1        # как часто проверяем цену в лайве (1 Hz)

# === База данных ===
DB_PATH = "bot.db"

# === Streamlit дашборд ===
DASHBOARD_PORT = 8501
