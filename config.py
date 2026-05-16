import os

# ── БАЗА ДАННЫХ ─────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "/opt/polymarket-bot/bot.db")

# ── ПЛАНИРОВЩИК (ТАЙМЕРЫ) ───────────────────────────────────────────────────
SCANNER_INTERVAL_SECONDS = int(os.getenv("SCANNER_INTERVAL_SECONDS", 60))
TRACKER_INTERVAL_SECONDS = int(os.getenv("TRACKER_INTERVAL_SECONDS", 60))

# ── СЕТЬ И API ──────────────────────────────────────────────────────────────
POLYMARKET_HOST = os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com")

# ── БЕЛЫЙ СПИСОК (ИГРЫ + ТОП КОМАНДЫ) ───────────────────────────────────────
CYBERSPORT_GAMES = {
    # CS2 / CS:GO
    r"\bcs2\b": "CS2", r"\bcounter-strike\b": "CS2", r"\bcs:go\b": "CS2", r"\bcsgo\b": "CS2",
    r"\bblast\b": "CS2", r"\biem\b": "CS2", r"\bpgl\b": "CS2", r"\besl\b": "CS2",
    
    # Dota 2
    r"\bdota\b": "Dota 2", r"\bti13\b": "Dota 2", r"\binternational\b": "Dota 2",
    r"\briyadh\b": "Dota 2",
    
    # Valorant & LoL
    r"\bvalorant\b": "Valorant", r"\bvct\b": "Valorant",
    r"\bleague of legends\b": "LoL", r"\blol\b": "LoL",
    r"\blck\b": "LoL", r"\blpl\b": "LoL", r"\blec\b": "LoL", r"\blcs\b": "LoL", r"\bmsi\b": "LoL",
    
    # Сигнатурные команды (если в тайтле нет названия игры)
    r"\bfaeze\b|\bnavi\b|\bnatus vincere\b|\bvirtus\.pro\b|\bvp\b": "CS2",
    r"\bspirit\b|\bfalcons\b|\bg2\b|\bteam liquid\b|\bliquid\b": "Dota 2",
    r"\bvitality\b|\bmouz\b|\bheroic\b|\bastralis\b": "CS2",
    r"\bbetboom\b|\bgladiators\b|\btundra\b|\bog\b|\bxtreme\b": "Dota 2",
    r"\bt1\b|\bgen\.g\b|\bfnatic\b|\bcloud9\b|\bc9\b|\bsentinels\b": "LoL",
}

# ── ЧЁРНЫЙ СПИСОК (ИСКЛЮЧЕНИЯ) ──────────────────────────────────────────────
MARKET_BLACKLIST = [
    "election", "president", "biden", "trump", "democrat", "republican", 
    "house of", "senate", "crypto", "bitcoin", "ethereum", "fed ", "interest rate",
    "gdp", "inflation", "celeb", "oscar", "movie", "box office", "album", "unemployment",
    "supreme court", "congress", "white house", "primaries", "premier league", "bundesliga",
    "la liga", "serie a", "champions league", "world cup", "football", "soccer", "liverpool", "epl"
]

# ── ДЕФОЛТЫ ДЛЯ ДАШБОРДА (STREAMLIT) ────────────────────────────────────────
DEFAULT_STRATEGY = {
    "entry_max_prob": 0.15,
    "entry_hours_before": 24,
    "bet_size": 50.0
}

DEFAULT_MARKET_FILTERS = {
    "games": ["CS2", "Dota 2", "Valorant", "LoL"],
    "market_types": ["match_winner", "map1", "map2"]
}
