# db.py — Единый модуль работы с БД для сканнера и дашборда
import sqlite3
import json
import logging
from config import DB_PATH

log = logging.getLogger(__name__)

def get_db_connection():
    """Создает и возвращает подключение к базе данных SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── ФУНКЦИИ ДЛЯ СТРАТЕГИЙ (ОБЩИЕ) ───────────────────────────────────────────

def get_all_strategies():
    """Возвращает список всех стратегий из БД."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM strategies")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_strategy(strategy_id: int):
    """Возвращает одну стратегию по её ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_strategy(strategy_id: int, name: str, is_active: bool, params: dict, filters: dict):
    """Обновляет настройки стратегии в БД."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE strategies
            SET name = ?, is_active = ?, params = ?, filters = ?
            WHERE id = ?
        ''', (name, int(is_active), json.dumps(params), json.dumps(filters), strategy_id))
        conn.commit()


def create_strategy(name: str, is_active: bool, params: dict, filters: dict):
    """Создает новую стратегию в БД."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO strategies (name, is_active, params, filters)
            VALUES (?, ?, ?, ?)
        ''', (name, int(is_active), json.dumps(params), json.dumps(filters)))
        conn.commit()
        return cursor.lastrowid

# ── ФУНКЦИИ ДЛЯ СДЕЛОК (TRADES) ─────────────────────────────────────────────

def get_open_trades(strategy_id: int):
    """Возвращает список открытых сделок по конкретной стратегии."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE strategy_id = ? AND status = 'open'", (strategy_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_all_trades(limit: int = 100):
    """Возвращает историю всех сделок для дашборда."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def open_trade(strategy_id, market_id, event_name, game, market_type, team, entry_price, bet_size, match_starts_at=None):
    """Записывает новую открытую сделку в базу данных."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (strategy_id, market_id, event_name, game, market_type, team, entry_price, bet_size, status, created_at, match_starts_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', datetime('now'), ?)
        ''', (strategy_id, market_id, event_name, game, market_type, team, entry_price, bet_size, match_starts_at))
        conn.commit()
        return cursor.lastrowid


def close_trade(trade_id: int, exit_price: float, pnl: float, status: str = 'closed'):
    """Закрывает сделку с фиксацией результата."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE trades
            SET exit_price = ?, pnl = ?, status = ?, closed_at = datetime('now')
            WHERE id = ?
        ''', (exit_price, pnl, status, trade_id))
        conn.commit()

# ── ФУНКЦИИ МОНИТОРИНГА ЦЕН (MONITORED) ──────────────────────────────────────

def upsert_monitored_market(market_id, event_name, game, market_type, underdog_team, underdog_price, match_starts_at=None):
    """Обновляет или добавляет рынок в таблицу отслеживаемых для трекера цен."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO monitored_markets (market_id, event_name, game, market_type, underdog_team, underdog_price, updated_at, match_starts_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)
            ON CONFLICT(market_id) DO UPDATE SET
                underdog_price = excluded.underdog_price,
                updated_at = datetime('now')
        ''', (market_id, event_name, game, market_type, underdog_team, underdog_price, match_starts_at))
        conn.commit()


def get_monitored_markets():
    """Возвращает список всех отслеживаемых в данный момент маркетов."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM monitored_markets ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
