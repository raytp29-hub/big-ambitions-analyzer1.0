"""
visualization/home_sections.py
Sezioni della Home (Main Dashboard): Overview e Revenue Analysis.
I calcoli stanno in analysis/revenue_analyzer.py; qui solo presentazione.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.revenue_analyzer import (
    DELTA_WINDOW, daily_revenue_by_business, summarize_revenue,
)
from visualization.ui_components import (
    CATEGORICAL, OTHER_COLOR, area_svg, columns_html, composition_html, day_strip_html,
    delta_tone, kpi_card_html, kpi_row_html, render_revenue_cards, ui_theme,
)

MAX_SERIES = 8   # oltre, i business più piccoli finiscono in "Other"


# ============================================================================
# OVERVIEW
# ============================================================================

def render_overview(df: pd.DataFrame, source: str | None = None) -> None:
    """4 card della stessa altezza, ognuna col suo grafico:
    transazioni/giorno (colonne), giorni coperti (striscia dei giorni),
    composizione per tipo (barra 100%), saldo (area)."""
    st.subheader("📊 Overview")
    per_day = df.groupby("day").size()
    days = [int(d) for d in sorted(df["day"].unique())]
    balance = df.sort_values("day", kind="stable").groupby("day")["balance"].last()
    type_counts = df["type"].value_counts()

    # --- 1. transazioni ---
    avg = per_day.mean() if len(per_day) else 0
    c1 = kpi_card_html(
        "📋 Total transactions", f"{len(df):,}",
        sub=f'<div class="ba-delta">≈ {avg:,.0f} per day</div>',
        graphic=columns_html(per_day.tolist(), [f"Day {d}" for d in per_day.index]),
        help="Columns = transactions per game day (hover for the number). The first and last day "
             "can be partial: the save cuts the oldest rows, and the current day is still running.",
        tone="info",
    )
    # --- 2. giorni ---
    c2 = kpi_card_html(
        "📅 Days analyzed", f"{len(days)} days",
        sub=f'<div class="ba-delta">Day {days[0]} → {days[-1]}</div>' if days else "",
        graphic=day_strip_html(days),
        help="One block per game day in the file, with its weekday (weekend lighter).",
        tone="info",
    )
    # --- 3. tipi ---
    c3 = kpi_card_html(
        "📝 Transaction types", f"{len(type_counts)}",
        graphic=composition_html(list(type_counts.items())),
        help="Share of rows per type: the 4 most frequent, the rest as Other.",
    )
    # --- 4. saldo ---
    sub, tone = "", "neutral"
    if len(balance) > 1:
        span = min(DELTA_WINDOW, len(balance) - 1)
        change = balance.iloc[-1] - balance.iloc[-span - 1]
        tone = delta_tone(change / abs(balance.iloc[-span - 1]) if balance.iloc[-span - 1] else None)
        arrow = "▲" if change >= 0 else "▼"
        sub = f'<div class="ba-delta"><b>{arrow} ${abs(change):,.0f}</b> in {span} days</div>'
    c4 = kpi_card_html(
        "💰 Final balance", f"${balance.iloc[-1]:,.0f}" if len(balance) else "$0",
        sub=sub, graphic=area_svg(balance.tolist()), tone=tone,
        help="Area = your balance at the end of each game day.",
    )
    st.html(kpi_row_html([c1, c2, c3, c4]))

    if source == "hsg":
        st.caption(
            f"The save keeps only the last 1,000 transactions (here {len(days)} days): "
            "Overview and Profit & Loss cover that period."
        )


# ============================================================================
# REVENUE ANALYSIS
# ============================================================================

def _fold_other(daily: pd.DataFrame, order: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Tiene i MAX_SERIES-1 business più grandi, somma il resto in 'Other'."""
    if len(order) <= MAX_SERIES:
        return daily, order
    keep = order[: MAX_SERIES - 1]
    folded = daily.assign(business=daily["business"].where(daily["business"].isin(keep), "Other"))
    folded = folded.groupby(["business", "day"], as_index=False)["revenue"].sum()
    return folded, keep + ["Other"]


def revenue_lines_figure(daily: pd.DataFrame, order: list[str], theme: str, log_y: bool = False) -> go.Figure:
    """Una linea per business. Colore legato al business (ordine alfabetico dei
    business mostrati), non alla posizione in classifica: se cambia il totale
    il colore resta lo stesso."""
    daily, shown = _fold_other(daily, order)
    palette = CATEGORICAL[theme]
    named = sorted(b for b in shown if b != "Other")
    color = {b: palette[i] for i, b in enumerate(named)}
    color["Other"] = OTHER_COLOR[theme]

    fig = go.Figure()
    for business in shown:                       # legenda nello stesso ordine delle card
        g = daily[daily["business"] == business].sort_values("day")
        fig.add_trace(go.Scatter(
            x=g["day"], y=g["revenue"], name=business, mode="lines",
            line=dict(color=color[business], width=2),
            hovertemplate="%{y:$,.0f}<extra>" + business.replace("<", "&lt;") + "</extra>",
        ))
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis_title="Game day", yaxis_title=None,
    )
    fig.update_yaxes(tickformat="$,.0s" if log_y else "$,.0f", type="log" if log_y else "linear")
    fig.update_xaxes(dtick=1 if daily["day"].nunique() <= 20 else None)
    return fig


def render_revenue_section(df: pd.DataFrame, bundle=None) -> None:
    item_sales = getattr(bundle, "item_sales", None) if bundle is not None else None
    daily, source = daily_revenue_by_business(df, item_sales)
    # business senza vendite nel periodo (es. Factory: righe a $0) → niente card
    rows = [r for r in summarize_revenue(daily) if r.total > 0]

    st.subheader("Revenue Analysis")
    if not rows:
        st.info("No revenue found in this file.")
        return
    n_days = daily["day"].nunique()
    origin = ("per-item sales stored in the save" if source == "item_sales"
              else "Revenue rows of the transaction ledger")
    st.caption(
        f"Last {n_days} days, from the {origin}. Each card: total revenue, change of the last "
        f"{DELTA_WINDOW} days vs the {DELTA_WINDOW} before, share of all your revenue, daily trend."
    )
    render_revenue_cards(rows, DELTA_WINDOW)

    st.markdown("**Daily revenue by business**")
    log_y = st.toggle(
        "Log scale", key="home_revenue_log",
        help="Useful when one business earns 100× another: small businesses stop looking flat.",
    )
    order = [r.business for r in rows]
    st.plotly_chart(revenue_lines_figure(daily, order, ui_theme(), log_y),
                    use_container_width=True, config={"displayModeBar": False})
    st.caption("Hover a day to compare every business on that day. Click a name in the legend to hide it.")
