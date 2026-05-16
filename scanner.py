# scanner.py — поиск аутсайдеров на Polymarket
#
# Использует два API Polymarket:
#   Gamma API  — метаданные рынков (название, теги, время)
#   CLOB API   — текущие цены (order book)

import logging
import requests
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

# ── Ключевые слова для определения киберспорта ──────────────────────────────
ESPORTS_KEYWORDS = [
    "cs2", "counter-strike", "dota", "valorant", "league of legends", "lol",
    "rainbow six", "r6", "rocket league", "overwatch", "call of duty", "cod",
    "starcraft", "apex", "fortnite", "pubg", "esport", "esports",
]

# ── Маппинг: ключевое слово → нормализованное название игры ─────────────────
GAME_MAP = {
    "cs2": "CS2", "counter-strike": "CS2",
    "dota": "Dota 2",
    "valorant": "Valorant",
    "league of legends": "LoL", "lol": "LoL",
    "rainbow six": "Rainbow Six", "r6": "Rainbow Six",
    "rocket league": "Rocket League",
    "overwatch": "Overwatch",
    "call of duty": "CoD", "cod": "CoD",
    "starcraft": "StarCraft",
    "apex": "Apex Legends",
    "fortnite": "Fortnite",
}

# ── Маппинг: ключевые слова в названии рынка → тип рынка ────────────────────
MARKET_TYPE_MAP = {
    "map 1": "map1", "map1": "map1",
    "map 2": "map2", "map2": "map2",
    "map 3": "map3", "map3": "map3",
    "map 4": "map4", "map4": "map4",
    "map 5": "map5", "map5": "map5",
}


# ────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ────────────────────────────────────────────────────────────────────────────

def _detect_game(text):
    t = text.lower()
    for kw, game in GAME_MAP.items():
        if kw in t:
            return game
    return None


def _detect_market_type(question):
    q = question.lower()
    for kw, mtype in MARKET_TYPE_MAP.items():
        if kw in q:
            return mtype
    return "match_winner"


def _is_esports(tags, question):
    combined = " ".join(tags).lower() + " " + question.lower()
    return any(kw in combined for kw in ESPORTS_KEYWORDS)


