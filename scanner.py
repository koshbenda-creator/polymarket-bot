# scanner.py — поиск аутсайдеров на Polymarket
#
# Gamma API — метаданные + цены (bestBid/bestAsk прямо в ответе)
# CLOB API  — не используется для цен, только как фоллбэк

import logging
import requests
import json as _json
from datetime import datetime, timezone, timedelta

from db import (
    get_all_strategies,
    open_trade,
    get_open_trades,
    upsert_monitored_market,
)

log = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"

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

def _detect_game(search_text):
    """Ищет игру в подготовленном расширенном текстовом блоке."""
    for kw, game in GAME_MAP.items():
        if kw in search_text:
            return game
    return None


def _detect_market_type(question):
    q = question.lower()
    for kw, mtype in MARKET_TYPE_MAP.items():
        if kw in q:
            return mtype
    return "match_winner"


def _parse_dt(dt_str):
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _now_utc():
    return datetime.now(timezone.utc)


# ────────────────────────────────────────────────────────────────────────────
# Gamma API — список активных рынков
# ────────────────────────────────────────────────────────────────────────────

def fetch_active_markets(limit=100, max_markets=5000):
    """
    Получаем все активные рынки с пагинацией.
    """
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

        if not batch or len(batch) == 0:
            break

        markets.extend(batch)
        log.debug(f"[Scanner] Загружено {len(markets)} рынков (offset={offset})")

        if len(batch) < limit:
            break
            
        offset += limit
        if len(markets) >= max_markets:
            log.info(f'[Scanner] Достигнут лимит {max_markets} рынков')
            break

    log.info(f"[Scanner] Получено рынков всего: {len(markets)}")
    return markets


# ────────────────────────────────────────────────────────────────────────────
# Определяем цену из ответа Gamma (без отдельных запросов к CLOB)
# ────────────────────────────────────────────────────────────────────────────

def _get_prices(market):
    """
    Возвращает (p0, p1) для двух исходов рынка.
    Приоритет: outcomePrices → bestBid/bestAsk → None
    """
    # 1. outcomePrices — самый надёжный источник
    outcome_prices = market.get("outcomePrices")
    if outcome_prices:
        try:
            if isinstance(outcome_prices, str):
                outcome_prices = _json.loads(outcome_prices)
            p0 = float(outcome_prices[0])
            p1 = float(outcome_prices[1])
            if 0 < p0 < 1 and 0 < p1 < 1:
                return round(p0, 4), round(p1, 4)
        except Exception:
            pass

    # 2. bestBid / bestAsk — прямо в ответе Gamma
    best_ask = market.get("bestAsk")
    best_bid = market.get("bestBid")
    if best_ask is not None:
        try:
            ask = float(best_ask)
            bid = float(best_bid) if best_bid else ask
            p0 = round((ask + bid) / 2, 4)
            p1 = round(1 - p0, 4)
            if 0 < p0 < 1:
                return p0, p1
        except Exception:
            pass

    # 3. lastTradePrice как последний фоллбэк
    last = market.get("lastTradePrice")
    if last is not None:
        try:
            p0 = round(float(last), 4)
            p1 = round(1 - p0, 4)
            if 0 < p0 < 1:
                return p0, p1
        except Exception:
            pass

    return None, None


# ────────────────────────────────────────────────────────────────────────────
# Фильтрация рынков под параметры стратегии
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
        # Критически важно: пропускаем рынки без токена торговли CLOB
        if not m.get("conditionId"):
            continue

        question = m.get("question", "")
        slug = m.get("slug", "")
        
        # Безопасно достаем название ивента/турнира, если оно есть
        event_data = m.get("event")
        event_title = event_data.get("title", "") if isinstance(event_data, dict) else ""

        # Объединяем все метаданные для поиска ключевых слов киберспорта
        search_text = f"{question} {slug} {event_title}".lower()

        # 1. Проверяем, относится ли к киберспорту
        if not any(kw in search_text for kw in ESPORTS_KEYWORDS):
            continue

        # 2. Определяем конкретную игру
        game = _detect_game(search_text)
        if not game or game not in allowed_games:
            continue

        # 3. Проверяем тип рынка (матч или конкретная карта)
        mtype = _detect_market_type(question)
        if mtype not in allowed_types:
            continue

        # 4. Проверка по времени начала
        start_dt = _parse_dt(
            m.get("startDateIso") or m.get("startDate") or m.get("endDateIso")
        )
        if start_dt:
            if start_dt <= now:
                continue  # Матч уже идет или завершен
            if start_dt > deadline:
                continue  # Матч начнется еще не скоро

        m["_game"]  = game
        m["_mtype"] = mtype
        m["_start"] = start_dt
        result.append(m)

    return result


# ────────────────────────────────────────────────────────────────────────────
# Определяем аутсайдера
# ────────────────────────────────────────────────────────────────────────────

def find_underdog(market, max_prob):
    """
    Возвращает {"team": str, "price": float} или None.
    Ищет исход с ценой < max_prob.
    """
    p0, p1 = _get_prices(market)
    if p0 is None or p1 is None:
        return None

    # названия исходов
    outcomes = market.get("outcomes", ["Yes", "No"])
    if isinstance(outcomes, str):
        try:
            outcomes = _json.loads(outcomes)
        except Exception:
            outcomes = ["Yes", "No"]

    label0 = outcomes[0] if len(outcomes) > 0 else "Yes"
    label1 = outcomes[1] if len(outcomes) > 1 else "No"

    for price, label in [(p0, label0), (p1, label1)]:
        if 0 < price < max_prob:
            return {"team": label, "price": round(price, 4)}

    return None


# ────────────────────────────────────────────────────────────────────────────
# Публичная функция — вызывается из main.py каждые 60 секунд
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

    for strategy in strategies:
        strategy_id = strategy["id"]
        params      = strategy["params"]
        max_prob    = params.get("entry_max_prob", 0.15)
        bet_size    = params.get("bet_size", 50.0)

        open_market_ids = {t["market_id"] for t in get_open_trades(strategy_id)}
        candidates = filter_markets_for_strategy(all_markets, strategy)

        log.info(
            f"[Scanner] '{strategy['name']}': "
            f"{len(candidates)} кандидатов из {len(all_markets)} "
            f"(порог <{max_prob*100:.0f}%)"
        )

        entered = 0
        for market in candidates:
            # Используем строго conditionId для совместимости с CLOB
            market_id = market.get("conditionId")

            # Обновляем монитор для дашборда
            p0, p1 = _get_prices(market)
            if p0 is not None:
                outcomes = market.get("outcomes", ["Yes", "No"])
                if isinstance(outcomes, str):
                    try:
                        outcomes = _json.loads(outcomes)
                    except Exception:
                        outcomes = ["Yes", "No"]
                        
                # Пишем в монитор меньший исход
                if p0 <= p1:
                    mon_price, mon_team = p0, (outcomes[0] if outcomes else "Yes")
                else:
                    mon_price, mon_team = p1, (outcomes[1] if len(outcomes) > 1 else "No")

                upsert_monitored_market(
                    market_id      = market_id,
                    event_name     = market.get("question", ""),
                    game           = market["_game"],
                    market_type    = market["_mtype"],
                    team           = mon_team,
                    current_price  = mon_price,
                    match_starts_at= (
                        market["_start"].isoformat() if market["_start"] else None
                    ),
                )

            # Не дублируем открытые сделки
            if market_id in open_market_ids:
                continue

            # Ищем аутсайдера под порог стратегии
            underdog = find_underdog(market, max_prob=max_prob)
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
