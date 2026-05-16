# db.py
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


def get_all_strategies():
    """Возвращает список всех стратегий из БД."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM strategies")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_open_trades(strategy_id: int):
    """Возвращает список открытых сделок по конкретной стратегии."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE strategy_id = ? AND status = 'open'", (strategy_id,))
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


def upsert_monitored_market(market_id, event_name, game, market_type, underdog_team, underdog_price, match_starts_at=None):
    """Обновляет или добавляет рынок в таблицу отслеживаемых."""
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
