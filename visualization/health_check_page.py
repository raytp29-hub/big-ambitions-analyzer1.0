import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit.components.v1 as components


from analysis.health_check import (
    NEIGHBOURHOOD_NAMES, compute_bep, compute_performance, demand_matrix,
    generate_report, rank_products, rank_zone, compute_recommended_hours
)

from analysis.schedule_constraints import get_available_buildings, get_available_categories, get_building_capacity, get_business_tupes_for_category
from core.game_data import get_demand_multipliers, business_type_display_by_name
from analysis.revenue_analyzer import extract_business_from_revenue
from analysis.business_alerts import (
    NON_CUSTOMER_TYPES, SAT_WARNING, _street_label, build_context, demand_status,
)
from analysis.business_fit import (
    WINDOW_DAYS, core_products_for, evaluate_business, menu_actions, open_hours_by_day,
    wage_shares,
)
from analysis.staffing_fit import evaluate_staffing, staffing_to_df
from visualization.staffing_heatmap import staffing_heatmap_spec
from visualization.schedule_grid import assign_shift_employees, build_day_html, build_station_rows
from visualization.alerts_view import render_alerts_section
from visualization.ui_components import (
    Column, Raw, badge_html, demand_icons_html, kpi_card_html, kpi_row_html,
    ratio_gauge, render_note, render_open_table, share_gauge, theory_card_html,
)


DAY_ORDER = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

MODE_MINE = "My business (from save)"
MODE_PLAN = "Plan a new business"


def render_health_check_page():
    st.title("Business Health Check")

    # === LIVE STATUS dal save HSG (alert + customer demands) ===
    bundle = st.session_state.get("bundle")
    render_alerts_section(bundle)
    st.divider()
    st.header("Plan a Business")

    has_snapshot = bundle is not None and bundle.snapshot is not None
    if has_snapshot:
        mode = st.radio("Mode", [MODE_MINE, MODE_PLAN], horizontal=True, key="hc_mode",
                        label_visibility="collapsed")
    else:
        mode = MODE_PLAN
        st.caption("Load an HSG save to compare your existing businesses with the theoretical model.")

    if mode == MODE_MINE:
        _render_my_business(bundle)
    else:
        _render_planner(bundle)


# ============================================================================
# HELPER CONDIVISI
# ============================================================================

def _demand_heatmap(internal_name: str, title: str, open_hours: dict | None = None) -> go.Figure:
    """Heatmap della domanda; con open_hours oscura le ore in cui sei chiuso."""
    matrix = demand_matrix(internal_name)
    x = [f"{h:02d}:00" for h in range(24)]
    fig = px.imshow(matrix, x=x, y=DAY_ORDER, color_continuous_scale='YlOrRd', title=title)
    fig.update_layout(coloraxis_colorbar=dict(title="Demand"))

    if open_hours is not None:
        closed = np.full((7, 24), np.nan)
        for day_idx in range(7):
            hours = open_hours.get(day_idx + 1, set())
            for h in range(24):
                if h not in hours:
                    closed[day_idx][h] = 1
        fig.add_trace(go.Heatmap(
            z=closed, x=x, y=DAY_ORDER, showscale=False, hoverinfo="skip",
            colorscale=[[0, "rgba(40,40,40,0.75)"], [1, "rgba(40,40,40,0.75)"]],
        ))
    return fig


# ============================================================================
# MODALITÀ 1 — IL MIO BUSINESS (dal save)
# ============================================================================

def _render_demand_icons(bundle, address: str) -> None:
    status = demand_status(bundle.snapshot, build_context(bundle.snapshot))
    status = status[status["address"] == address]
    if status.empty:
        return
    items = [(r.demand_key, r.demand, bool(r.fulfilled)) for r in status.itertuples()]
    missing = [label for _, label, met in items if not met]
    summary = ("all met" if not missing else "missing: " + ", ".join(missing))
    st.html(
        '<div class="ba-section">Customer demands</div>'
        f'<div class="ba-muted ba-small">{len(items) - len(missing)}/{len(items)} met · {summary}.</div>'
        + demand_icons_html(items)
    )


