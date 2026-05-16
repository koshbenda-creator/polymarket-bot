# tracker.py — лайв мониторинг открытых сделок
#
# Вызывается каждую секунду из main.py.
# Для каждой открытой сделки:
#   1. Получает текущую цену с CLOB API
#   2. Проверяет TP / SL условия
#   3. Закрывает сделку если условие сработало

import logging
import requests
from datetime import datetime, timezone

from db import (
    get_all_strategies,
    get_open_trades,
    close_trade,
    record_balance,
    get_strategy,
)

log = logging.getLogger(__name__)

CLOB_API = "https://clob.polymarket.com"

# Кэш: market_id → token_id (чтобы не парсить каждую секунду)
_token_cache: dict[str, str] = {}


# ────────────────────────────────────────────────────────────────────────────
# Получение цены
# ────────────────────────────────────────────────────────────────────────────

def _get_token_id(market_id: str) -> str | None:
    """Получаем token_id для market_id через Gamma API (кэшируем)."""
    if market_id in _token_cache:
        return _token_cache[market_id]
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"condition_ids": market_id},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            import json as _json
            tokens = data[0].get("clobTokenIds", [])
            if isinstance(tokens, str):
                tokens = _json.loads(tokens)
            if tokens:
                _token_cache[market_id] = tokens[0]
                return tokens[0]
    except Exception as e:
        log.debug(f"[Tracker] token_id lookup failed for {market_id}: {e}")
    return None


def fetch_current_price(market_id: str, entry_team: str) -> float | None:
    """
    Получает текущую mid-price для команды аутсайдера.
    Сначала пробуем /midpoint, потом /book.
    """
    token_id = _get_token_id(market_id)
    if not token_id:
        return None

    # --- пробуем /midpoint (быстрее) ---
    try:
        resp = requests.get(
            f"{CLOB_API}/midpoint",
            params={"token_id": token_id},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            mid = data.get("mid")
            if mid is not None:
                return round(float(mid), 4)
    except Exception:
        pass

    # --- фоллбэк: /book ---
    try:
        resp = requests.get(
            f"{CLOB_API}/book",
            params={"token_id": token_id},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        asks = data.get("asks", [])
        bids = data.get("bids", [])
        if asks:
            ask = float(asks[0]["price"])
            bid = float(bids[0]["price"]) if bids else ask
            return round((ask + bid) / 2, 4)
    except Exception as e:
        log.debug(f"[Tracker] book fetch failed for {market_id}: {e}")

    return None


def fetch_prices_batch(market_ids: list[str]) -> dict[str, float | None]:
    """
    Батчевый запрос цен для нескольких market_id.
    Возвращает {market_id: price}.
    """
    if not market_ids:
        return {}

    # собираем token_ids
    token_map = {}  # token_id → market_id
    for mid in market_ids:
        tid = _get_token_id(mid)
        if tid:
            token_map[tid] = mid

    if not token_map:
        return {mid: None for mid in market_ids}

    result = {mid: None for mid in market_ids}
    try:
        resp = requests.get(
            f"{CLOB_API}/midpoints",
            params={"token_ids": ",".join(token_map.keys())},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            for token_id, price in data.items():
                mid = token_map.get(token_id)
                if mid:
                    result[mid] = round(float(price), 4)
            return result
    except Exception:
        pass

    # фоллбэк — поодиночке
    for token_id, mid in token_map.items():
        try:
            resp = requests.get(
                f"{CLOB_API}/midpoint",
                params={"token_id": token_id},
                timeout=5,
            )
            if resp.status_code == 200:
                p = resp.json().get("mid")
                if p is not None:
                    result[mid] = round(float(p), 4)
        except Exception:
            pass

    return result


# ────────────────────────────────────────────────────────────────────────────
# Проверка TP / SL
# ────────────────────────────────────────────────────────────────────────────

def check_tp_sl(
    current_price: float,
    entry_price: float,
    tp_multiplier: float,
    sl_fraction: float,
) -> str | None:
    """
    Возвращает 'tp', 'sl' или None.

    TP: current_price >= entry_price * (1 + tp_multiplier)
        Например entry=0.10, tp_multiplier=2.0 → продаём при >= 0.30

    SL: current_price <= entry_price * (1 - sl_fraction)
        Например entry=0.10, sl_fraction=0.50 → продаём при <= 0.05
    """
    if entry_price <= 0:
        return None

    tp_target = round(entry_price * (1 + tp_multiplier), 6)
    sl_target = round(entry_price * (1 - sl_fraction), 6)

    if current_price >= tp_target:
        return "tp"
    if current_price <= sl_target:
        return "sl"
    return None


def is_market_resolved(market_id: str) -> bool:
    """
    Проверяет завершён ли рынок (resolved=true на Gamma API).
    """
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"condition_ids": market_id},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return data[0].get("resolved", False) or data[0].get("closed", False)
    except Exception:
        pass
    return False


# ────────────────────────────────────────────────────────────────────────────
# Главная функция — вызывается каждую секунду
# ────────────────────────────────────────────────────────────────────────────

def track_open_trades():
    """
    Основной цикл трекера.
    Вызывается каждые TRACKER_INTERVAL_SECONDS (1 сек) из APScheduler.
    Легковесный: не логирует при отсутствии событий.
    """
    strategies = [s for s in get_all_strategies() if s["is_active"]]
    if not strategies:
        return

    for strategy in strategies:
        strategy_id = strategy["id"]
        params      = strategy["params"]
        tp_mult     = params.get("take_profit", 2.0)    # 2.0 = +200%
        sl_frac     = params.get("stop_loss", 0.50)     # 0.50 = -50%

        open_trades = get_open_trades(strategy_id)
        if not open_trades:
            continue

        # батчевый запрос цен для всех открытых сделок
        market_ids = [t["market_id"] for t in open_trades]
        prices = fetch_prices_batch(market_ids)

        for trade in open_trades:
            trade_id    = trade["id"]
            market_id   = trade["market_id"]
            entry_price = trade["entry_price"]
            event_name  = trade["event_name"]

            current_price = prices.get(market_id)

            # если не смогли получить цену — проверяем не завершился ли рынок
            if current_price is None:
                if is_market_resolved(market_id):
                    # рынок закрылся — фиксируем как expired по entry_price
                    close_trade(trade_id, exit_price=entry_price, status="expired")
                    log.info(
                        f"[Tracker] ⏱ Expired: {event_name} | "
                        f"trade #{trade_id} | цена недоступна"
                    )
                continue

            # проверяем TP / SL
            signal = check_tp_sl(
                current_price=current_price,
                entry_price=entry_price,
                tp_multiplier=tp_mult,
                sl_fraction=sl_frac,
            )

            if signal == "tp":
                close_trade(trade_id, exit_price=current_price, status="tp")
                pnl = round(trade["bet_size"] * (current_price - entry_price) / entry_price, 2)
                log.info(
                    f"[Tracker] ✅ TP: {event_name} | "
                    f"{entry_price*100:.1f}% → {current_price*100:.1f}% | "
                    f"PnL: +${pnl} | trade #{trade_id}"
                )

            elif signal == "sl":
                close_trade(trade_id, exit_price=current_price, status="sl")
                pnl = round(trade["bet_size"] * (current_price - entry_price) / entry_price, 2)
                log.info(
                    f"[Tracker] ❌ SL: {event_name} | "
                    f"{entry_price*100:.1f}% → {current_price*100:.1f}% | "
                    f"PnL: ${pnl} | trade #{trade_id}"
                )
