# scanner.py — поиск аутсайдеров на Polymarket
#
# Использует два API Polymarket:
#   Gamma API  — метаданные рынков (название, теги, время)
#   CLOB API   — точные live-цены (order book) через POST-запросы

import logging
import json
import requests
import re
from datetime import datetime, timezone, timedelta

from config import POLYMARKET_HOST
from db import (
    get_all_strategies,
    open_trade,
    get_open_trades,
    upsert_monitored_market,
)

log = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = POLYMARKET_HOST  # https://clob.polymarket.com

# ── Белый список: Точные ключевые слова с границами слов ────────────────────
GAME_MAP = {
    r"\bcs2\b": "CS2", r"\bcounter-strike\b": "CS2", r"\bcs:go\b": "CS2", r"\bcsgo\b": "CS2",
    r"\bblast\b": "CS2", r"\biem\b": "CS2", r"\bpgl\b": "CS2", r"\besl\b": "CS2", r"\bepl\b": "CS2",
    
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

# ── Чёрный список: Исключает политику, экономику и традиционный спорт ───────
BLACKLIST = [
    "election", "president", "biden", "trump", "democrat", "republican", 
    "house of", "senate", "crypto", "bitcoin", "ethereum", "fed ", "interest rate",
    "gdp", "inflation", "celeb", "oscar", "movie", "box office", "album", "unemployment",
    "supreme court", "congress", "white house", "primaries", "premier league", "bundesliga",
    "la liga", "serie a", "champions league", "world cup", "football", "soccer"
]


def _detect_game(market_title: str) -> str | None:
    """Определяет киберспортивную дисциплину по названию рынка (защита регулярками)."""
    title_lower = market_title.lower()
    
    if any(bad_word in title_lower for bad_word in BLACKLIST):
        return None
        
    for pattern, game_name in GAME_MAP.items():
        if re.search(pattern, title_lower):
            return game_name
                
    return None


def _get_market_type(market_title: str) -> str:
    """Определяет тип маркета (победитель матча или конкретная карта)."""
    title_lower = market_title.lower()
    if "map 1" in title_lower:
        return "map1"
    if "map 2" in title_lower:
        return "map2"
    if "map 3" in title_lower:
        return "map3"
    return "match_winner"


def fetch_gamma_markets() -> list[dict]:
    """Скачивает активные маркеты Polymarket."""
    try:
        all_markets = []
        
        for offset in [0, 100, 200, 300, 400]:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={
                    "closed": "false",
                    "resolved": "false",
                    "active": "true",
                    "limit": 100,
                    "offset": offset,
                },
                timeout=15
            )
            resp.raise_for_status()
            chunk = resp.json()
            if not chunk:
                break
            all_markets.extend(chunk)
        
        log.info(f"[Scanner] Gamma API суммарно вернул {len(all_markets)} active рынков для анализа.")

        valid_markets = []
        for m in all_markets:
            if not m.get("clobTokenIds") or not m.get("outcomePrices"):
                continue
                
            title = m.get("question", "")
            game = _detect_game(title)
            if not game:
                continue

            start_dt = None
            if m.get("gameStartTime"):
                try:
                    start_dt = datetime.fromisoformat(m["gameStartTime"].replace("Z", "+00:00"))
                except Exception:
                    pass

            valid_markets.append({
                "id": m.get("conditionId"),
                "question": title,
                "outcomes": eval(m["outcomes"]) if isinstance(m.get("outcomes"), str) else m.get("outcomes", []),
                "clob_token_ids": eval(m["clobTokenIds"]) if isinstance(m["clobTokenIds"], str) else m["clobTokenIds"],
                "prices": eval(m["outcomePrices"]) if isinstance(m["outcomePrices"], str) else m["outcomePrices"],
                "_game": game,
                "_mtype": _get_market_type(title),
                "_start": start_dt
            })
            
        return valid_markets
    except Exception as e:
        log.error(f"[Scanner] Ошибка при получении маркетов с Gamma API: {e}")
        return []


def fetch_clob_prices(token_ids: list[str]) -> dict[str, float]:
    """Получает точные цены из CLOB API через POST запрос, оборачивая в объект token_ids."""
    prices = {}
    if not token_ids:
        return prices
        
    unique_tokens = list(set(token_ids))
    
    try:
        # Polymarket CLOB API ожидает структуру {"token_ids": [...]}
        resp = requests.post(
            f"{CLOB_API}/prices",
            json={"token_ids": unique_tokens},
            timeout=12
        )
        resp.raise_for_status()
        data = resp.json()
        
        # Ответ приходит в виде {"0x...": "0.12", "0x...": "0.88"}
        if isinstance(data, dict):
            for t_id, p_str in data.items():
                try:
                    prices[t_id] = float(p_str)
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        log.error(f"[Scanner] Ошибка отправки POST в CLOB API цен: {e}")
        
    return prices


