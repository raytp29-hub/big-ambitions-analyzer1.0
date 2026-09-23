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
    CATEGORICAL, OTHER_COLOR, Column, Raw, area_svg, badge_html, columns_html,
    composition_html, day_strip_html, delta_tone, kpi_card_html, kpi_row_html,
    hour_columns_html, render_note, render_open_table, render_revenue_cards, ui_theme,
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
        sub=sub, graphic=area_svg(balance.tolist(), tone), tone=tone,
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


def business_colors(names, theme: str) -> dict[str, str]:
    """Colore per business, uguale in tutti i grafici della Home: ordine alfabetico
    sull'elenco completo dei business, non sulla classifica (se cambia il totale,
    o un filtro toglie un business, gli altri tengono il loro colore).
    Oltre gli 8 slot della palette → colore di "Other"."""
    palette = CATEGORICAL[theme]
    ordered = sorted({str(n) for n in names if n and n != "Other"})
    colors = {b: (palette[i] if i < len(palette) else OTHER_COLOR[theme]) for i, b in enumerate(ordered)}
    colors["Other"] = OTHER_COLOR[theme]
    return colors


def home_businesses(bundle, daily: pd.DataFrame | None = None) -> list[str]:
    """Elenco master dei business per i colori: chi vende (revenue > 0) + chi ha clienti."""
    names = set()
    if daily is not None and not daily.empty:
        tot = daily.groupby("business")["revenue"].sum()
        names |= set(tot[tot > 0].index)
    hr = getattr(bundle, "hour_reports", None) if bundle is not None else None
    if hr is not None and not hr.empty:
        names |= set(hr["business_name"].dropna().unique())
    return sorted(names)


