# dashboard.py — Streamlit веб-дашборд
# Запуск: streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
from datetime import datetime, timezone, timedelta

import db
from db import (
    get_all_strategies, get_strategy, create_strategy,
    update_strategy_params, toggle_strategy,
    get_trades, get_open_trades, get_balance_history, get_stats,
    get_monitored_markets,
)
from config import DEFAULT_STRATEGY, DEFAULT_MARKET_FILTERS

# ────────────────────────────────────────────────────────────────────────────
# Конфиг страницы
# ────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Polymarket Bot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ────────────────────────────────────────────────────────────────────────────
# CSS
# ────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Sora:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Sora', sans-serif;
}

/* Фон */
.stApp { background: #0d0f14; }

/* Убираем стандартный padding */
.block-container { padding: 1.5rem 2rem 2rem 2rem !important; max-width: 100% !important; }

/* Метрики */
[data-testid="metric-container"] {
    background: #13161e;
    border: 1px solid #1e2230;
    border-radius: 12px;
    padding: 1rem 1.2rem;
}
[data-testid="metric-container"] label {
    color: #5a6180 !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace !important;
}
[data-testid="metric-container"] [data-testid="metric-value"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.6rem !important;
    color: #e8eaf0 !important;
}
[data-testid="stMetricDelta"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
}

/* Заголовки вкладок */
[data-testid="stTabs"] [role="tab"] {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    letter-spacing: 0.05em;
    color: #5a6180;
    border-radius: 8px 8px 0 0;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #7eb8f7 !important;
    border-bottom: 2px solid #7eb8f7 !important;
}

/* Инпуты */
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
    background: #13161e !important;
    border: 1px solid #1e2230 !important;
    border-radius: 8px !important;
    color: #e8eaf0 !important;
    font-family: 'JetBrains Mono', monospace !important;
}

/* Чекбоксы */
[data-testid="stCheckbox"] label {
    color: #9ba3bf !important;
    font-size: 0.88rem !important;
}

/* Кнопки */
[data-testid="stButton"] button {
    background: #13161e !important;
    border: 1px solid #1e2230 !important;
    color: #9ba3bf !important;
    border-radius: 8px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.8rem !important;
    transition: all 0.15s ease;
}
[data-testid="stButton"] button:hover {
    border-color: #7eb8f7 !important;
    color: #7eb8f7 !important;
}
[data-testid="stButton"] button[kind="primary"] {
    background: #1a2a3a !important;
    border-color: #7eb8f7 !important;
    color: #7eb8f7 !important;
}

/* Таблица */
[data-testid="stDataFrame"] {
    border: 1px solid #1e2230;
    border-radius: 12px;
    overflow: hidden;
}