def find_underdog(market: dict, max_prob: float, prices_cache: dict) -> dict | None:
    """Ищет в маркете команду-аутсайдера, чья цена ниже установленного порога."""
    outcomes = market["outcomes"]
    tokens = market["clob_token_ids"]
    
    if len(outcomes) != 2 or len(tokens) != 2:
        return None

    p0 = prices_cache.get(tokens[0], None)
    p1 = prices_cache.get(tokens[1], None)
    
    if p0 is None or p1 is None:
        try:
            p0 = float(market["prices"][0])
            p1 = float(market["prices"][1])
        except (IndexError, ValueError, TypeError):
            return None

    if 0.01 < p0 <= max_prob:
        return {"team": outcomes[0], "price": p0, "token_id": tokens[0]}
    if 0.01 < p1 <= max_prob:
        return {"team": outcomes[1], "price": p1, "token_id": tokens[1]}
        
    return None


def scan_markets():
    """Основной рабочий цикл сканера."""
    log.info("[Scanner] Запуск сканирования киберспортивных рынков...")
    
    strategies = get_all_strategies()
    active_strategies = [s for s in strategies if s["is_active"]]
    if not active_strategies:
        log.info("[Scanner] Нет активных стратегий. Сканирование пропущено.")
        return

    markets = fetch_gamma_markets()
    log.info(f"[Scanner] После фильтрации по ключевым словам осталось {len(markets)} киберспортивных рынков.")

    if not markets:
        return

    all_token_ids = []
    for m in markets:
        all_token_ids.extend(m["clob_token_ids"])
        
    prices_cache = fetch_clob_prices(all_token_ids)
    now_utc = datetime.now(timezone.utc)

    for strategy in active_strategies:
        strategy_id = strategy["id"]
        
        params = strategy["params"]
        if isinstance(params, str):
            params = json.loads(params)
            
        filters = strategy["filters"]
        if isinstance(filters, str):
            filters = json.loads(filters)

        max_prob = params.get("entry_max_prob", 0.15)
        hours_before = params.get("entry_hours_before", 24)
        bet_size = params.get("bet_size", 50.0)

        allowed_games = [g.lower() for g in filters.get("games", [])]
        allowed_mtypes = filters.get("market_types", [])

        open_trades = get_open_trades(strategy_id)
        open_market_ids = {t["market_id"] for t in open_trades}

        entered = 0

        for market in markets:
            market_id = market["id"]
            game = market["_game"]
            mtype = market["_mtype"]

            log.info(f"[MATCH-DEBUG] Найден подходящий маркет: '{market['question']}' | Игра: {game} | Тип: {mtype}")

            if game.lower() not in allowed_games:
                continue
            if mtype not in allowed_mtypes:
                continue

            start_at = market["_start"]
            if start_at:
                if start_at <= now_utc:
                    log.info(f"[MATCH-DEBUG] Матч уже идет (LIVE): '{market['question']}'")
                if start_at > now_utc + timedelta(hours=hours_before):
                    continue

            # Ищем любого аутсайдера (до 100%), чтобы закинуть в таблицу мониторинга
            any_underdog = find_underdog(market, max_prob=1.0, prices_cache=prices_cache)
            if any_underdog:
                # ВАЖНО: строго под сигнатуру db.py (underdog_team, underdog_price)
                upsert_monitored_market(
                    market_id       = market_id,
                    event_name      = market.get("question", ""),
                    game            = game,
                    market_type     = mtype,
                    underdog_team   = any_underdog["team"],
                    underdog_price  = any_underdog["price"],
                    match_starts_at = market["_start"].isoformat() if market["_start"] else None,
                )

            if market_id in open_market_ids:
                continue

            underdog = find_underdog(market, max_prob=max_prob, prices_cache=prices_cache)
            if not underdog:
                continue

            trade_id = open_trade(
                strategy_id    = strategy_id,
                market_id      = market_id,
                event_name     = market.get("question", ""),
                game           = game,
                market_type    = mtype,
                team           = underdog["team"],
                entry_price    = underdog["price"],
                bet_size       = bet_size,
                match_starts_at= market["_start"].isoformat() if market["_start"] else None,
            )
            open_market_ids.add(market_id)
            entered += 1
            log.info(
                f"[Scanner] ✅ Открыта сделка: {market.get('question', '')} | "
                f"{underdog['team']} @ {underdog['price']*100:.1f}% | trade #{trade_id}"
            )

        if entered > 0:
            log.info(f"[Scanner] '{strategy['name']}': открыто {entered} новых сделок.")

    log.info("[Scanner] Сканирование успешно завершено.")