def revenue_lines_figure(daily: pd.DataFrame, order: list[str], theme: str, log_y: bool = False,
                         colors: dict | None = None) -> go.Figure:
    """Una linea per business, colori da business_colors (fissi per business)."""
    daily, shown = _fold_other(daily, order)
    color = colors or business_colors(shown, theme)

    fig = go.Figure()
    for business in shown:                       # legenda nello stesso ordine delle card
        g = daily[daily["business"] == business].sort_values("day")
        fig.add_trace(go.Scatter(
            x=g["day"], y=g["revenue"], name=business, mode="lines",
            line=dict(color=color.get(business, OTHER_COLOR[theme]), width=2),
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
    theme = ui_theme()
    colors = business_colors(home_businesses(bundle, daily), theme)
    st.plotly_chart(revenue_lines_figure(daily, order, theme, log_y, colors),
                    use_container_width=True, config={"displayModeBar": False})
    st.caption("Hover a day to compare every business on that day. Click a name in the legend to hide it.")


# ============================================================================
# PROFIT & LOSS
# ============================================================================

MARGIN_OK = 20.0        # margin % ≥ 20 → verde; 0-20 → giallo; < 0 → rosso


def margin_tone(pct) -> str | None:
    if pct is None or pd.isna(pct):
        return None
    return "ok" if pct >= MARGIN_OK else "warning" if pct >= 0 else "critical"


def wage_share_tone(share) -> str | None:
    """Stesse soglie della Health Check (business_fit.WAGE_SHARE_OK / _WARN)."""
    from analysis.business_fit import WAGE_SHARE_OK, WAGE_SHARE_WARN
    if share is None:
        return None
    return "ok" if share <= WAGE_SHARE_OK else "warning" if share <= WAGE_SHARE_WARN else "critical"


def profit_tone(profit: float) -> str:
    return "ok" if profit > 0 else "critical" if profit < 0 else "neutral"


def _money(v) -> str:
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def pl_rows(pl_df: pd.DataFrame) -> list[dict]:
    """Righe per la tabella P&L, già con badge e sottotitoli."""
    rows = []
    for r in pl_df.sort_values("profit", ascending=False).itertuples():
        share = r.wages / r.revenue if r.revenue > 0 else None
        share_tone = wage_share_tone(share)
        rows.append({
            "business": r.business,
            "revenue": r.revenue,
            "wages": r.wages,
            "wages_sub": (Raw(badge_html(f"{share:.0%} of revenue", share_tone))
                          if share is not None else None),
            "marketing": r.marketing,
            "other_direct": r.health_insurance + r.hr_training,
            "shared": r.total_shared_costs,
            "shared_sub": (f"{_money(r.shared_revenue_based)} by revenue · "
                           f"{_money(r.shared_equal_split)} equal"),
            "profit": Raw(badge_html(_money(r.profit), profit_tone(r.profit))),
            "margin": (Raw(badge_html(f"{r.margin_pct:.0f}%", margin_tone(r.margin_pct)))
                       if r.revenue > 0 else None),
        })
    return rows


PL_COLUMNS = [
    Column("business", "Business", align="left"),
    Column("revenue", "Revenue", fmt=_money, help="Sales income of this business."),
    Column("wages", "Wages", fmt=_money, sub="wages_sub",
           help="Wages + replacement wages of this business's employees. "
                "Below: share of revenue (green ≤ 20%, yellow ≤ 35%, red above, as in the Health Check)."),
    Column("marketing", "Marketing", fmt=_money, help="Marketing campaigns for this business."),
    Column("other_direct", "Other direct", fmt=_money,
           help="Health insurance + HR training of this business's employees."),
    Column("shared", "Shared costs", fmt=_money, sub="shared_sub",
           help="Costs not tied to one business in the ledger. Rent, loans, taxes and negative "
                "bank interest are split in proportion to revenue; interior designer costs are "
                "split equally."),
    Column("profit", "Profit", help="Revenue minus all costs above."),
    Column("margin", "Margin", help="Profit / revenue. Green ≥ 20%, yellow 0–20%, red below 0."),
]


def render_pl_section(df: pd.DataFrame) -> pd.DataFrame | None:
    """Mostra la tabella P&L e restituisce il DataFrame (ordinato per profit),
    che app.py riusa per i Detailed Charts. None se non calcolabile o vuoto."""
    from analysis.profit_loss import calculate_profit_loss
    st.subheader("💰 Profit & Loss Analysis")
    try:
        pl_df = calculate_profit_loss(df)
    except Exception as e:
        st.error(f"❌ Error calculating P&L: {e}")
        st.info("💡 This might happen if there are data inconsistencies. Check your data!")
        return None
    if pl_df.empty:
        st.info("No businesses found in the transactions.")
        return None
    n_days = df["day"].nunique()
    st.caption(f"Last {n_days} days of transactions, sorted by profit. "
               "Hover a column name for what it contains.")
    render_open_table(PL_COLUMNS, pl_rows(pl_df))
    return pl_df.sort_values("profit", ascending=False).reset_index(drop=True)


# ============================================================================
# ITEM-LEVEL MARGIN
# ============================================================================

ITEM_TOP = 25


def item_rows(im: pd.DataFrame, show_business: bool) -> list[dict]:
    rows = []
    for r in im.itertuples():
        pct = None if pd.isna(r.margin_pct) else r.margin_pct
        rows.append({
            "item": r.item_display,
            "business": r.business_name if show_business else None,
            "margin": float(r.margin),
            "units": int(r.units_sold),
            "revenue": float(r.revenue),
            "avg_price": None if pd.isna(r.avg_price_per_unit) else float(r.avg_price_per_unit),
            "margin_pct": Raw(badge_html(f"{pct:.0f}%", margin_tone(pct))) if pct is not None else None,
        })
    return rows


ITEM_COLUMNS = [
    Column("item", "Item", align="left", sub="business"),
    Column("margin", "Margin $", fmt=_money, bar=True,
           help="Revenue minus wholesale cost of the units sold. Bar = relative to the top item."),
    Column("units", "Units sold", fmt=lambda v: f"{v:,}"),
    Column("revenue", "Revenue", fmt=_money),
    Column("avg_price", "Avg price", fmt=lambda v: f"${v:,.2f}", help="Revenue / units sold."),
    Column("margin_pct", "Margin %", help="Margin / revenue. Green ≥ 20%, yellow 0–20%, red below 0."),
]


def render_item_margin_section(bundle) -> None:
    from analysis.profit_loss import calculate_item_margin
    st.subheader("Item-Level Margin")
    sales = getattr(bundle, "item_sales", None) if bundle is not None else None
    if sales is None or sales.empty:
        st.info("Item-level margin requires an HSG save file. Load one from the sidebar to unlock this section.")
        return

    businesses = sorted(sales["business_name"].dropna().unique().tolist())
    c1, c2 = st.columns([3, 1])
    with c1:
        pick = st.selectbox("Business", ["All businesses"] + businesses, key="item_margin_business_filter")
    with c2:
        st.write("")   # allinea il toggle alla selectbox
        show_all = st.toggle("Show all items", key="item_margin_show_all")
    business = None if pick == "All businesses" else pick

    im = calculate_item_margin(sales, business_filter=business)
    if im.empty:
        st.warning("No item sales for this selection.")
        return
    n_days = sales["day"].nunique()
    shown = im if show_all else im.head(ITEM_TOP)
    st.caption(
        f"Last {n_days} days of sales stored in the save, sorted by margin $. "
        + ("" if show_all or len(im) <= ITEM_TOP else f"Top {ITEM_TOP} of {len(im)} items.")
    )
    render_open_table(ITEM_COLUMNS, item_rows(shown, show_business=business is None))


# ============================================================================
# HOURLY CUSTOMER TRAFFIC
# ============================================================================

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def hourly_profile(agg: pd.DataFrame) -> pd.Series:
    """Clienti medi per ora (0-23) sommati sui business selezionati: il 'giorno tipo'."""
    return agg.groupby("hour")["avg_customers"].sum().reindex(range(24), fill_value=0.0)


def traffic_kpis(hr: pd.DataFrame, agg: pd.DataFrame, single: bool,
                 colors: dict | None = None) -> list[str]:
    """Le 3 card sopra il grafico."""
    profile = hourly_profile(agg)
    peak = int(profile.idxmax())
    c1 = kpi_card_html(
        "⏰ Peak hour", f"{peak:02d}:00",
        sub=f'<div class="ba-delta">≈ {profile[peak]:,.0f} customers in that hour</div>',
        graphic=hour_columns_html(profile.tolist(), highlight=peak),
        help="Hour with the most customers on an average day (all selected businesses together). "
             "Columns = the 24 hours, the peak highlighted.",
        tone="info",
    )

    per_day = hr.groupby("day")["customers"].sum()
    per_open_hour = agg["avg_customers"].mean()
    c2 = kpi_card_html(
        "👥 Avg customers / hour", f"{per_open_hour:,.1f}",
        sub=f'<div class="ba-delta">≈ {per_day.mean():,.0f} customers per day</div>',
        graphic=area_svg(per_day.tolist(), "info"),
        help="Average customers in an open hour, per business. Area = total customers per game day.",
        tone="info",
    )

    if single:
        wd = hr.assign(wd=(hr["day"] - 1) % 7).groupby(["wd", "day"])["customers"].sum()
        by_wd = wd.groupby("wd").mean().reindex(range(7), fill_value=0.0)
        best = int(by_wd.idxmax())
        c3 = kpi_card_html(
            "📅 Busiest weekday", _WEEKDAYS[best],
            sub=f'<div class="ba-delta">≈ {by_wd[best]:,.0f} customers</div>',
            graphic=columns_html(by_wd.round().astype(int).tolist(), _WEEKDAYS),
            help="Average customers per weekday. Columns = Monday → Sunday.",
            tone="info",
        )
    else:
        totals = hr.groupby("business_name")["customers"].sum().sort_values(ascending=False)
        c3 = kpi_card_html(
            "🏪 Busiest business", str(totals.index[0]),
            sub=f'<div class="ba-delta">{int(totals.iloc[0]):,} customers in total</div>',
            graphic=composition_html(list(totals.items()), colors=colors),
            help="Share of all customers per business (the 4 busiest, the rest as Other).",
        )
    return [c1, c2, c3]


def hourly_figure(agg: pd.DataFrame, colors: dict, theme: str) -> go.Figure:
    fig = go.Figure()
    for business, g in agg.groupby("business_name", sort=False):
        fig.add_trace(go.Scatter(
            x=g["hour"], y=g["avg_customers"], name=str(business), mode="lines+markers",
            line=dict(color=colors.get(business, OTHER_COLOR[theme]), width=2),
            marker=dict(size=6),
            hovertemplate="%{y:,.1f} customers<extra>" + str(business).replace("<", "&lt;") + "</extra>",
        ))
    fig.update_layout(
        height=400, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis_title="Hour of day", yaxis_title="Avg customers",
    )
    fig.update_xaxes(tickmode="array", tickvals=list(range(0, 24, 2)),
                     ticktext=[f"{h:02d}:00" for h in range(0, 24, 2)], range=[-0.5, 23.5])
    return fig


HOW_TO_READ_TRAFFIC = (
    "<b>How to read this chart.</b> Each line is one business. Across: the hours of the day. "
    "Up: how many customers walked in during that hour, on average over the days it was open "
    "at that hour. A gap in a line = the business was closed at that hour. "
    "<b>Use it to</b> open when your line would still be high, and put more staff on the "
    "peak hours (compare with the staffing in the Business Health Check)."
)


def render_hourly_traffic_section(bundle) -> None:
    from analysis.temporal_analyzer import calculate_hourly_traffic
    st.subheader("Hourly Customer Traffic")
    hr = getattr(bundle, "hour_reports", None) if bundle is not None else None
    if hr is None or hr.empty:
        st.info("Hourly customer traffic requires an HSG save file. Load one from the sidebar to unlock this section.")
        return

    businesses = sorted(hr["business_name"].dropna().unique().tolist())
    pick = st.selectbox("Business", ["All businesses"] + businesses, key="hourly_traffic_business_filter")
    business = None if pick == "All businesses" else pick
    sel = hr if business is None else hr[hr["business_name"] == business]
    agg = calculate_hourly_traffic(hr, business_filter=business)
    if agg.empty:
        st.warning("No hourly traffic data for this selection.")
        return

    st.caption(f"Last {hr['day'].nunique()} days of hourly reports stored in the save.")
    theme = ui_theme()
    colors = business_colors(home_businesses(bundle), theme)
    st.html(kpi_row_html(traffic_kpis(sel, agg, single=business is not None, colors=colors)))
    render_note(HOW_TO_READ_TRAFFIC)
    st.plotly_chart(hourly_figure(agg, colors, theme), use_container_width=True,
                    config={"displayModeBar": False})
