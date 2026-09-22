import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go


from analysis.health_check import (
    NEIGHBOURHOOD_NAMES, compute_bep, compute_performance,
    generate_report, rank_products, rank_zone, compute_recommended_hours
)

from analysis.schedule_constraints import get_available_buildings, get_available_categories, get_building_capacity, get_business_tupes_for_category
from core.game_data import get_demand_multipliers, business_type_display_by_name
from analysis.revenue_analyzer import extract_business_from_revenue
from analysis.business_alerts import (
    NON_CUSTOMER_TYPES, SAT_WARNING, _street_label, build_context, demand_status,
)
from analysis.business_fit import (
    STATUS_ICON, evaluate_business, fit_to_df, open_hours_by_day,
)
from analysis.staffing_fit import evaluate_staffing, staffing_to_df
from visualization.staffing_heatmap import staffing_heatmap_spec
from visualization.alerts_view import render_alerts_section


DAY_ORDER = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# Icone delle customer demands (come i "Standards" del sito di Peter:
# verde se soddisfatta, rossa se manca)
DEMAND_ICONS = {
    "ba:customerdemand_music":            "🎵",
    "ba:customerdemand_employeeuniforms": "👕",
    "ba:customerdemand_interiordesign":   "🖼️",
    "ba:customerdemand_seating":          "🪑",
    "ba:customerdemand_toilet":           "🚽",
    "ba:customerdemand_toiletprivacy":    "🚪",
    "ba:customerdemand_sink":             "🚰",
}

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

def _demand_matrix(internal_name: str) -> np.ndarray:
    """Domanda 7×24 (giorno × ora) dal game data: moltiplicatore giorno × ora."""
    demand = get_demand_multipliers(internal_name)
    hourly_24 = [0.0] * 24
    for h in demand['hourly']:
        for hour in range(h['start'], min(h['end'], 24)):
            hourly_24[hour] = h['multiplier']

    matrix = np.zeros((7, 24))
    for d in demand['daily']:
        day_idx = d['day'] - 1
        for hour in range(24):
            matrix[day_idx][hour] = round(d['multiplier'] * hourly_24[hour], 3)
    return matrix


def _demand_heatmap(internal_name: str, title: str, open_hours: dict | None = None) -> go.Figure:
    """Heatmap della domanda; con open_hours oscura le ore in cui sei chiuso."""
    matrix = _demand_matrix(internal_name)
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

def _render_demand_chips(bundle, address: str) -> None:
    status = demand_status(bundle.snapshot, build_context(bundle.snapshot))
    status = status[status["address"] == address]
    if status.empty:
        return
    chips = []
    for r in status.itertuples():
        color = "#1f9d55" if r.fulfilled else "#d64545"
        icon = DEMAND_ICONS.get(r.demand_key, "•")
        chips.append(
            f'<span title="{r.demand}: {"met" if r.fulfilled else "missing"}" '
            f'style="display:inline-block;margin:0 6px 6px 0;padding:4px 10px;'
            f'border-radius:999px;border:1px solid {color};color:{color};font-size:0.9rem">'
            f'{icon} {r.demand}</span>'
        )
    st.markdown("**Customer demands**", help="Green = met, red = missing. From the game data + your save.")
    st.markdown("".join(chips), unsafe_allow_html=True)


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


