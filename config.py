import os

# Путь к базе данных
DB_PATH = os.getenv("DB_PATH", "/opt/polymarket-bot/bot.db")

# Настройки планировщика (интервал сканирования в секундах)
SCANNER_INTERVAL_SECONDS = int(os.getenv("SCANNER_INTERVAL_SECONDS", 60))

# Основные настройки сети
POLYMARKET_HOST = os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com")

# ── Белый список: Регулярные выражения для детекции киберспортивных игр ───────
CYBERSPORT_GAMES = {
    r"\bcs2\b": "CS2", r"\bcounter-strike\b": "CS2", r"\bcs:go\b": "CS2", r"\bcsgo\b": "CS2",
    r"\bblast\b": "CS2", r"\biem\b": "CS2", r"\bpgl\b": "CS2", r"\besl\b": "CS2",
    
    r"\bdota\b": "Dota 2", r"\bti13\b": "Dota 2", r"\binternational\b": "Dota 2",
    
    r"\bvalorant\b": "Valorant", r"\bvct\b": "Valorant",
    
    r"\bleague of legends\b": "LoL", r"\blol\b": "LoL",
    r"\blck\b": "LoL", r"\blpl\b": "LoL", r"\blec\b": "LoL", r"\blcs\b": "LoL", r"\bmsi\b": "LoL",
    
    r"\brainbow six\b": "Rainbow Six", r"\br6\b": "Rainbow Six",
    r"\brocket league\b": "Rocket League", r"\brlcs\b": "Rocket League",
    r"\boverwatch\b": "Overwatch", r"\bowl\b": "Overwatch",
    r"\bcall of duty\b": "CoD", r"\bcod\b": "CoD",
    r"\bstarcraft\b": "StarCraft", r"\bsc2\b": "StarCraft",
    r"\bapex\b": "Apex Legends",
    r"\bfortnite\b": "Fortnite",
}

# ── Чёрный список: Исключаем политику, экономику, шоубиз и традиционный спорт ──
MARKET_BLACKLIST = [
    "election", "president", "biden", "trump", "democrat", "republican", 
    "house of", "senate", "crypto", "bitcoin", "ethereum", "fed ", "interest rate",
    "gdp", "inflation", "celeb", "oscar", "movie", "box office", "album", "unemployment",
    "supreme court", "congress", "white house", "primaries", "premier league", "bundesliga",
    "la liga", "serie a", "champions league", "world cup", "football", "soccer", "liverpool", "epl"
]

# ── Дефолтные настройки для Дашборда (Streamlit) ─────────────────────────────
DEFAULT_STRATEGY = {
    "entry_max_prob": 0.15,
    "entry_hours_before": 24,
    "bet_size": 50.0
}

DEFAULT_MARKET_FILTERS = {
    "games": ["CS2", "Dota 2", "Valorant", "LoL"],
    "market_types": ["match_winner", "map1", "map2"]
}
