# main.py — точка входа, запускает все компоненты бота

import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler

from config import (
    SCANNER_INTERVAL_SECONDS,
    TRACKER_INTERVAL_SECONDS,
    DEFAULT_STRATEGY,
    DEFAULT_MARKET_FILTERS,
)
from db import init_db, get_all_strategies, create_strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def run_scanner():
    """Запускается каждые SCANNER_INTERVAL_SECONDS секунд."""
    try:
        from scanner import scan_markets
        scan_markets()
    except Exception as e:
        log.error(f"[Scanner] Ошибка: {e}")


def run_tracker():
    """Запускается каждые TRACKER_INTERVAL_SECONDS секунд."""
    try:
        from tracker import track_open_trades
        track_open_trades()
    except Exception as e:
        log.error(f"[Tracker] Ошибка: {e}")


def ensure_default_strategy():
    """Создаём стратегию по умолчанию если нет ни одной."""
    strategies = get_all_strategies()
    if not strategies:
        log.info("[Main] Создаём стратегию по умолчанию...")
        create_strategy(
            name="Стратегия A",
            params=DEFAULT_STRATEGY,
            filters=DEFAULT_MARKET_FILTERS,
            deposit=DEFAULT_STRATEGY["paper_deposit"],
        )
        log.info("[Main] Стратегия A создана.")


def main():
    log.info("=" * 50)
    log.info("  Polymarket Paper Trading Bot  ")
    log.info("=" * 50)

    # инициализация БД
    init_db()

    # создаём дефолтную стратегию если нет ни одной
    ensure_default_strategy()

    # запускаем планировщик
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        run_scanner,
        trigger="interval",
        seconds=SCANNER_INTERVAL_SECONDS,
        id="scanner",
        next_run_time=__import__("datetime").datetime.now(),  # запуск сразу
    )

    scheduler.add_job(
        run_tracker,
        trigger="interval",
        seconds=TRACKER_INTERVAL_SECONDS,
        id="tracker",
    )

    scheduler.start()
    log.info(f"[Main] Scanner запущен (каждые {SCANNER_INTERVAL_SECONDS}с)")
    log.info(f"[Main] Tracker запущен (каждые {TRACKER_INTERVAL_SECONDS}с)")
    log.info("[Main] Дашборд: запусти отдельно командой: streamlit run dashboard.py")
    log.info("[Main] Бот работает. Ctrl+C для остановки.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("[Main] Остановка...")
        scheduler.shutdown()
        log.info("[Main] Бот остановлен.")


if __name__ == "__main__":
    main()
