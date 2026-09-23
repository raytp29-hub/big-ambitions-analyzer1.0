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
    WINDOW_DAYS, evaluate_business, open_hours_by_day, wage_shares,
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
        f'<div class="ba-muted ba-small">{len(items) - len(missing)}/{len(items)} met · {summary}. '
        'Hover an icon for its name.</div>' + demand_icons_html(items)
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

def _render_planner(bundle) -> None:
    categories = get_available_categories()
    category = st.selectbox(
        "Business Category",
        options=categories,
        key="hc_category"
    )


    business_type = get_business_tupes_for_category(category)

    busi_type = st.selectbox(
        "Business Type",
        options= business_type,
        key="hc_business_type"
    )

    internal_name = busi_type.replace(" ", "")
    ranked = rank_products(internal_name)

    rows = []

    for p in ranked:
        rows.append({
            "Product": p.name,
            "Price": f"${p.market_price:.2f}",
            "Cost":f"${p.wholesale_price:.2f}",
            "Margin":f"${p.margin:.2f}",
            "Sales Ratio": f"{p.sales_ratio:.2f}",
            "Impact": f"{p.impact:.2f}",
            "Probability": f"{p.probability:.0%}",
            "Score": f"${p.score:.2f}"
        })

    st.dataframe(pd.DataFrame(rows))


    st.caption("Score = Margin × Probability. Higher score = more profitable product to stock.")


    st.header("Where to Open - Zone Ranking")
    zone_rows = []

    zones = rank_zone(internal_name)

    for z in zones:
        zone_rows.append({
            "Zone": z.name,
            "Avg Traffic": z.avg_traffic,
            "Available Buildings": z.n_buildings,
            "Product Match": f"{z.product_match:.0%}"
        })

    st.dataframe(pd.DataFrame(zone_rows), hide_index= True)


    st.caption("Zones ranked by average foot traffic. More traffic = more potential customers.")



    # SECTION 2

    st.header(f"Break Even Analysis - ({busi_type})")


    col1, col2 = st.columns(2)

    with col1:
        business_location = st.selectbox(
            "Business Location",
            options= [z.name for z in zones],
            key= "hc_bl"
        )

    with col2:
        buildings = get_available_buildings(category)
        business_size = st.selectbox(
            "Business Size",
            options= buildings,
            format_func= lambda x: f"{x} {get_building_capacity(category,x)} cust/h",
            key= "hc_bk_size"
        )


    daily_rent = st.number_input("Daily Rent ($)", min_value=0, max_value=10000, value=100, key="hc_rent")


    building_cap = get_building_capacity(category, business_size)
    zone_traffic = next((z.avg_traffic for z in zones if z.name == business_location),0)

    result = compute_bep(internal_name, building_cap, zone_traffic, daily_rent)

    if result is None:
        st.error("The game's demand curve for this business type never reaches the model threshold: no theoretical opening hours.")
    else:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Daily Customers", f"{result.daily_customers:.0f}")
        with col2:
            st.metric("Daily Revenue", f"${result.revenue:.2f}")
        with col3:
            st.metric("Daily Costs", f"${result.costs:.2f}")
        with col4:
            st.metric("Daily Profit", f"${result.profit:.2f}")



        furniture_rows = [{"Name": f.name, "Qty": f.quantity, "Price": f"${f.price:.2f}", "Capacity": f"{f.capacity}/hr", "Total": f"${f.price * f.quantity}"} for f in result.furniture]


        st.dataframe(pd.DataFrame(furniture_rows), hide_index= True)

        st.caption("Minimum furniture needed to reach building capacity. Includes mandatory items (toilet, cleaning station, cash register, security locker).")

        col5, col6, col7 = st.columns(3)
        with col5:
            st.metric("Setup Cost", f"${result.setup_cost:,.2f}")
        with col6:
            st.metric("Employees Needed", result.employees)
        with col7:
            st.metric("Break Even", f"{result.break_even:.0f} days" if result.profit > 0 else "never",
                      help="Days to recover the setup cost. 'never' = the model makes a daily loss.")

        st.caption("Estimated daily figures based on optimal furniture, location traffic, and demand curve. Break Even = days to recover the setup cost.")

        fig = _demand_heatmap(internal_name, f"Demand Heatmap - Business Type: {busi_type}")
        st.plotly_chart(fig, use_container_width=True)


        st.caption("Brighter = higher demand. Use this to set your opening hours.")


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