def _render_satisfaction(bundle, address: str) -> None:
    b = bundle.snapshot.businesses
    b = b[b["address"] == address].iloc[0]
    scores = {
        "Customer service": b["sat_customer_service"],
        "Pricing":          b["sat_pricing"],
        "Cleanliness":      b["sat_cleanliness"],
        "Facility":         b["sat_facility"],
    }
    fig = go.Figure(go.Bar(
        x=list(scores.values()), y=list(scores.keys()), orientation="h",
        marker_color=["#1f9d55" if v >= SAT_WARNING else "#d64545" for v in scores.values()],
        text=[f"{v:.0f}" for v in scores.values()], textposition="inside",
    ))
    fig.add_vline(x=SAT_WARNING, line_dash="dash", line_color="grey")
    fig.update_layout(
        title=f"Satisfaction · overall {b['sat_overall']:.0f}", height=220,
        xaxis=dict(range=[0, 100]), margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


STATUS_TONE = {"ok": "ok", "warn": "warning", "bad": "critical", "info": "info"}
STATUS_WORD = {"ok": "on track", "warn": "watch", "bad": "fix", "info": "info"}

HOW_TO_READ_THEORY = (
    "<b>Theory</b> is what this building could do with its foot traffic, customer capacity and "
    "rent, open during the hours the game's demand curve says matter, using this business type's "
    "core products. <b>Actual</b> is what your save shows over the last {window} days. "
    "The bar is your value as a share of the theory (the white mark = 100%): "
    "green at 85% or more, yellow from 60%, red below. Customers and revenue in the theory are "
    "<b>estimates</b>: the game adds factors (marketing, prices, competition) the model can't see."
)
HOW_TO_READ_FIX = (
    "Every check where your business is below the model, worst first. <b>Fix</b> (red) = far "
    "from the theory, <b>watch</b> (yellow) = close but not there. Theory = what the model "
    "expects, You have = your save. The last column says what the gap is about."
)
HOW_TO_READ_HEATMAP = (
    "<b>How to read the heatmap.</b> Rows = weekdays, columns = hours. The colour is how many "
    "customers the game sends to this business type at that time (brighter = more). "
    "<b>Dark cells are the hours you are closed.</b> A bright cell covered by dark means "
    "customers you are losing: consider opening then."
)


def _profile_cards(profile) -> str:
    cards = [
        kpi_card_html("Type", business_type_display_by_name(profile.biz_name), compact=True,
                      help="Business type from your save."),
        kpi_card_html("Location", profile.neighbourhood, compact=True,
                      help=f"Neighbourhood of the building (size {profile.building_size or '?'})."),
        kpi_card_html("Traffic index", str(profile.traffic), compact=True,
                      help="Foot traffic of this address in the game data: more traffic = more "
                           "potential customers. The theory scales with it."),
        kpi_card_html("Capacity", f"{profile.capacity}/h", compact=True,
                      help="Most customers per hour this building can serve (from your save). "
                           "The theory never goes above it."),
        kpi_card_html("Rent", f"${profile.rent:,.0f}/day", compact=True,
                      help="Daily rent of this building, from your save."),
    ]
    return kpi_row_html(cards)


def _row(rows, metric):
    return next((r for r in rows if r.metric == metric), None)


def _theory_cards(bep, actual, rows, staffing, profile) -> str:
    """Le 3 card Theory vs Actual: revenue, clienti, salari/ricavo."""
    cards = []
    rev = _row(rows, "Daily revenue")
    if rev is not None:
        ratio = (actual.revenue_per_day / bep.revenue
                 if actual.revenue_per_day is not None and bep.revenue else None)
        note = (f"{ratio:.0%} of theory · estimate" if ratio is not None else "no sales data")
        cards.append(theory_card_html("Daily revenue", rev.actual, rev.theory, rev.status,
                                      note, *ratio_gauge(ratio)))
    cus = _row(rows, "Customers / day")
    if cus is not None:
        ratio = (actual.customers_per_day / bep.daily_customers
                 if actual.customers_per_day is not None and bep.daily_customers else None)
        note = (f"{ratio:.0%} of theory · " if ratio is not None else "") + \
               f"capacity {profile.capacity}/h · traffic {profile.traffic}"
        cards.append(theory_card_html("Customers / day", cus.actual, cus.theory, cus.status,
                                      note, *ratio_gauge(ratio)))
    wag = _row(rows, "Wages / revenue")
    if wag is not None:
        theo, mine = wage_shares(bep, actual, staffing)
        per_day = actual.wages_per_open_day * (len(actual.open_hours) or 1) / 7
        note = f"${per_day:,.0f} wages per day · avg ${actual.avg_hourly_wage:,.2f}/h"
        cards.append(theory_card_html("Wages / revenue", wag.actual, wag.theory, wag.status,
                                      note, *share_gauge(mine, theo), hint="lower is better"))
    return kpi_row_html(cards) if cards else ""


FIX_COLUMNS = [
    Column("status", "", align="left"),
    Column("metric", "Check", align="left"),
    Column("theory", "Theory", help="What the model expects for this building."),
    Column("actual", "You have", help="What your save shows."),
    Column("note", "Why", align="left"),
]


def _render_what_to_fix(rows) -> None:
    to_fix = sorted((r for r in rows if r.status in ("bad", "warn")), key=lambda r: r.status != "bad")
    st.subheader("What to fix first")
    if not to_fix:
        st.success("Nothing below the model: every check is on track.")
        return
    render_note(HOW_TO_READ_FIX)
    render_open_table(FIX_COLUMNS, [
        {"status": Raw(badge_html(STATUS_WORD[r.status], STATUS_TONE[r.status])),
         "metric": r.metric, "theory": r.theory, "actual": r.actual, "note": r.note}
        for r in to_fix
    ])


def _hours_advice(bundle, profile, address, bep, window):
    """Consigli sugli orari: ore del modello chiuse / ore aperte con pochi clienti veri."""
    from analysis.business_fit import _window
    from analysis.health_check import demand_matrix
    from analysis.hours_advice import hours_advice
    from analysis.staffing_fit import observed_customers
    if bep is None:
        return []
    days = _window(bundle.hour_reports, window)
    observed = observed_customers(bundle.hour_reports, profile.business_name, days) or None
    cap = min(sum(f.capacity * f.quantity for f in bep.furniture), profile.capacity) or profile.capacity
    return hours_advice(demand_matrix(profile.biz_name), bep.open_hours,
                        open_hours_by_day(bundle.snapshot, address), profile.traffic, cap, observed)


def _advice_sentence(a) -> tuple[str, str, str]:
    """(tono, titolo, spiegazione) per un HoursAdvice."""
    if a.kind == "closed_day":
        return ("warning", f"Open on {a.days_label}",
                f"{a.hours_label}: the game sends customers on those days and you're closed "
                f"— about {a.customers_per_week:,.0f} customers a week (model estimate).")
    if a.kind == "open_more":
        return ("warning", f"Open {a.hours_label} on {a.days_label}",
                f"demand is high then and you're closed — about {a.customers_per_week:,.0f} "
                "customers a week (model estimate).")
    per_hour = a.customers_per_week / max(len(a.days) * len(a.hours), 1)
    return ("info", f"Consider closing {a.hours_label} on {a.days_label}",
            f"outside the demand hours and only {per_hour:.1f} customers per hour in your save: "
            "you pay staff for almost nobody.")


def _issue_list(items: list[tuple[str, str, str]], numbered: bool = False) -> str:
    """Elenco con pallino di tono: (tono, titolo in grassetto, testo)."""
    from html import escape
    li = []
    for i, (tone, title, text) in enumerate(items, 1):
        num = f"{i}. " if numbered else ""
        li.append(f'<li style="--ba-tone: var(--ba-{tone})"><span class="ba-dot"></span>'
                  f'<b>{num}{escape(title)}</b> <span class="ba-muted">— {escape(text)}</span></li>')
    return f'<ul class="ba-issues">{"".join(li)}</ul>'


def _render_hours_advice(tips) -> None:
    st.markdown("**What we'd change in your hours**")
    if not tips:
        st.success("Your opening hours match the demand curve: nothing to change.")
        return
    opens = [t for t in tips if t.kind != "close"][:3]
    closes = [t for t in tips if t.kind == "close"][:3]
    st.html(_issue_list([_advice_sentence(t) for t in opens + closes]))


OUTCOME_METRICS = {"Daily revenue", "Customers / day", "Wages / revenue", "Opening hours", "Model"}


def _row_action(r) -> tuple[str, str, str] | None:
    """Una riga del confronto → azione concreta (None se è un risultato, non un'azione)."""
    tone = "critical" if r.status == "bad" else "warning"
    if r.metric.startswith("Furniture · "):
        name = r.metric.split(" · ", 1)[1]
        try:
            n = int(r.theory) - int(r.actual)
        except ValueError:
            n = 0
        return (tone, f"Buy {n} × {name}" if n > 0 else f"Check {name}",
                f"the model needs {r.theory}, you have {r.actual} ({r.note}).")
    if r.metric == "Core products sold":
        return (tone, "Stock the missing core products", r.note + ".")
    return None


def _names(items: list) -> str:
    """['A'] → 'A', ['A','B'] → 'A and B', ['A','B','C'] → 'A, B and C'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _menu_item(a) -> tuple[str, str, str]:
    """MenuAction → voce del piano."""
    what = _names(a.products)
    if a.furniture:
        tone = "critical"
        title = f"Add {what} to the menu"
        detail = (f"buy {a.buy} × {a.furniture} ({a.capacity:g}/h each), then stock "
                  f"{'it' if len(a.products) == 1 else 'them'}: core product"
                  f"{'' if len(a.products) == 1 else 's'} for this business type.")
    else:
        tone = "warning"
        title = f"Stock {what}"
        detail = (f"you already have the {a.equipment}: " if a.equipment else "") + \
                 f"core product{'' if len(a.products) == 1 else 's'} for this business type."
    return tone, title, detail


def _render_action_plan(bundle, address, rows, staffing, hours_tips, menu=()) -> None:
    """Mini report: le azioni più utili, prese da tutte le sezioni della pagina, in ordine."""
    items = []
    # 1. customer demands mancanti
    status = demand_status(bundle.snapshot, build_context(bundle.snapshot))
    missing = status[(status["address"] == address) & ~status["fulfilled"]]["demand"].tolist()
    if missing:
        items.append(("critical", "Add the missing customer demands",
                      ", ".join(missing) + ": customers expect them and satisfaction drops without."))
    # 2. prodotti chiave mancanti, raggruppati con il loro arredo ("Add Pizza to the menu"),
    #    poi gli altri arredi e prodotti (righe "fix" prima, poi "watch")
    covered = {a.furniture for a in menu if a.furniture}
    items += [_menu_item(a) for a in menu if a.furniture]
    for want in ("bad", "warn"):
        for r in rows:
            if r.status != want or r.metric in OUTCOME_METRICS:
                continue
            if menu and r.metric == "Core products sold":
                continue                              # già detto dalle azioni menu
            if r.metric.startswith("Furniture · ") and r.metric.split(" · ", 1)[1] in covered:
                continue
            act = _row_action(r)
            if act:
                items.append(act)
    items += [_menu_item(a) for a in menu if not a.furniture]
    # 3. orari: il consiglio più utile per tipo
    for kind in ("closed_day", "open_more", "close"):
        tip = next((t for t in hours_tips if t.kind == kind), None)
        if tip:
            items.append(_advice_sentence(tip))
    # 4. personale: risultato del solver se c'è, altrimenti lo spreco stimato
    entry = st.session_state.get(f"hc_opt::{address}")
    if entry and entry.get("bundle_id") == id(bundle) and entry["result"].success:
        from analysis.schedule_compare import compare_schedules
        cmp = compare_schedules(entry["setup"].employees, entry["current"], entry["result"])
        if cmp.saving > 0:
            items.append(("warning", "Adopt the optimized schedule",
                          f"saves ${cmp.saving:,.0f} a week with the same employees (see Staffing)."))
    elif staffing is not None and staffing.wasted_per_week >= 300:
        items.append(("warning", "Cut the extra shifts",
                      f"~${staffing.wasted_per_week:,.0f} a week goes to sales staff beyond what the "
                      "customers need: run the optimizer in Staffing to see where."))

    st.subheader("Your action plan")
    # contesto: dove sei rispetto al modello (risultato, non azione)
    rev = next((r for r in rows if r.metric == "Daily revenue"), None)
    lead = ""
    if rev is not None and rev.status in ("bad", "warn"):
        lead = (f"Revenue is {rev.actual} a day against {rev.theory} in the model. "
                "These are the likely causes, most urgent first.")
    if not items:
        st.success("Nothing urgent: this business is in line with the model.")
        return
    # "$" nel markdown di Streamlit apre una formula LaTeX: va scritto "\\$"
    st.caption((lead or "The most useful things to do for this business, collected from every "
                        "section above, most urgent first.").replace("$", "\\$"))
    st.html(f'<div class="ba-card" style="height:auto">{_issue_list(items[:6], numbered=True)}</div>')


def _render_my_business(bundle) -> None:
    biz = bundle.snapshot.businesses
    biz = biz[~biz["business_type"].isin(NON_CUSTOMER_TYPES)].sort_values("business_name")
    if biz.empty:
        st.info("No customer-facing businesses in this save.")
        return

    labels = {r.address: f"{r.business_name} — {_street_label(r.address)}" for r in biz.itertuples()}
    address = st.selectbox("Your business", options=list(labels), format_func=labels.get,
                           key="hc_my_business")
    window = WINDOW_DAYS

    staffing = evaluate_staffing(bundle, address, window)
    profile, bep, actual, rows = evaluate_business(bundle, address, window, staffing=staffing)
    if profile is None:
        st.warning("Business type not found in the game data.")
        return

    # --- Input del modello, letti dal save ---
    st.html(_profile_cards(profile))

    left, right = st.columns([3, 2])
    with left:
        _render_demand_icons(bundle, address)
    with right:
        _render_satisfaction(bundle, address)

    # --- Theory vs Actual: 3 card ---
    st.subheader("Theory vs Actual")
    if bep is None:
        st.info(rows[0].note if rows else "The theoretical model does not apply to this business.")
    else:
        render_note(HOW_TO_READ_THEORY.format(window=window))
        st.html(_theory_cards(bep, actual, rows, staffing, profile))

    # --- Personale ora per ora ---
    _render_staffing(bundle, address, staffing, window)

    # --- Cosa sistemare prima (tutte le righe del confronto, non solo le 3 card) ---
    _render_what_to_fix(rows)

    # --- Heatmap domanda con i tuoi orari ---
    st.subheader("Demand vs your opening hours")
    render_note(HOW_TO_READ_HEATMAP)
    fig = _demand_heatmap(
        profile.biz_name,
        f"Demand vs your opening hours — {profile.business_name}",
        open_hours=open_hours_by_day(bundle.snapshot, address),
    )
    st.plotly_chart(fig, use_container_width=True)
    hours_tips = _hours_advice(bundle, profile, address, bep, window)
    _render_hours_advice(hours_tips)

    # --- Mini report: le cose da fare, in ordine ---
    menu = menu_actions(bep, rows, core_products_for(profile.biz_name), actual.items_sold)
    _render_action_plan(bundle, address, rows, staffing, hours_tips, menu)


def _ui_theme() -> str:
    """'dark' o 'light': il tema attivo di Streamlit (st.context.theme dalla 1.46)."""
    try:
        kind = st.context.theme.type
        if kind in ("dark", "light"):
            return kind
    except Exception:
        pass
    try:
        return "dark" if st.get_option("theme.base") == "dark" else "light"
    except Exception:
        return "light"


HOW_TO_READ_STAFFING = (
    "<b>What this does.</b> The Schedule Optimizer takes this business as it is in your save "
    "(stations, employees with their wages and demands, opening hours) and the customers it "
    "really had per hour over the last {window} days, and builds the cheapest schedule that "
    "still covers them (+25% margin). Below you see your schedule and the optimized one side by "
    "side, and what changes for each role and employee. Costs are hours × hourly wage, so the "
    "two numbers compare like for like."
)
HOW_TO_READ_HEATMAP_STAFF = (
    "Blue = more people on shift than needed (extra cost) · red = fewer than needed · grey = "
    "matched · empty = closed with nobody on shift. Hover a cell for on shift / needed / customers. "
    "Needed = stations for that hour's customers (+25% margin, at least 1 while open); customers = "
    "average per weekday × hour over the last {window} days. Cleaning and security assume 1 person "
    "every open hour."
)
CHANGE_TONE = {"dropped": "critical", "fewer": "info", "more": "warning", "added": "warning",
               "same": "neutral"}


def _money_delta(v: float) -> str:
    return f"{'+' if v > 0 else '-' if v < 0 else ''}${abs(v):,.0f}"


def _run_optimizer(bundle, address, window):
    """Carica il business dal save e lancia il solver. Restituisce (setup, current, result)."""
    from analysis.schedule_compare import run_saved_business
    return run_saved_business(bundle, address, window)


def _render_schedule_compare(entry, window) -> None:
    from analysis.schedule_compare import compare_schedules
    setup, current, result = entry["setup"], entry["current"], entry["result"]
    for note in setup.notes:
        st.warning(note)
    if not result.success:
        st.error(f"The optimizer found no valid schedule: {result.status}. Usually the employees' "
                 "demands (hours, days off) can't all fit the opening hours: try it in the "
                 "Schedule Optimizer page, where you can relax them.")
        return

    cmp = compare_schedules(setup.employees, current, result)
    saving = cmp.saving
    share = saving / cmp.current_cost if cmp.current_cost else 0.0
    cards = [
        kpi_card_html("Your schedule (save)", f"${cmp.current_cost:,.0f}/week",
                      sub=f'<div class="ba-delta">{cmp.current_hours} staff-hours</div>',
                      help="Wages of the shifts in your save: hours × hourly wage.", tone="neutral",
                      compact=True),
        kpi_card_html("Optimized", f"${cmp.optimized_cost:,.0f}/week",
                      sub=f'<div class="ba-delta">{cmp.optimized_hours} staff-hours</div>',
                      help="Wages of the optimized schedule, same employees and wages.", tone="info",
                      compact=True),
        kpi_card_html("Saving" if saving >= 0 else "Extra cost",
                      f"{_money_delta(-saving)}/week",
                      sub=f'<div class="ba-delta"><b>{abs(share):.0%}</b> of your wage bill</div>',
                      help="Optimized − yours. Negative = you save. Positive = your schedule leaves "
                           "customer hours uncovered and the optimizer adds staff.",
                      tone="ok" if saving > 0 else "critical" if saving < 0 else "neutral",
                      compact=True),
    ]
    st.html(kpi_row_html(cards))

    cov = result.coverage_report or {}
    gaps = {r: d for r, d in cov.items() if d.get("real", 0) > 0.5}
    if gaps:
        st.warning("Not enough employees to cover every needed hour: " + "; ".join(
            f"{r} {d['real']:.0f} h uncovered (hire ~{d['suggest']})" for r, d in sorted(gaps.items())))
    if result.unmet_demands:
        st.caption("Employee demands the optimizer could not satisfy: " + "; ".join(result.unmet_demands[:6]))

    st.markdown("**What changes per role**")
    render_open_table([
        Column("role", "Role", align="left"),
        Column("now", "Now h/week"),
        Column("opt", "Optimized h/week"),
        Column("dh", "Δ hours", fmt=lambda v: f"{v:+d}"),
        Column("dc", "Δ wages/week", help="Optimized − now. Negative = saving."),
    ], [{"role": r.role, "now": r.current_hours, "opt": r.optimized_hours, "dh": r.delta_hours,
         "dc": Raw(badge_html(_money_delta(r.delta_cost),
                              "ok" if r.delta_cost < 0 else "critical" if r.delta_cost > 0 else "neutral"))}
        for r in cmp.roles])

    st.markdown("**What changes per employee**")
    render_open_table([
        Column("name", "Employee", align="left", sub="role"),
        Column("wage", "Wage", fmt=lambda v: f"${v:,.2f}/h"),
        Column("now", "Now h/week"),
        Column("opt", "Optimized h/week"),
        Column("change", "Change", help="dropped = no shifts in the optimized schedule; "
                                        "fewer / more = hours changed."),
    ], [{"name": e.name, "role": e.role, "wage": e.wage, "now": e.current_hours,
         "opt": e.optimized_hours,
         "change": Raw(badge_html(e.status if e.status in ("dropped", "same", "added")
                                  else f"{e.status} ({e.delta_hours:+d} h)", CHANGE_TONE[e.status]))}
        for e in cmp.employees])

    # --- griglie affiancate: stesso giorno, tuo sopra, ottimizzato sotto ---
    _render_day_grids(setup, current, result, cmp.current_cost, cmp.optimized_cost)


@st.fragment
def _render_day_grids(setup, current, result, current_cost: float, optimized_cost: float) -> None:
    """Fragment: cambiando giorno si ridisegna solo questo blocco, non tutta la pagina
    (niente ricalcolo di alert, confronto con la teoria, staffing…)."""
    stations = build_station_rows(setup.selected_furniture)
    open_days = [d.day_name for d in setup.weekly_schedule if d.is_open]
    if not stations or not open_days:
        st.info("No workstations or open days: the day grid is not available.")
        return
    st.markdown("**Shifts of one day**")
    day = st.radio("Day", open_days, horizontal=True, key=f"hc_opt_day_{setup.address}",
                   label_visibility="collapsed")
    height = 70 + 49 * (len(stations) + 1)
    panels = (
        ("Your schedule (save)",
         f"The shifts as they are in your save today · ${current_cost:,.0f}/week in wages.",
         current),
        ("Optimized",
         "The cheapest schedule that still covers your real customers (+25% margin), with the same "
         f"employees, wages and demands · ${optimized_cost:,.0f}/week.",
         result),
    )
    for title, desc, res in panels:
        st.html(f'<div class="ba-grid-title">{_esc(title)}</div>'
                f'<div class="ba-grid-desc">{_esc(desc)}</div>')
        assignment = assign_shift_employees(res, setup.employees, stations)
        components.html(build_day_html(day, res, stations, assignment, setup.employees),
                        height=height, scrolling=False)


def _role_detail_rows(staffing) -> list[dict]:
    kind = {"sales": "sales", "appointment": "appointment (indicative)", "presence": "presence (1 per open hour)"}
    return [{
        "status": Raw(badge_html(STATUS_WORD[r.status], STATUS_TONE[r.status])),
        "role": r.role, "kind": kind.get(r.kind, r.kind), "stations": r.stations,
        "peak": f"{r.peak_needed} / {r.peak_staffed}",
        "hours": f"{r.hours_needed} / {r.hours_staffed}",
        "people": f"{r.headcount_needed} / {r.headcount_actual}",
        "over": r.over_hours, "under": r.under_hours,
        "wasted": Raw(badge_html(f"${r.wasted_per_week:,.0f}", "critical" if r.wasted_per_week > 0 else "neutral")),
    } for r in staffing.roles]


ROLE_DETAIL_COLUMNS = [
    Column("status", "", align="left"),
    Column("role", "Role", align="left", sub="kind"),
    Column("stations", "Stations"),
    Column("peak", "Peak need / have", help="Most people needed in the same hour vs most on shift."),
    Column("hours", "Hours/week need / have"),
    Column("people", "Employees need / have"),
    Column("over", "Extra h", help="Person-hours on shift beyond the need."),
    Column("under", "Missing h", help="Person-hours needed but not on shift."),
    Column("wasted", "Extra cost/week", help="Extra hours × the role's average wage (sales roles)."),
]


def _render_staffing(bundle, address, staffing, window: int) -> None:
    st.subheader("Staffing — your schedule vs optimized")
    render_note(HOW_TO_READ_STAFFING.format(window=window))

    key = f"hc_opt::{address}"
    entry = st.session_state.get(key)
    if entry is not None and entry.get("bundle_id") != id(bundle):
        entry = None                                   # save ricaricato: risultato vecchio
    label = "Optimize this schedule" if entry is None else "Optimize again"
    if st.button(label, type="primary", key=f"hc_opt_btn_{address}"):
        with st.spinner("Running the Schedule Optimizer…"):
            try:
                setup, current, result = _run_optimizer(bundle, address, window)
            except Exception as e:                    # il solver non deve rompere la pagina
                st.error(f"Optimizer error: {type(e).__name__}: {e}")
                setup = None
            if setup is None:
                st.session_state.pop(key, None)
                entry = None
            else:
                entry = {"bundle_id": id(bundle), "setup": setup, "current": current, "result": result}
                st.session_state[key] = entry
    if entry is None:
        st.caption("Takes a few seconds. Nothing in your save is changed.")
    else:
        _render_schedule_compare(entry, window)

    # --- vista ora per ora (senza solver) ---
    if staffing is None or not staffing.roles:
        return
    with st.expander("Hour by hour: staff on shift vs needed, per role"):
        s1, s2, s3 = st.columns(3)
        s1.metric("Extra wages / week", f"${staffing.wasted_per_week:,.0f}",
                  help="Hours on sales roles beyond what the customers needed, × the role's average wage.")
        s2.metric("Share of wage bill", f"{staffing.wasted_share:.0%}")
        s3.metric("Customer data", "real (hour reports)" if staffing.customers_source == "observed"
                  else "game curve (no reports)")
        _render_role_heatmap(staffing)
        render_note(HOW_TO_READ_HEATMAP_STAFF.format(window=window))
        st.markdown("**Details per role**")
        render_open_table(ROLE_DETAIL_COLUMNS, _role_detail_rows(staffing))
        over = staffing.top_over_ranges(8)
        under = staffing.under_ranges()
        if over:
            st.markdown(f"**Overstaffed hours** (top {len(over)})")
            st.html("<ul class=\"ba-issues\">" + "".join(
                f"<li style=\"--ba-tone: var(--ba-info)\"><span class=\"ba-dot\"></span>{line}</li>"
                for line in map(_esc, over)) + "</ul>")
        if under:
            st.markdown(f"**Understaffed hours** ({len(under)})")
            st.html("<ul class=\"ba-issues\">" + "".join(
                f"<li style=\"--ba-tone: var(--ba-critical)\"><span class=\"ba-dot\"></span>{line}</li>"
                for line in map(_esc, under)) + "</ul>")


@st.fragment
def _render_role_heatmap(staffing) -> None:
    """Fragment: cambiando ruolo si ridisegna solo la heatmap."""
    order = {"sales": 0, "appointment": 1, "presence": 2}
    roles = [r.role for r in sorted(staffing.roles, key=lambda r: (order.get(r.kind, 9), r.role))]
    role = st.radio("Role", roles, horizontal=True, key="hc_staff_role_" + "|".join(roles),
                    label_visibility="collapsed")
    spec = staffing_heatmap_spec(staffing.grid(role), role, theme=_ui_theme())
    st.plotly_chart(go.Figure(spec), use_container_width=True, theme=None,
                    config={"displayModeBar": False})


def _esc(text) -> str:
    from html import escape
    return escape(str(text))


# ============================================================================
# MODALITÀ 2 — PIANIFICA UN NUOVO BUSINESS (input manuali, come prima)
# ============================================================================

HOW_TO_READ_PRODUCTS = (
    "Products this business type can sell, best first. <b>Score</b> = margin × probability that "
    "a customer buys it: the higher, the more it's worth stocking. Products marked <b>core</b> are "
    "the ones the break-even model below uses to estimate revenue per customer."
)
HOW_TO_READ_ZONES = (
    "Neighbourhoods ranked by average foot traffic of their buildings: more traffic = more "
    "potential customers. <b>Product match</b> = how many of this type's products sell in that area."
)
HOW_TO_READ_BEP = (
    "An <b>estimate</b> for one building: the model fills it with the minimum furniture to reach "
    "its customer capacity, opens it in the hours the game's demand curve says matter (day by day) "
    "and sells the core products. All figures are per calendar day. <b>Break even</b> = days to earn "
    "back the setup cost."
)
HOW_TO_READ_PLAN_HEATMAP = (
    "<b>How to read the heatmap.</b> Rows = weekdays, columns = hours, brighter = more customers "
    "for this business type. <b>Dark cells are outside the model's opening hours</b>: the model "
    "keeps the business open from the first to the last hour of each day where demand reaches 0.3."
)


def _core_names(ranked) -> set:
    """Stessa regola di compute_bep: prodotti con impact ≥ 0.90, altrimenti i primi 3."""
    core = [p for p in ranked if p.impact >= 0.90] or ranked[:3]
    return {p.name for p in core}


PRODUCT_COLUMNS = [
    Column("product", "Product", align="left", sub="core"),
    Column("price", "Price", fmt=lambda v: f"${v:,.2f}", help="Market price in the game data."),
    Column("cost", "Cost", fmt=lambda v: f"${v:,.2f}", help="Wholesale price."),
    Column("margin", "Margin", fmt=lambda v: f"${v:,.2f}", bar=True, help="Price − cost, per unit."),
    Column("prob", "Probability", fmt=lambda v: f"{v:.0%}",
           help="Chance a customer of this business type buys it."),
    Column("score", "Score", fmt=lambda v: f"${v:,.2f}", help="Margin × probability."),
]
ZONE_COLUMNS = [
    Column("zone", "Zone", align="left"),
    Column("traffic", "Avg traffic", fmt=lambda v: f"{v:,.0f}", bar=True,
           help="Average traffic index of the buildings in the zone."),
    Column("buildings", "Buildings", fmt=lambda v: f"{v:,.0f}", help="Buildings of this category in the zone."),
    Column("match", "Product match", fmt=lambda v: f"{v:.0%}",
           tone=lambda v: "ok" if v >= 0.8 else "warning" if v >= 0.5 else "critical"),
]
FURNITURE_COLUMNS = [
    Column("name", "Furniture", align="left", sub="kind"),
    Column("qty", "Qty"),
    Column("price", "Price", fmt=lambda v: f"${v:,.0f}"),
    Column("capacity", "Capacity", fmt=lambda v: f"{v:,.0f}/h" if v else "—",
           help="Customers per hour one piece can serve."),
    Column("total", "Total", fmt=lambda v: f"${v:,.0f}", bar=True),
]


def _render_planner(bundle) -> None:
    from visualization.home_sections import profit_tone

    c1, c2 = st.columns(2)
    with c1:
        category = st.selectbox("Business category", options=get_available_categories(), key="hc_category")
    with c2:
        busi_type = st.selectbox("Business type", options=get_business_tupes_for_category(category),
                                 key="hc_business_type")
    internal_name = busi_type.replace(" ", "")

    # --- prodotti ---
    st.subheader("What to sell")
    render_note(HOW_TO_READ_PRODUCTS)
    ranked = rank_products(internal_name)
    core = _core_names(ranked)
    render_open_table(PRODUCT_COLUMNS, [
        {"product": p.name, "core": Raw(badge_html("core", "info")) if p.name in core else None,
         "price": p.market_price, "cost": p.wholesale_price, "margin": p.margin,
         "prob": p.probability, "score": p.score}
        for p in ranked
    ])

    # --- zone ---
    st.subheader("Where to open")
    render_note(HOW_TO_READ_ZONES)
    zones = rank_zone(internal_name)
    render_open_table(ZONE_COLUMNS, [
        {"zone": z.name, "traffic": z.avg_traffic, "buildings": z.n_buildings, "match": z.product_match}
        for z in zones
    ])

    # --- break even ---
    st.subheader(f"Break-even — {busi_type}")
    c1, c2, c3 = st.columns(3)
    with c1:
        business_location = st.selectbox("Location", options=[z.name for z in zones], key="hc_bl")
    with c2:
        buildings = get_available_buildings(category)
        business_size = st.selectbox(
            "Building size", options=buildings,
            format_func=lambda x: f"{x} · {get_building_capacity(category, x)} customers/h",
            key="hc_bk_size",
        )
    with c3:
        daily_rent = st.number_input("Daily rent ($)", min_value=0, max_value=10000, value=100, key="hc_rent")

    building_cap = get_building_capacity(category, business_size)
    zone_traffic = next((z.avg_traffic for z in zones if z.name == business_location), 0)
    result = compute_bep(internal_name, building_cap, zone_traffic, daily_rent)

    if result is None:
        st.error("The game's demand curve for this business type never reaches the model threshold: "
                 "no theoretical opening hours.")
    else:
        render_note(HOW_TO_READ_BEP)
        profit = result.profit
        st.html(kpi_row_html([
            kpi_card_html("Customers / day", f"{result.daily_customers:,.0f}", compact=True,
                          help=f"Traffic {zone_traffic:,.0f} × demand curve, capped at {building_cap}/h."),
            kpi_card_html("Revenue / day", f"${result.revenue:,.0f}", compact=True,
                          help="Customers × what a customer spends on the core products."),
            kpi_card_html("Costs / day", f"${result.costs:,.0f}", compact=True,
                          help=f"Rent + wages ({result.staff_hours} staff-hours a week at $22/h, per "
                               "calendar day) + wholesale cost of the goods sold."),
            kpi_card_html("Profit / day", f"${profit:,.0f}" if profit >= 0 else f"-${abs(profit):,.0f}",
                          compact=True, tone=profit_tone(profit), help="Revenue − costs."),
        ]))
        days = len(result.open_hours)
        st.html(kpi_row_html([
            kpi_card_html("Opening hours (model)", f"{days} days · {result.weekly_hours} h/week",
                          sub=f'<div class="ba-delta">{result.open_hour:02d}:00 → {result.close_hour:02d}:00 at most</div>',
                          compact=True, help="Hours the model keeps the business open: see the heatmap below."),
            kpi_card_html("Setup cost", f"${result.setup_cost:,.0f}", compact=True,
                          help="Price of the furniture in the table below."),
            kpi_card_html("Staff at the busiest hour", str(result.employees), compact=True,
                          sub='<div class="ba-delta">' + _esc(" · ".join(
                              f"{r.peak} {r.role}" for r in result.staff)) + "</div>",
                          help=f"People on shift at the same time at peak. The model needs "
                               f"{result.staff_hours} staff-hours a week: cash registers for the customers "
                               "of each hour (+25% margin, at least 1), cleaning and security 1 per open hour."),
            kpi_card_html("Break even", f"{result.break_even:,.0f} days" if profit > 0 else "never",
                          compact=True, tone="ok" if profit > 0 else "critical",
                          help="Days to earn back the setup cost. 'never' = the model makes a daily loss."),
        ]))

        st.markdown("**Furniture the model needs**")
        render_open_table(FURNITURE_COLUMNS, [
            {"name": f.name, "kind": "workstation" if f.is_workstation else None, "qty": f.quantity,
             "price": f.price, "capacity": f.capacity, "total": f.price * f.quantity}
            for f in result.furniture
        ])
        st.caption("Minimum furniture to reach the building's capacity, plus the model's mandatory items "
                   "(toilet, cleaning station, cash register, security locker).")

        st.subheader("Demand and model hours")
        render_note(HOW_TO_READ_PLAN_HEATMAP)
        fig = _demand_heatmap(internal_name, f"Demand — {busi_type}", open_hours=result.open_hours)
        st.plotly_chart(fig, use_container_width=True)


    # SECTION 4 THEO VS EFFECTIVE
    # Con un save HSG il confronto vero sta nella modalità "My business":
    # qui resta il vecchio Performance Check per chi carica solo il CSV.
    if bundle is not None and bundle.snapshot is not None:
        return

    if st.session_state.df is not None and result is not None:
        st.header("Performance Check")

        business_names, _, _ = extract_business_from_revenue(st.session_state.df)

        selected_business = st.selectbox(
            "Your Business",
            options=business_names,
            key= "hc_busi_name_perf"
        )

        perf = compute_performance(st.session_state.df, selected_business, result)

        if perf is not None:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=perf.daily_data['day'],
                y=perf.daily_data['revenue'],
                mode='lines+markers',
                name='Actual Revenue',
            ))
            fig.add_trace(go.Scatter(
                x=[perf.daily_data['day'].min(), perf.daily_data['day'].max()],
                y=[perf.theo_revenue, perf.theo_revenue],
                mode='lines',
                name=f'Theoretical: ${perf.theo_revenue:,.0f}',
                line=dict(dash='dash', color='red')
            ))
            fig.update_layout(
                yaxis=dict(range=[0, max(perf.daily_data['revenue'].max(), perf.theo_revenue) * 1.1]),
                title= "Daily Revenue: Actual vs Theoretical"
            )
            st.plotly_chart(fig, use_container_width=True)

            st.caption("Blue line = your actual daily revenue from CSV. Red dashed line = theoretical maximum based on BEP analysis. Closer to red = better.")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Performance", f"{perf.performance_pct:.2f}%")
            with col2:
                st.metric("Rating", perf.rating)
            with col3:
                st.metric("Avg Daily Revenue", f"${perf.actual_revenue:,.0f}")
            with col4:
                st.metric("Days Analyzed", perf.n_days)

            st.caption("Performance = actual revenue as % of theoretical. Rating: Excellent (85%+), Good (65%+), Below Average (40%+), Poor (<40%).")

            fig_wages = go.Figure()

            fig_wages.add_trace(go.Scatter(
                x=perf.daily_data['day'],
                y=[perf.actual_wages] * len(perf.daily_data),
                mode='lines+markers',
                name='Actual Daily Wages'
            ))

            fig_wages.add_trace(go.Scatter(
                x=[perf.daily_data['day'].min(), perf.daily_data['day'].max()],
                y=[perf.theo_wages, perf.theo_wages],
                mode='lines',
                name=f'Theoretical: ${perf.theo_wages:,.0f}',
                line=dict(dash='dash', color='red')
            ))

            fig_wages.update_layout(
                title= "Daily Wages: Actual vs Theoretical"
            )

            st.plotly_chart(fig_wages, use_container_width=True)


            st.caption("Compare your actual wage spend vs the theoretical minimum based on optimal staffing.")


            col5, col6 = st.columns(2)
            wage_diff = perf.actual_wages - perf.theo_wages
            with col5:
                st.metric("Actual Daily Wages", f"${perf.actual_wages:,.0f}")
            with col6:
                st.metric("Theoretical Daily Wages", f"${perf.theo_wages:,.0f}",
                        delta=f"${wage_diff:+,.0f}", delta_color="inverse")

            rec_hours = compute_recommended_hours(internal_name)
            report = generate_report(perf, result, recommended_hours=rec_hours)

            # --- ACTION REPORT ---
            st.header("Action Report")

            for item in report:
                with st.expander(f"{item.icon} {item.title}", expanded=(item.priority <= 2)):
                    st.write(item.detail)


    elif st.session_state.df is None:
        st.info("Upload your CSV in the sidebar to compare actual vs theoretical performance")
