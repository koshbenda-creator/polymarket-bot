# db.py — работа с базой данных

import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Создаём таблицы если их нет."""
    conn = get_conn()
    c = conn.cursor()

    # === Стратегии ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            params      TEXT NOT NULL,   -- JSON с параметрами
            filters     TEXT NOT NULL,   -- JSON с фильтрами рынков
            deposit     REAL NOT NULL,   -- стартовый депозит
            balance     REAL NOT NULL,   -- текущий баланс
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT NOT NULL
        )
    """)

    # === Сделки ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id     INTEGER NOT NULL,
            market_id       TEXT NOT NULL,      -- ID рынка на Polymarket
            event_name      TEXT NOT NULL,      -- название события
            game            TEXT NOT NULL,      -- CS2, Dota 2 и т.д.
            market_type     TEXT NOT NULL,      -- match_winner, map1 и т.д.
            team            TEXT NOT NULL,      -- команда аутсайдер
            entry_price     REAL NOT NULL,      -- вероятность при входе (0.0-1.0)
            exit_price      REAL,               -- вероятность при выходе
            bet_size        REAL NOT NULL,      -- размер ставки в USD
            pnl             REAL,               -- итоговый PnL в USD
            status          TEXT DEFAULT 'open', -- open / tp / sl / expired
            opened_at       TEXT NOT NULL,
            closed_at       TEXT,
            match_starts_at TEXT,               -- время начала матча
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        )
    """)

    # === История баланса (для графика) ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS balance_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id INTEGER NOT NULL,
            balance     REAL NOT NULL,
            recorded_at TEXT NOT NULL,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        )
    """)

    # === Мониторинг (предстоящие события которые мы смотрим) ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS monitored_markets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id       TEXT NOT NULL UNIQUE,
            event_name      TEXT NOT NULL,
            game            TEXT NOT NULL,
            market_type     TEXT NOT NULL,
            team            TEXT NOT NULL,
            current_price   REAL NOT NULL,
            match_starts_at TEXT,
            last_checked_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] База данных инициализирована.")


# ─────────────────────────────────────────────
# Стратегии
# ─────────────────────────────────────────────

def create_strategy(name, params, filters, deposit):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO strategies (name, params, filters, deposit, balance, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
    """, (name, json.dumps(params), json.dumps(filters), deposit, deposit,
          datetime.utcnow().isoformat()))
    conn.commit()
    strategy_id = c.lastrowid
    # записываем стартовый баланс в историю
    record_balance(strategy_id, deposit)
    conn.close()
    return strategy_id


def get_all_strategies():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM strategies ORDER BY id").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["params"] = json.loads(d["params"])
        d["filters"] = json.loads(d["filters"])
        result.append(d)
    return result


def get_strategy(strategy_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["params"] = json.loads(d["params"])
    d["filters"] = json.loads(d["filters"])
    return d


def update_strategy_params(strategy_id, params=None, filters=None):
    conn = get_conn()
    if params:
        conn.execute("UPDATE strategies SET params = ? WHERE id = ?",
                     (json.dumps(params), strategy_id))
        # если изменился paper_deposit — обновляем deposit и balance
        if "paper_deposit" in params:
            new_deposit = float(params["paper_deposit"])
            conn.execute(
                "UPDATE strategies SET deposit = ?, balance = ? WHERE id = ?",
                (new_deposit, new_deposit, strategy_id)
            )
            # сбрасываем историю баланса
            conn.execute(
                "DELETE FROM balance_history WHERE strategy_id = ?", (strategy_id,)
            )
            conn.execute(
                "INSERT INTO balance_history (strategy_id, balance, recorded_at) VALUES (?, ?, ?)",
                (strategy_id, new_deposit, datetime.utcnow().isoformat())
            )
    if filters:
        conn.execute("UPDATE strategies SET filters = ? WHERE id = ?",
                     (json.dumps(filters), strategy_id))
    conn.commit()
    conn.close()


def update_strategy_balance(strategy_id, new_balance):
    conn = get_conn()
    conn.execute("UPDATE strategies SET balance = ? WHERE id = ?",
                 (new_balance, strategy_id))
    conn.commit()
    conn.close()


def toggle_strategy(strategy_id, is_active):
    conn = get_conn()
    conn.execute("UPDATE strategies SET is_active = ? WHERE id = ?",
                 (1 if is_active else 0, strategy_id))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# Сделки
# ─────────────────────────────────────────────

def open_trade(strategy_id, market_id, event_name, game, market_type,
               team, entry_price, bet_size, match_starts_at=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO trades
            (strategy_id, market_id, event_name, game, market_type,
             team, entry_price, bet_size, status, opened_at, match_starts_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
    """, (strategy_id, market_id, event_name, game, market_type,
          team, entry_price, bet_size,
          datetime.utcnow().isoformat(), match_starts_at))
    conn.commit()
    trade_id = c.lastrowid
    conn.close()
    return trade_id


