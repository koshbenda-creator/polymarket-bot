# scanner.py — поиск аутсайдеров на Polymarket
#
# Использует два API Polymarket:
#   Gamma API  — метаданные рынков (название, теги, время) с фильтрацией по Gaming
#   CLOB API   — текущие цены (order book)

import logging
import re
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

# ── Ключевые слова для точного определения игры ─────────────────────────────
# Строго синхронизировано со списком в config.py и dashboard.py
GAME_MAP = {
    "cs2": "CS2", "counter-strike": "CS2",
    "blast premier": "CS2", "iem ": "CS2", "pgl ": "CS2",
    
    "dota": "Dota 2",
    "valorant": "Valorant", "champions tour": "Valorant",
    
    "league of legends": "LoL", "lol": "LoL",
    "lck": "LoL", "lpl": "LoL", "lec": "LoL", "lcs": "LoL", "cblol": "LoL",
    
    "rainbow six": "Rainbow Six", "r6": "Rainbow Six",
    "rocket league": "Rocket League",
    "overwatch": "Overwatch",
    "call of duty": "CoD",  # Защита от Cody Gakpo: ищем только полную фразу
    "starcraft": "StarCraft",
    "apex": "Apex Legends",
    "fortnite": "Fortnite",
}


def _detect_game(market_title: str) -> str | None:
    """Определяет конкретную киберспортивную дисциплину по названию рынка."""
    title_lower = market_title.lower()
    
    for keyword, game_name in GAME_MAP.items():
        # Если ключевое слово длинное или содержит пробелы, проверяем обычным вхождением
        if " " in keyword or len(keyword) > 4:
            if keyword in title_lower:
                return game_name
        else:
            # Короткие теги (lol, lck, cs2, r6) ищем строго как отдельные слова (\b)
            if re.search(r'\b' + re.escape(keyword) + r'\b', title_lower):
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
    """Скачивает активные маркеты, фильтруя их по категории Gaming на стороне API."""
    try:
        # Запрашиваем только маркеты из категории Gaming/Esports
        # Также запрашиваем только активные (not resolved) и не закрытые (open) рынки
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={
                "tag_slug": "gaming",  # Фильтрация на уровне API Polymarket
                "closed": "false",
                "resolved": "false",
                "limit": 100,
            },
            timeout=15
        )
        resp.raise_for_status()
        markets = resp.json()
        
        # На всякий случай делаем fallback на тег esports, если по gaming пусто
        if not markets:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={"tag_slug": "esports", "closed": "false", "resolved": "false", "limit": 100},
                timeout=15
            )
            resp.raise_for_status()
            markets = resp.json()

        valid_markets = []
        for m in markets:
            # Базовые проверки на валидность полей API
            if not m.get("clobTokenIds") or not m.get("outcomePrices"):
                continue
                
            title = m.get("question", "")
            game = _detect_game(title)
            if not game:
                continue  # Пропускаем, если игра не распознана нашими фильтрами

            # Парсинг даты начала матка
            start_dt = None
            if m.get("gameStartTime"):
                try:
                    # Пример: 2026-05-16T22:00:00Z
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
    """Получает точные live-цены (order book) из CLOB API для списка токенов."""
    prices = {}
    if not token_ids:
        return prices
    try:
        # Пакетный запрос цен, чтобы не спамить API
        resp = requests.get(
            f"{CLOB_API}/prices",
            params={"token_ids": token_ids},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        # API возвращает dict { token_id: price_string }
        for t_id, p_str in data.items():
            try:
                prices[t_id] = float(p_str)
            except (ValueError, TypeError):
                pass
    except Exception as e:
        log.error(f"[Scanner] Ошибка CLOB API цен: {e}")
    return prices


def find_underdog(market: dict, max_prob: float, prices_cache: dict) -> dict | None:
    """Ищет в маркете команду-аутсайдера, чья цена ниже установленного порога."""
    outcomes = market["outcomes"]
    tokens = market["clob_token_ids"]
    
    if len(outcomes) != 2 or len(tokens) != 2:
        return None  # Работаем только с бинарными исходами (П1 / П2)

    # Берём live-цену из кэша CLOB, если её нет — используем базовую из Gamma
    p0 = prices_cache.get(tokens[0], None)
    p1 = prices_cache.get(tokens[1], None)
    
    if p0 is None or p1 is None:
        try:
            p0 = float(market["prices"][0])
            p1 = float(market["prices"][1])
        except (IndexError, ValueError, TypeError):
            return None

    # Проверяем условия для каждого исхода
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

    # 1. Скачиваем отфильтрованные киберспортивные рынки через Gamma API
    markets = fetch_gamma_markets()
    log.info(f"[Scanner] Получено {len(markets)} потенциальных киберспортивных рынков.")

    if not markets:
        return

    # 2. Собираем все Token ID для live-цен
    all_token_ids = []
    for m in markets:
        all_token_ids.extend(m["clob_token_ids"])
        
    # Кэшируем live-цены из стакана (CLOB)
    prices_cache = fetch_clob_prices(all_token_ids)

    now_utc = datetime.now(timezone.utc)

    # 3. Обработка рынков для каждой стратегии
    for strategy in active_strategies:
        strategy_id = strategy["id"]
        
        # Распаковываем конфиги из БД
        import json
        params = json.loads(strategy["params"])
        filters = json.loads(strategy["filters"])

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

            # Валидация по фильтрам стратегии
            if game.lower() not in allowed_games:
                continue
            if mtype not in allowed_mtypes:
                continue

            # Проверка времени начала матча
            start_at = market["_start"]
            if start_at:
                # Если матч уже начался или прошел
                if start_at <= now_utc:
                    log.info(f"[MATCH-DEBUG] Матч: '{market['question']}' | Игра: {game} | Статус: УЖЕ ИДЕТ/ПРОШЕЛ")
                    continue
                # Если до матча осталось больше времени, чем разрешено стратегией
                if start_at > now_utc + timedelta(hours=hours_before):
                    continue
            else:
                # Если у рынка вообще нет даты начала — это долгосрочный аутрайт, скипаем
                continue

            # Добавляем или обновляем рынок в таблице мониторинга дашборда
            any_underdog = find_underdog(market, max_prob=1.0, prices_cache=prices_cache)
            if any_underdog:
                upsert_monitored_market(
                    market_id      = market_id,
                    event_name     = market.get("question", ""),
                    game           = game,              # Сохраняется красиво (LoL, CS2)
                    market_type    = mtype,
                    underdog_team  = any_underdog["team"],
                    underdog_price = any_underdog["price"],
                    match_starts_at= market["_start"].isoformat() if market["_start"] else None,
                )

            # Если по этому рынку уже открыта сделка — дублировать нельзя
            if market_id in open_market_ids:
                continue

            # Ищем конкретного аутсайдера под жесткий порог вероятности (например, < 15%)
            underdog = find_underdog(market, max_prob=max_prob, prices_cache=prices_cache)
            if not underdog:
                continue

            # Открываем сделку (симуляция покупки)
            trade_id = open_trade(
                strategy_id    = strategy_id,
                market_id      = market_id,
                event_name     = market.get("question", ""),
                game           = game,              # Сохраняется красиво (LoL, CS2)
                market_type    = mtype,
                team           = underdog["team"],
                entry_price    = underdog["price"],
                bet_size       = bet_size,
                match_starts_at= market["_start"].isoformat() if market["_start"] else None,
            )
            open_market_ids.add(market_id)
            entered += 1
            log.info(
                f"[Scanner] ✅ {market.get('question', '')} | "
                f"{underdog['team']} @ {underdog['price']*100:.1f}% | "
                f"trade #{trade_id}"
            )

        if entered > 0:
            log.info(f"[Scanner] '{strategy['name']}': открыто {entered} новых сделок.")

    log.info("[Scanner] Сканирование успешно завершено.")