/* Разделитель */
hr { border-color: #1e2230 !important; }

/* Заголовки секций */
.section-header {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    color: #3d4460;
    text-transform: uppercase;
    margin: 1.5rem 0 0.8rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #1e2230;
}

/* Статус бот */
.bot-status {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #5a6180;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.pulse-dot {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #22c55e;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34,197,94,0.4); }
    50% { opacity: 0.7; box-shadow: 0 0 0 4px rgba(34,197,94,0); }
}

/* Монитор строки */
.monitor-row {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 12px;
    background: #13161e;
    border-radius: 8px;
    margin-bottom: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
}
.monitor-game { color: #5a6180; min-width: 70px; }
.monitor-event { color: #c8cce0; flex: 1; }
.monitor-type {
    background: #1a2a3a;
    color: #7eb8f7;
    padding: 2px 8px; border-radius: 20px;
    font-size: 0.7rem;
}
.monitor-price-hot { color: #22c55e; font-weight: 700; }
.monitor-price-warm { color: #f59e0b; }
.monitor-price-cold { color: #5a6180; }
.monitor-time { color: #3d4460; min-width: 80px; text-align: right; }

/* Бейдж стратегии */
.strategy-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
}
.badge-active { background: #0d2a1a; color: #22c55e; border: 1px solid #1a4a2a; }
.badge-paused { background: #2a1f0d; color: #f59e0b; border: 1px solid #4a3a1a; }
</style>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Инициализация БД
# ────────────────────────────────────────────────────────────────────────────

db.init_db()


# ────────────────────────────────────────────────────────────────────────────
# Хелперы
# ────────────────────────────────────────────────────────────────────────────

def fmt_pnl(val):
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:.2f}"

def fmt_price(p):
    if p is None:
        return "—"
    return f"{p*100:.1f}%"

def status_emoji(s):
    return {"tp": "✅", "sl": "❌", "open": "⏳", "expired": "⏱"}.get(s, s)

def time_until(dt_str):
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        diff = dt - datetime.now(timezone.utc)
        if diff.total_seconds() < 0:
            return "идёт"
        h, rem = divmod(int(diff.total_seconds()), 3600)
        m = rem // 60
        if h > 0:
            return f"{h}ч {m}м"
        return f"{m}м"
    except Exception:
        return "—"

def filter_by_period(trades, period):
    now = datetime.now(timezone.utc)
    cutoffs = {
        "Сегодня":   now - timedelta(days=1),
        "Неделя":    now - timedelta(weeks=1),
        "Месяц":     now - timedelta(days=30),
        "Всё время": None,
    }
    cutoff = cutoffs.get(period)
    if cutoff is None:
        return trades
    result = []
    for t in trades:
        try:
            opened = datetime.fromisoformat(t["opened_at"].replace("Z", "+00:00"))
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
            if opened >= cutoff:
                result.append(t)
        except Exception:
            result.append(t)
    return result


def make_balance_chart(history, deposit):
    if not history:
        return None
    df = pd.DataFrame(history)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["recorded_at"],
        y=df["balance"],
        mode="lines",
        line=dict(color="#7eb8f7", width=2),
        fill="tozeroy",
        fillcolor="rgba(126,184,247,0.06)",
        hovertemplate="%{y:.2f}$<extra></extra>",
    ))
    fig.add_hline(
        y=deposit,
        line_dash="dot",
        line_color="#3d4460",
        annotation_text="старт",
        annotation_font_color="#3d4460",
        annotation_font_size=10,
    )
    fig.update_layout(
        plot_bgcolor="#0d0f14",
        paper_bgcolor="#0d0f14",
        margin=dict(l=0, r=0, t=10, b=0),
        height=200,
        xaxis=dict(showgrid=False, color="#3d4460", tickfont=dict(family="JetBrains Mono", size=10)),
        yaxis=dict(showgrid=True, gridcolor="#1e2230", color="#3d4460",
                   tickfont=dict(family="JetBrains Mono", size=10),
                   tickprefix="$"),
        showlegend=False,
    )
    return fig


def make_pnl_chart(trades):
    closed = [t for t in trades if t["status"] != "open" and t["pnl"] is not None]
    if not closed:
        return None
    df = pd.DataFrame(closed)
    df["opened_at"] = pd.to_datetime(df["opened_at"])
    df = df.sort_values("opened_at")
    df["cumulative"] = df["pnl"].cumsum()
    df["color"] = df["pnl"].apply(lambda x: "#22c55e" if x > 0 else "#ef4444")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["opened_at"],
        y=df["pnl"],
        marker_color=df["color"],
        hovertemplate="%{y:+.2f}$<extra></extra>",
    ))
    fig.update_layout(
        plot_bgcolor="#0d0f14",
        paper_bgcolor="#0d0f14",
        margin=dict(l=0, r=0, t=10, b=0),
        height=180,
        xaxis=dict(showgrid=False, color="#3d4460",
                   tickfont=dict(family="JetBrains Mono", size=10)),
        yaxis=dict(showgrid=True, gridcolor="#1e2230", color="#3d4460",
                   tickfont=dict(family="JetBrains Mono", size=10),
                   tickprefix="$"),
        showlegend=False,
    )
    return fig


# ────────────────────────────────────────────────────────────────────────────
# Хедер
# ────────────────────────────────────────────────────────────────────────────

col_title, col_status = st.columns([6, 1])
with col_title:
    st.markdown(
        "<h1 style='font-family:JetBrains Mono,monospace;font-size:1.3rem;"
        "color:#e8eaf0;margin:0;font-weight:600;letter-spacing:0.05em'>"
        "POLYMARKET PAPER BOT</h1>",
        unsafe_allow_html=True,
    )
with col_status:
    st.markdown(
        "<div class='bot-status' style='justify-content:flex-end;padding-top:8px'>"
        "<span class='pulse-dot'></span> running</div>",
        unsafe_allow_html=True,
    )

st.markdown("<hr style='margin:0.5rem 0 1rem 0'>", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Загружаем стратегии
# ────────────────────────────────────────────────────────────────────────────

strategies = get_all_strategies()

if not strategies:
    st.info("Нет стратегий. Создай первую ниже ↓")
    strategies = []


# ────────────────────────────────────────────────────────────────────────────
# Вкладки: одна на стратегию + Мониторинг + Сравнение + Новая
# ────────────────────────────────────────────────────────────────────────────

tab_names = [s["name"] for s in strategies] + ["📡 Мониторинг", "⚖️ Сравнение", "＋ Стратегия"]
tabs = st.tabs(tab_names)


# ════════════════════════════════════════════════════════════════════════════
# ВКЛАДКИ СТРАТЕГИЙ
# ════════════════════════════════════════════════════════════════════════════

for i, strategy in enumerate(strategies):
    with tabs[i]:
        sid       = strategy["id"]
        params    = strategy["params"]
        filters   = strategy["filters"]
        is_active = bool(strategy["is_active"])

        all_trades   = get_trades(sid)
        open_trades  = get_open_trades(sid)
        stats        = get_stats(sid)
        bal_history  = get_balance_history(sid)
        deposit      = strategy["deposit"]
        balance      = strategy["balance"]

        # ── Статус + кнопка паузы ───────────────────────────────────────────
        c1, c2 = st.columns([8, 1])
        with c1:
            badge_cls  = "badge-active" if is_active else "badge-paused"
            badge_text = "active" if is_active else "paused"
            st.markdown(
                f"<span class='strategy-badge {badge_cls}'>{badge_text}</span>",
                unsafe_allow_html=True,
            )
        with c2:
            btn_label = "⏸ пауза" if is_active else "▶ старт"
            if st.button(btn_label, key=f"toggle_{sid}"):
                toggle_strategy(sid, not is_active)
                st.rerun()

        # ── Метрики ─────────────────────────────────────────────────────────
        st.markdown("<div class='section-header'>обзор</div>", unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)

        pnl_total = stats.get("total_pnl", 0)
        roi       = stats.get("roi", 0)
        winrate   = stats.get("winrate", 0)
        total_tr  = stats.get("total_trades", 0)

        m1.metric("Баланс",   f"${balance:,.2f}",
                  delta=f"{fmt_pnl(pnl_total)} от старта")
        m2.metric("PnL",      fmt_pnl(pnl_total),
                  delta=f"{roi:+.1f}% ROI")
        m3.metric("Winrate",  f"{winrate:.0f}%",
                  delta=f"{stats.get('wins',0)}W / {stats.get('losses',0)}L")
        m4.metric("Сделок",   str(total_tr),
                  delta=f"{len(open_trades)} открытых")
        m5.metric("Avg Win",  fmt_pnl(stats.get("avg_win")),
                  delta=f"Avg Loss: {fmt_pnl(stats.get('avg_loss'))}")

        # ── Графики ─────────────────────────────────────────────────────────
        st.markdown("<div class='section-header'>баланс</div>", unsafe_allow_html=True)

        period_col, _ = st.columns([2, 6])
        with period_col:
            period = st.radio("", ["7д", "30д", "Всё"], horizontal=True,
                              key=f"period_{sid}", label_visibility="collapsed")

        days_map = {"7д": 7, "30д": 30, "Всё": 9999}
        hist = get_balance_history(sid, days=days_map[period])

        gcol1, gcol2 = st.columns(2)
        with gcol1:
            fig_bal = make_balance_chart(hist, deposit)
            if fig_bal:
                st.plotly_chart(fig_bal, use_container_width=True, config={"displayModeBar": False})
            else:
                st.caption("Нет данных для графика баланса")
        with gcol2:
            fig_pnl = make_pnl_chart(all_trades)
            if fig_pnl:
                st.plotly_chart(fig_pnl, use_container_width=True, config={"displayModeBar": False})
            else:
                st.caption("Нет закрытых сделок")

        # ── Сделки ──────────────────────────────────────────────────────────
        st.markdown("<div class='section-header'>сделки</div>", unsafe_allow_html=True)

        tc1, tc2 = st.columns([3, 5])
        with tc1:
            trade_period = st.radio(
                "", ["Сегодня", "Неделя", "Месяц", "Всё время"],
                horizontal=True, key=f"tperiod_{sid}", label_visibility="collapsed"
            )
        with tc2:
            show_open   = st.checkbox("Открытые", value=True, key=f"show_open_{sid}")
            show_closed = st.checkbox("Закрытые", value=True, key=f"show_closed_{sid}")

        filtered = filter_by_period(all_trades, trade_period)
        if not show_open:
            filtered = [t for t in filtered if t["status"] != "open"]
        if not show_closed:
            filtered = [t for t in filtered if t["status"] == "open"]

        if filtered:
            rows = []
            for t in filtered:
                rows.append({
                    "Статус":    status_emoji(t["status"]) + " " + t["status"].upper(),
                    "Время":     t["opened_at"][:16].replace("T", " "),
                    "Событие":   t["event_name"],
                    "Игра":      t["game"],
                    "Тип":       t["market_type"],
                    "Вход":      fmt_price(t["entry_price"]),
                    "Выход":     fmt_price(t["exit_price"]),
                    "Ставка":    f"${t['bet_size']:.0f}",
                    "PnL":       fmt_pnl(t["pnl"]) if t["pnl"] is not None else "—",
                })
            df = pd.DataFrame(rows)
            st.dataframe(
                df, use_container_width=True, hide_index=True,
                column_config={
                    "PnL": st.column_config.TextColumn("PnL"),
                }
            )
        else:
            st.caption("Нет сделок за выбранный период")

        # ── Настройки ───────────────────────────────────────────────────────
        st.markdown("<div class='section-header'>параметры стратегии</div>",
                    unsafe_allow_html=True)

        with st.expander("⚙️ Настроить", expanded=False):
            pc1, pc2, pc3, pc4 = st.columns(4)
            new_entry  = pc1.number_input("Порог входа (%)", 1, 49,
                            int(params["entry_max_prob"] * 100), key=f"entry_{sid}")
            new_hours  = pc2.number_input("Часов до матча", 1, 48,
                            int(params["entry_hours_before"]), key=f"hours_{sid}")
            new_tp     = pc3.number_input("Take Profit (%)", 50, 1000,
                            int(params["take_profit"] * 100), key=f"tp_{sid}")
            new_sl     = pc4.number_input("Stop Loss (%)", 5, 95,
                            int(params["stop_loss"] * 100), key=f"sl_{sid}")

            new_deposit = st.number_input("Paper депозит ($)", 100, 100000,
                            int(params["paper_deposit"]), step=100, key=f"dep_{sid}")
            new_bet     = st.number_input("Размер ставки ($)", 1, 10000,
                            int(params["bet_size"]), step=10, key=f"bet_{sid}")

            st.markdown("**Типы рынков:**")
            fcol1, fcol2, fcol3 = st.columns(3)
            mtype_opts = {
                "match_winner": fcol1.checkbox("Вся игра",  "match_winner" in filters["market_types"], key=f"mt_mw_{sid}"),
                "map1":         fcol1.checkbox("Карта 1",   "map1"         in filters["market_types"], key=f"mt_m1_{sid}"),
                "map2":         fcol2.checkbox("Карта 2",   "map2"         in filters["market_types"], key=f"mt_m2_{sid}"),
                "map3":         fcol2.checkbox("Карта 3",   "map3"         in filters["market_types"], key=f"mt_m3_{sid}"),
                "map4":         fcol3.checkbox("Карта 4 (Bo5)", "map4"     in filters["market_types"], key=f"mt_m4_{sid}"),
                "map5":         fcol3.checkbox("Карта 5 (Bo5)", "map5"     in filters["market_types"], key=f"mt_m5_{sid}"),
            }

            st.markdown("**Игры:**")
            games_all = ["CS2", "Dota 2", "Valorant", "LoL", "Rainbow Six",
                         "Rocket League", "Overwatch", "CoD", "StarCraft", "Apex Legends"]
            gcols = st.columns(5)
            game_checks = {}
            for j, game in enumerate(games_all):
                game_checks[game] = gcols[j % 5].checkbox(
                    game, game in filters["games"], key=f"game_{sid}_{game}"
                )

            if st.button("💾 Сохранить параметры", key=f"save_{sid}", type="primary"):
                new_params = {
                    **params,
                    "entry_max_prob":   new_entry / 100,
                    "entry_hours_before": new_hours,
                    "take_profit":      new_tp / 100,
                    "stop_loss":        new_sl / 100,
                    "paper_deposit":    float(new_deposit),
                    "bet_size":         float(new_bet),
                }
                new_filters = {
                    "market_types": [k for k, v in mtype_opts.items() if v],
                    "games":        [g for g, v in game_checks.items() if v],
                }
                update_strategy_params(sid, params=new_params, filters=new_filters)
                st.success("Параметры сохранены!")
                st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# ВКЛАДКА: МОНИТОРИНГ
# ════════════════════════════════════════════════════════════════════════════

monitor_tab_idx = len(strategies)
with tabs[monitor_tab_idx]:
    st.markdown("<div class='section-header'>предстоящие события</div>",
                unsafe_allow_html=True)

    monitored = get_monitored_markets()

    if not monitored:
        st.caption("Нет данных. Бот ещё не запускал сканер или не нашёл киберспортивных рынков.")
    else:
        # Фильтры
        fc1, fc2 = st.columns([3, 5])
        with fc1:
            show_only_entry = st.checkbox("Только под порог входа (<15%)", value=False)
        with fc2:
            game_filter = st.multiselect(
                "Игры",
                options=list(set(m["game"] for m in monitored)),
                default=[],
                placeholder="Все игры",
            )

        filtered_m = monitored
        if show_only_entry:
            filtered_m = [m for m in filtered_m if m["current_price"] < 0.15]
        if game_filter:
            filtered_m = [m for m in filtered_m if m["game"] in game_filter]

        for m in filtered_m:
            price = m["current_price"]
            if price < 0.10:
                price_cls  = "monitor-price-hot"
            elif price < 0.15:
                price_cls  = "monitor-price-warm"
            else:
                price_cls  = "monitor-price-cold"

            st.markdown(f"""
            <div class='monitor-row'>
                <span class='monitor-game'>{m['game']}</span>
                <span class='monitor-event'>{m['event_name']}</span>
                <span class='monitor-type'>{m['market_type']}</span>
                <span class='{price_cls}'>{price*100:.1f}%</span>
                <span class='monitor-time'>через {time_until(m['match_starts_at'])}</span>
            </div>
            """, unsafe_allow_html=True)

        st.caption(f"Всего событий в мониторинге: {len(monitored)} | "
                   f"Показано: {len(filtered_m)}")


# ════════════════════════════════════════════════════════════════════════════
# ВКЛАДКА: СРАВНЕНИЕ
# ════════════════════════════════════════════════════════════════════════════

compare_tab_idx = len(strategies) + 1
with tabs[compare_tab_idx]:
    st.markdown("<div class='section-header'>сравнение стратегий</div>",
                unsafe_allow_html=True)

    if len(strategies) < 2:
        st.info("Нужно минимум 2 стратегии для сравнения.")
    else:
        # Таблица метрик
        rows = []
        for s in strategies:
            st_stats = get_stats(s["id"])
            rows.append({
                "Стратегия":  s["name"],
                "Баланс":     f"${s['balance']:,.2f}",
                "PnL":        fmt_pnl(st_stats.get("total_pnl")),
                "ROI":        f"{st_stats.get('roi', 0):+.1f}%",
                "Winrate":    f"{st_stats.get('winrate', 0):.0f}%",
                "Сделок":     str(st_stats.get("total_trades", 0)),
                "Avg Win":    fmt_pnl(st_stats.get("avg_win")),
                "Avg Loss":   fmt_pnl(st_stats.get("avg_loss")),
                "Лучшая":     fmt_pnl(st_stats.get("best_trade")),
                "Худшая":     fmt_pnl(st_stats.get("worst_trade")),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Сравнительный график балансов
        st.markdown("<div class='section-header'>график балансов</div>",
                    unsafe_allow_html=True)

        colors = ["#7eb8f7", "#22c55e", "#f59e0b", "#ef4444", "#a78bfa"]
        fig = go.Figure()

        for j, s in enumerate(strategies):
            hist = get_balance_history(s["id"])
            if hist:
                df = pd.DataFrame(hist)
                df["recorded_at"] = pd.to_datetime(df["recorded_at"])
                fig.add_trace(go.Scatter(
                    x=df["recorded_at"],
                    y=df["balance"],
                    name=s["name"],
                    mode="lines",
                    line=dict(color=colors[j % len(colors)], width=2),
                ))

        fig.update_layout(
            plot_bgcolor="#0d0f14",
            paper_bgcolor="#0d0f14",
            margin=dict(l=0, r=0, t=10, b=0),
            height=280,
            xaxis=dict(showgrid=False, color="#3d4460",
                       tickfont=dict(family="JetBrains Mono", size=10)),
            yaxis=dict(showgrid=True, gridcolor="#1e2230", color="#3d4460",
                       tickfont=dict(family="JetBrains Mono", size=10),
                       tickprefix="$"),
            legend=dict(
                font=dict(family="JetBrains Mono", size=11, color="#9ba3bf"),
                bgcolor="rgba(0,0,0,0)",
            ),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════════════════════════
# ВКЛАДКА: НОВАЯ СТРАТЕГИЯ
# ════════════════════════════════════════════════════════════════════════════

new_tab_idx = len(strategies) + 2
with tabs[new_tab_idx]:
    st.markdown("<div class='section-header'>создать новую стратегию</div>",
                unsafe_allow_html=True)

    nc1, nc2 = st.columns([2, 4])
    with nc1:
        new_name = st.text_input("Название", value=f"Стратегия {chr(65+len(strategies))}")

    with st.expander("Параметры", expanded=True):
        p1, p2, p3, p4 = st.columns(4)
        n_entry  = p1.number_input("Порог входа (%)",    1, 49, 15, key="new_entry")
        n_hours  = p2.number_input("Часов до матча",     1, 48, 24, key="new_hours")
        n_tp     = p3.number_input("Take Profit (%)",  50, 1000, 200, key="new_tp")
        n_sl     = p4.number_input("Stop Loss (%)",     5,   95,  50, key="new_sl")
        n_dep    = st.number_input("Paper депозит ($)", 100, 100000, 1000, step=100, key="new_dep")
        n_bet    = st.number_input("Размер ставки ($)",   1,  10000,   50, step=10,  key="new_bet")

    with st.expander("Фильтры рынков", expanded=True):
        st.markdown("**Типы рынков:**")
        nfc1, nfc2, nfc3 = st.columns(3)
        n_mtypes = {
            "match_winner": nfc1.checkbox("Вся игра",      True,  key="n_mt_mw"),
            "map1":         nfc1.checkbox("Карта 1",       True,  key="n_mt_m1"),
            "map2":         nfc2.checkbox("Карта 2",       True,  key="n_mt_m2"),
            "map3":         nfc2.checkbox("Карта 3",       True,  key="n_mt_m3"),
            "map4":         nfc3.checkbox("Карта 4 (Bo5)", False, key="n_mt_m4"),
            "map5":         nfc3.checkbox("Карта 5 (Bo5)", False, key="n_mt_m5"),
        }

        st.markdown("**Игры:**")
        all_games = ["CS2", "Dota 2", "Valorant", "LoL", "Rainbow Six",
                     "Rocket League", "Overwatch", "CoD", "StarCraft", "Apex Legends"]
        gcols2 = st.columns(5)
        n_games = {g: gcols2[j % 5].checkbox(g, True, key=f"n_game_{g}") for j, g in enumerate(all_games)}

    if st.button("🚀 Создать стратегию", type="primary", key="create_strategy"):
        if not new_name.strip():
            st.error("Введи название стратегии")
        else:
            try:
                new_params = {
                    "entry_max_prob":     n_entry / 100,
                    "entry_hours_before": n_hours,
                    "take_profit":        n_tp / 100,
                    "stop_loss":          n_sl / 100,
                    "paper_deposit":      float(n_dep),
                    "bet_size":           float(n_bet),
                }
                new_filters = {
                    "market_types": [k for k, v in n_mtypes.items() if v],
                    "games":        [g for g, v in n_games.items() if v],
                }
                create_strategy(new_name.strip(), new_params, new_filters, float(n_dep))
                st.success(f"Стратегия «{new_name}» создана!")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

# ── Авто-обновление каждые 30 секунд ────────────────────────────────────────
st.markdown("""
<script>
setTimeout(() => window.location.reload(), 30000);
</script>
""", unsafe_allow_html=True)