def close_trade(trade_id, exit_price, status):
    """status: 'tp' | 'sl' | 'expired'"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if not row:
        conn.close()
        return

    bet = row["bet_size"]
    entry = row["entry_price"]

    # PnL расчёт: если цена выросла — профит, упала — убыток
    # Считаем как долевое изменение вероятности
    if entry > 0:
        price_change = (exit_price - entry) / entry
    else:
        price_change = 0
    pnl = round(bet * price_change, 2)

    conn.execute("""
        UPDATE trades
        SET exit_price = ?, pnl = ?, status = ?, closed_at = ?
        WHERE id = ?
    """, (exit_price, pnl, status, datetime.utcnow().isoformat(), trade_id))

    # обновляем баланс стратегии
    strategy = conn.execute(
        "SELECT balance, strategy_id FROM trades t JOIN strategies s ON t.strategy_id = s.id WHERE t.id = ?",
        (trade_id,)
    ).fetchone()
    if strategy:
        new_balance = round(strategy["balance"] + pnl, 2)
        conn.execute("UPDATE strategies SET balance = ? WHERE id = ?",
                     (new_balance, row["strategy_id"]))
        record_balance(row["strategy_id"], new_balance, conn=conn)

    conn.commit()
    conn.close()


def get_trades(strategy_id, status=None, limit=200):
    conn = get_conn()
    if status:
        rows = conn.execute("""
            SELECT * FROM trades WHERE strategy_id = ? AND status = ?
            ORDER BY opened_at DESC LIMIT ?
        """, (strategy_id, status, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM trades WHERE strategy_id = ?
            ORDER BY opened_at DESC LIMIT ?
        """, (strategy_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_trades(strategy_id):
    return get_trades(strategy_id, status="open")


# ─────────────────────────────────────────────
# История баланса
# ─────────────────────────────────────────────

def record_balance(strategy_id, balance, conn=None):
    close_after = False
    if conn is None:
        conn = get_conn()
        close_after = True
    conn.execute("""
        INSERT INTO balance_history (strategy_id, balance, recorded_at)
        VALUES (?, ?, ?)
    """, (strategy_id, balance, datetime.utcnow().isoformat()))
    if close_after:
        conn.commit()
        conn.close()


def get_balance_history(strategy_id, days=30):
    conn = get_conn()
    rows = conn.execute("""
        SELECT balance, recorded_at FROM balance_history
        WHERE strategy_id = ?
        ORDER BY recorded_at ASC
    """, (strategy_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# Мониторинг
# ─────────────────────────────────────────────

def upsert_monitored_market(market_id, event_name, game, market_type, underdog_team, underdog_price, match_starts_at):
    """Обновляет или добавляет маркет в таблицу мониторинга."""
    conn = get_db_connection()  # или как у тебя называется функция подключения
    cursor = conn.cursor()
    
    query = """
        INSERT INTO monitored_markets (market_id, event_name, game, market_type, underdog_team, underdog_price, match_starts_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (market_id) 
        DO UPDATE SET 
            underdog_price = EXCLUDED.underdog_price,
            updated_at = NOW();
    """
    try:
        cursor.execute(query, (market_id, event_name, game, market_type, underdog_team, underdog_price, match_starts_at))
        conn.commit()
    except Exception as e:
        log.error(f"[DB] Ошибка при upsert_monitored_market: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def get_monitored_markets():
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM monitored_markets ORDER BY match_starts_at ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_monitored_market(market_id):
    conn = get_conn()
    conn.execute("DELETE FROM monitored_markets WHERE market_id = ?", (market_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# Статистика
# ─────────────────────────────────────────────

def get_stats(strategy_id):
    conn = get_conn()
    trades = conn.execute("""
        SELECT * FROM trades WHERE strategy_id = ? AND status != 'open'
    """, (strategy_id,)).fetchall()
    strategy = conn.execute(
        "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
    ).fetchone()
    conn.close()

    if not trades or not strategy:
        return {}

    closed = [dict(t) for t in trades]
    total = len(closed)
    wins = [t for t in closed if t["pnl"] and t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] and t["pnl"] <= 0]

    total_pnl = sum(t["pnl"] for t in closed if t["pnl"])
    deposit = strategy["deposit"]
    roi = round((total_pnl / deposit) * 100, 2) if deposit else 0

    return {
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round(len(wins) / total * 100, 1) if total else 0,
        "total_pnl": round(total_pnl, 2),
        "roi": roi,
        "avg_win": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0,
        "best_trade": round(max((t["pnl"] for t in closed if t["pnl"]), default=0), 2),
        "worst_trade": round(min((t["pnl"] for t in closed if t["pnl"]), default=0), 2),
    }