def _parse_dt(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _now_utc():
    return datetime.now(timezone.utc)


# ────────────────────────────────────────────────────────────────────────────
# Gamma API — список активных рынков
# ────────────────────────────────────────────────────────────────────────────

def fetch_active_markets(limit=500):
    markets = []
    offset = 0
    session = requests.Session()

    while True:
        try:
            resp = session.get(
                f"{GAMMA_API}/markets",
                params={
                    "limit":  limit,
                    "offset": offset,
                    "active": "true",
                    "closed": "false",
                },
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json()
        except Exception as e:
            log.error(f"[Scanner] Gamma API ошибка: {e}")
            break

        if not batch:
            break

        markets.extend(batch)

        if len(batch) < limit:
            break
        offset += limit

    log.info(f"[Scanner] Получено рынков: {len(markets)}")
    return markets


# ────────────────────────────────────────────────────────────────────────────
# CLOB API — текущие цены
# ────────────────────────────────────────────────────────────────────────────

def fetch_prices_batch(token_ids):
    """Батчевый запрос цен. Возвращает {token_id: float}."""
    if not token_ids:
        return {}
    try:
        resp = requests.get(
            f"{CLOB_API}/prices",
            params={"token_ids": ",".join(token_ids)},
            timeout=10,
        )
        resp.raise_for_status()
        return {k: float(v) for k, v in resp.json().items()}
    except Exception as e:
        log.debug(f"[Scanner] CLOB batch price error: {e}")
        return {}


def fetch_price_single(condition_id):
    """Одиночный запрос цены через order book. Возвращает mid-price или None."""
    try:
        resp = requests.get(
            f"{CLOB_API}/book",
            params={"token_id": condition_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        asks = data.get("asks", [])
        bids = data.get("bids", [])
        if not asks:
            return None
        ask = float(asks[0]["price"])
        bid = float(bids[0]["price"]) if bids else ask
        return round((ask + bid) / 2, 4)
    except Exception as e:
        log.debug(f"[Scanner] CLOB single price error: {e}")
        return None


# ────────────────────────────────────────────────────────────────────────────
# Фильтрация рынков
# ────────────────────────────────────────────────────────────────────────────

def filter_markets_for_strategy(markets, strategy):
    params  = strategy["params"]
    filters = strategy["filters"]

    allowed_games  = set(filters.get("games", []))
    allowed_types  = set(filters.get("market_types", ["match_winner"]))
    hours_before   = params.get("entry_hours_before", 24)
    now            = _now_utc()
    deadline       = now + timedelta(hours=hours_before)

    result = []
    for m in markets:
        question = m.get("question", "")
        raw_tags = m.get("tags", [])
        if isinstance(raw_tags, list):
            tags = [t.get("label", "") if isinstance(t, dict) else str(t) for t in raw_tags]
        else:
            tags = []

        if not _is_esports(tags, question):
            continue

        game = _detect_game(" ".join(tags) + " " + question)
        if not game or game not in allowed_games:
            continue

        mtype = _detect_market_type(question)
        if mtype not in allowed_types:
            continue

        start_dt = _parse_dt(m.get("startDate") or m.get("gameStartTime"))
        if start_dt:
            if start_dt <= now:
                continue
            if start_dt > deadline:
                continue

        m["_game"]  = game
        m["_mtype"] = mtype
        m["_start"] = start_dt
        result.append(m)

    return result


# ────────────────────────────────────────────────────────────────────────────
# Определяем аутсайдера
# ────────────────────────────────────────────────────────────────────────────

def find_underdog(market, max_prob, prices_cache=None):
    """
    Возвращает {"team": str, "price": float} или None.
    Сначала пробуем цены из Gamma (outcomePrices),
    потом из батч-кэша CLOB, потом одиночный запрос.
    """
    import json as _json

    # --- цены ---
    outcome_prices = market.get("outcomePrices")
    p0, p1 = None, None

    if outcome_prices:
        try:
            if isinstance(outcome_prices, str):
                outcome_prices = _json.loads(outcome_prices)
            p0 = float(outcome_prices[0])
            p1 = float(outcome_prices[1])
        except Exception:
            pass

    if p0 is None:
        tokens = market.get("clobTokenIds", [])
        if isinstance(tokens, str):
            try:
                tokens = _json.loads(tokens)
            except Exception:
                tokens = []

        if tokens and len(tokens) >= 2:
            if prices_cache:
                p0 = prices_cache.get(tokens[0])
                p1 = prices_cache.get(tokens[1])
            if p0 is None:
                p0 = fetch_price_single(tokens[0])
            if p1 is None and len(tokens) > 1:
                p1 = 1 - p0 if p0 is not None else None

    if p0 is None or p1 is None:
        return None

    # --- названия исходов ---
    outcomes = market.get("outcomes", ["Team A", "Team B"])
    if isinstance(outcomes, str):
        try:
            outcomes = _json.loads(outcomes)
        except Exception:
            outcomes = ["Team A", "Team B"]

    label0 = outcomes[0] if len(outcomes) > 0 else "Team A"
    label1 = outcomes[1] if len(outcomes) > 1 else "Team B"

    for price, label in [(p0, label0), (p1, label1)]:
        if 0 < price < max_prob:
            return {"team": label, "price": round(price, 4)}

    return None


# ────────────────────────────────────────────────────────────────────────────
# Публичная функция — вызывается из main.py
# ────────────────────────────────────────────────────────────────────────────

def scan_markets():
    log.info("[Scanner] Сканирование начато...")

    strategies = [s for s in get_all_strategies() if s["is_active"]]
    if not strategies:
        log.info("[Scanner] Нет активных стратегий.")
        return

    all_markets = fetch_active_markets()
    if not all_markets:
        log.warning("[Scanner] Рынков не получено.")
        return

    # Батчевый запрос цен для всех token_id сразу (экономим запросы)
    import json as _json
    all_token_ids = []
    for m in all_markets:
        tokens = m.get("clobTokenIds", [])
        if isinstance(tokens, str):
            try:
                tokens = _json.loads(tokens)
            except Exception:
                tokens = []
        all_token_ids.extend(tokens[:2])

    prices_cache = fetch_prices_batch(all_token_ids) if all_token_ids else {}
    log.info(f"[Scanner] Получено цен из CLOB: {len(prices_cache)}")

    for strategy in strategies:
        strategy_id = strategy["id"]
        params      = strategy["params"]
        max_prob    = params.get("entry_max_prob", 0.15)
        bet_size    = params.get("bet_size", 50.0)

        open_market_ids = {t["market_id"] for t in get_open_trades(strategy_id)}
        candidates = filter_markets_for_strategy(all_markets, strategy)

        log.info(
            f"[Scanner] '{strategy['name']}': "
            f"{len(candidates)} кандидатов (порог <{max_prob*100:.0f}%)"
        )

        entered = 0
        for market in candidates:
            market_id = market.get("conditionId") or market.get("id", "")

            # обновляем монитор для дашборда (все рынки, не только под порог)
            any_underdog = find_underdog(market, max_prob=1.0, prices_cache=prices_cache)
            if any_underdog:
                upsert_monitored_market(
                    market_id      = market_id,
                    event_name     = market.get("question", ""),
                    game           = market["_game"],
                    market_type    = market["_mtype"],
                    team           = any_underdog["team"],
                    current_price  = any_underdog["price"],
                    match_starts_at= (
                        market["_start"].isoformat() if market["_start"] else None
                    ),
                )

            # не дублируем открытые сделки
            if market_id in open_market_ids:
                continue

            # ищем аутсайдера под порог стратегии
            underdog = find_underdog(market, max_prob=max_prob, prices_cache=prices_cache)
            if not underdog:
                continue

            trade_id = open_trade(
                strategy_id    = strategy_id,
                market_id      = market_id,
                event_name     = market.get("question", ""),
                game           = market["_game"],
                market_type    = market["_mtype"],
                team           = underdog["team"],
                entry_price    = underdog["price"],
                bet_size       = bet_size,
                match_starts_at= (
                    market["_start"].isoformat() if market["_start"] else None
                ),
            )
            open_market_ids.add(market_id)
            entered += 1
            log.info(
                f"[Scanner] ✅ {market.get('question', '')} | "
                f"{underdog['team']} @ {underdog['price']*100:.1f}% | "
                f"trade #{trade_id}"
            )

        log.info(f"[Scanner] '{strategy['name']}': открыто {entered} новых сделок.")

    log.info("[Scanner] Сканирование завершено.")