def _render_my_business(bundle) -> None:
    biz = bundle.snapshot.businesses
    biz = biz[~biz["business_type"].isin(NON_CUSTOMER_TYPES)].sort_values("business_name")
    if biz.empty:
        st.info("No customer-facing businesses in this save.")
        return

    labels = {r.address: f"{r.business_name} — {_street_label(r.address)}" for r in biz.itertuples()}
    col1, col2 = st.columns([3, 1])
    with col1:
        address = st.selectbox("Your business", options=list(labels), format_func=labels.get,
                               key="hc_my_business")
    with col2:
        window = st.select_slider("Actuals window (days)", options=[7, 14, 30], value=7,
                                  key="hc_fit_window")

    staffing = evaluate_staffing(bundle, address, window)
    profile, bep, actual, rows = evaluate_business(bundle, address, window, staffing=staffing)
    if profile is None:
        st.warning("Business type not found in the game data.")
        return

    # --- Input del modello, letti dal save (prima erano selectbox) ---
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Type", business_type_display_by_name(profile.biz_name))
    c2.metric("Location", profile.neighbourhood, help=f"Building {profile.building_size or '?'}")
    c3.metric("Traffic index", profile.traffic)
    c4.metric("Capacity", f"{profile.capacity}/h")
    c5.metric("Rent", f"${profile.rent:,.0f}/day")

    left, right = st.columns([3, 2])
    with left:
        _render_demand_chips(bundle, address)
    with right:
        _render_satisfaction(bundle, address)

    # --- Theory vs Actual ---
    st.subheader("Theory vs Actual")
    counts = {s: sum(r.status == s for r in rows) for s in STATUS_ICON}
    st.caption(" · ".join(f"{STATUS_ICON[s]} {n}" for s, n in counts.items() if n))
    st.dataframe(fit_to_df(rows), hide_index=True, use_container_width=True)
    st.caption(
        "Theory = compute_bep with this building's traffic, capacity, rent and your average wage. "
        f"Actual = your save (last {window} days of sales/customers; current schedule, staff and furniture). "
        "✅ ≥85% of theory · ⚠️ ≥60% · ❌ below · ℹ️ informative only."
    )

    # --- Personale ora per ora ---
    if staffing is not None and staffing.roles:
        _render_staffing(staffing, window)

    # --- Cosa sistemare prima ---
    to_fix = [r for r in rows if r.status in ("bad", "warn")]
    if to_fix:
        st.subheader("What to fix first")
        for r in sorted(to_fix, key=lambda r: r.status != "bad"):
            st.markdown(f"{STATUS_ICON[r.status]} **{r.metric}** — theory {r.theory}, you have {r.actual}. {r.note}")

    # --- Heatmap domanda con i tuoi orari ---
    fig = _demand_heatmap(
        profile.biz_name,
        f"Demand vs your opening hours — {profile.business_name}",
        open_hours=open_hours_by_day(bundle.snapshot, address),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Brighter = higher demand. Dark cells = hours you are closed: bright + dark means lost customers.")

    if bep is not None:
        with st.expander("Model details (theoretical setup for this building)"):
            furniture_rows = [{"Name": f.name, "Qty": f.quantity, "Price": f"${f.price:,.2f}",
                               "Capacity": f"{f.capacity}/hr", "Total": f"${f.price * f.quantity:,.0f}"}
                              for f in bep.furniture]
            st.dataframe(pd.DataFrame(furniture_rows), hide_index=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("Theoretical daily profit", f"${bep.profit:,.0f}")
            m2.metric("Setup cost", f"${bep.setup_cost:,.0f}")
            m3.metric("Profitable hours (model)", f"{bep.open_hour:02d}:00-{bep.close_hour:02d}:00")


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


def _render_staffing(staffing, window: int) -> None:
    st.subheader("Staffing — theory vs actual")
    s1, s2, s3 = st.columns(3)
    s1.metric("Extra wages / week", f"${staffing.wasted_per_week:,.0f}",
              help="Hours on sales roles beyond what the customers needed, × the role's average wage.")
    s2.metric("Share of wage bill", f"{staffing.wasted_share:.0%}")
    s3.metric("Customer data", "real (hour reports)" if staffing.customers_source == "observed"
              else "game curve (no reports)")

    # --- heatmap per ruolo: in turno − necessari, giorno × ora ---
    order = {"sales": 0, "appointment": 1, "presence": 2}
    roles = [r.role for r in sorted(staffing.roles, key=lambda r: (order.get(r.kind, 9), r.role))]
    # chiave legata ai ruoli: cambiando business il radio non tiene un ruolo che non c'è
    role = st.radio("Role", roles, horizontal=True, key="hc_staff_role_" + "|".join(roles),
                    label_visibility="collapsed")
    spec = staffing_heatmap_spec(staffing.grid(role), role, theme=_ui_theme())
    st.plotly_chart(go.Figure(spec), use_container_width=True, theme=None,
                    config={"displayModeBar": False})
    st.caption(
        "Blue = more people on shift than needed (extra cost) · red = fewer than needed · "
        "grey = matched · empty = closed with nobody on shift. Hover a cell for on shift / needed / customers. "
        f"Needed = stations for that hour's customers (+25% margin, at least 1 while open); "
        f"customers = average per weekday × hour over the last {window} days. "
        "Cleaning and security assume 1 person every open hour."
    )

    with st.expander("Details per role"):
        st.dataframe(staffing_to_df(staffing), hide_index=True, use_container_width=True)
    over = staffing.top_over_ranges(8)
    under = staffing.under_ranges()
    if over:
        with st.expander(f"Overstaffed hours (top {len(over)})"):
            for line in over:
                st.markdown(f"- {line}")
    if under:
        with st.expander(f"Understaffed hours ({len(under)})"):
            for line in under:
                st.markdown(f"- {line}")


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
        st.error("This business is not profitable with these parameters.")
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
            st.metric("Break Even", f"{result.break_even:.0f} days")

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
