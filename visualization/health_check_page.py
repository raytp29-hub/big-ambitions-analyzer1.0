"""
Business Health Check Page
Four sections:
  1. Product ranking (what to sell)
  2. Zone ranking (where to open)
  3. BEP & theoretical projection (minimum setup)
  4. Performance check (actual vs theoretical, requires CSV)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from analysis.health_check import (
    rank_products, rank_zones, get_building_options,
    compute_bep, compute_performance, analyze_schedule, compute_optimal_setup, DAY_NAMES,
)
from analysis.revenue_analyzer import extract_business_from_revenue
from core.game_data import (
    get_business_categories,
    get_businesses_for_category,
    get_products_for_business,
    get_demand_multipliers,
    get_all_business_types,
    get_furniture_for_business,
    format_item_name,
    _game_data,
)

_P = "hc_"


def _key(n: str) -> str:
    return f"{_P}{n}"


def render_health_check_page():
    st.title("Business Health Check")

    # --- Business type selection ---
    col_cat, col_type = st.columns(2)
    with col_cat:
        category = st.selectbox("Category", get_business_categories(), key=_key("cat"))
    with col_type:
        raw_names = get_businesses_for_category(category)
        display_names = [format_item_name(n) for n in raw_names]
        biz_display = st.selectbox("Business Type", display_names, key=_key("type"))

    internal = biz_display.replace(' ', '') if biz_display else None
    if not internal:
        return

    products = get_products_for_business(internal)
    if not products:
        st.warning("No product data for this business type.")
        return

    # Get buildings for reuse across sections
    all_bt = get_all_business_types()
    buildings = get_building_options(internal, all_bt)

    st.divider()

    # ==================================================================
    # SECTION 1: PRODUCT RANKING
    # ==================================================================
    st.header("1. What to Sell — Product Ranking")

    ranked = rank_products(internal)
    rows = []
    for p in ranked:
        rows.append({
            'Product': p.name,
            'Price': f"${p.market_price:.2f}",
            'Cost': f"${p.wholesale_price:.2f}",
            'Margin': f"${p.margin:.2f}",
            'SalesRatio': f"{p.sales_ratio:.0%}",
            'Impact': f"{p.impact:.0%}",
            'Eff.Prob': f"{p.effective_ratio:.0%}",
            'Score': f"${p.score:.2f}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    total_rev = sum(p.market_price * p.effective_ratio for p in ranked)
    total_cost = sum(p.wholesale_price * p.effective_ratio for p in ranked)
    st.caption(f"Expected per customer: **${total_rev:.2f}** revenue · **${total_cost:.2f}** cost · **${total_rev - total_cost:.2f}** profit")

    st.divider()

    # ==================================================================
    # SECTION 2: WHERE TO OPEN — Zone Ranking
    # ==================================================================
    st.header("2. Where to Open — Zone Ranking")

    zones = rank_zones(internal, _game_data)
    if zones:
        z_rows = []
        for z in zones:
            z_rows.append({
                'Zone': z.name,
                'Avg Traffic': z.avg_traffic,
                'Available Buildings': z.n_buildings,
                'Product Match': f"{z.product_match:.0%}",
            })
        st.dataframe(pd.DataFrame(z_rows), use_container_width=True, hide_index=True)
        restricted = [z for z in zones if z.product_match < 1.0]
        if restricted:
            st.caption("Some products have neighbourhood restrictions — zones with lower Product Match won't sell the full catalog.")
    else:
        st.info("No zone data available for this business type.")

    st.divider()

    # ==================================================================
    # SECTION 3: BEP & THEORETICAL PROJECTION
    # ==================================================================
    st.header("3. Break-Even Analysis")

    col_bld, col_traffic = st.columns(2)
    with col_bld:
        building_code = st.selectbox(
            "Building size",
            [b.code for b in buildings] if buildings else [],
            format_func=lambda c: f"{c} — {next((b.capacity for b in buildings if b.code == c), 0)} cust/hr cap",
            key=_key("bep_bld"),
        )
    with col_traffic:
        bep_traffic = st.number_input("Traffic Index", 1, 100, 30, key=_key("bep_ti"),
                                      help="Found in-game on the building info panel")

    col_rent, col_wage = st.columns(2)
    with col_rent:
        daily_rent = st.number_input("Daily rent ($)", 0, 10000, 100, key=_key("rent"))
    with col_wage:
        hourly_wage = st.number_input("Avg hourly wage ($)", 0, 200, 18, key=_key("wage"))

    col_sh, col_eh = st.columns(2)
    with col_sh:
        bep_start = st.number_input("Opening hour", 0, 23, 8, key=_key("bep_sh"))
    with col_eh:
        bep_end = st.number_input("Closing hour", 0, 23, 22, key=_key("bep_eh"))

    # Open days selection
    st.caption("**Open days**")
    day_cols = st.columns(7)
    open_days = []
    for i, d in enumerate(DAY_NAMES):
        with day_cols[i]:
            open_days.append(st.checkbox(d[:3], value=True, key=_key(f"day_{i}")))

    # Product selection
    all_products = rank_products(internal)
    product_names = [p.internal_name for p in all_products]
    product_display = [f"{p.name} (${p.market_price:.0f})" for p in all_products]
    selected_idx = st.multiselect("Products in your store", product_display,
                                   default=product_display, key=_key("bep_prods"))
    sel_products = [product_names[product_display.index(p)] for p in selected_idx] if selected_idx else None

    building_cap = next((b.capacity for b in buildings if b.code == building_code), 0)

    bep = compute_bep(internal, building_cap, bep_traffic, daily_rent, hourly_wage,
                      bep_start, bep_end, open_days, sel_products)

    if bep:
        _render_bep(bep)

        # Schedule analysis
        sched = analyze_schedule(
            internal, bep_traffic, building_cap,
            bep_start, bep_end, open_days,
        )
        if sched:
            _render_schedule(sched)
    else:
        st.warning("Cannot calculate BEP for this business type.")

    st.divider()

    # ==================================================================
    # SECTION 5: OPTIMIZER
    # ==================================================================
    st.header("5. Optimizer — Best Setup")

    if bep:
        opt = compute_optimal_setup(internal, building_cap, bep_traffic, daily_rent,
                                     hourly_wage, bep_start, bep_end, open_days, sel_products)
        if opt:
            _render_optimizer(opt)
        else:
            st.warning("Cannot compute optimal setup for this business type.")
    else:
        st.info("Configure Section 3 (BEP) first to run the optimizer.")

    st.divider()

    # ==================================================================
    # SECTION 4: PERFORMANCE CHECK (requires CSV)
    # ==================================================================
    st.header("4. How's It Going — Performance Check")

    df = st.session_state.get('df')
    if df is None:
        st.info("Upload your CSV in the sidebar to compare actual vs theoretical performance.")
        return

    business_names, _, _ = extract_business_from_revenue(df)
    if not business_names:
        st.warning("No revenue data in CSV.")
        return

    selected_biz = st.selectbox(
        "Select your business from CSV",
        sorted(business_names),
        key=_key("csv_biz"),
    )

    # Furniture selection (compact)
    st.subheader("Furniture Setup")
    furniture_list = get_furniture_for_business(internal)
    selected_furniture = []

    if not furniture_list:
        st.warning("No furniture data for this business type.")
        return

    for i, f in enumerate(furniture_list):
        is_secondary = bool(f.get('secondary_products'))
        label = f"{f['display_name']} ({f['added_customers_per_hour']}/hr)"
        if is_secondary:
            prods = ', '.join(format_item_name(p) for p in f['secondary_products'][:3])
            label += f" — secondary: {prods}"

        cols = st.columns([4, 1, 1])
        with cols[0]:
            checked = st.checkbox(label, key=_key(f"f_{i}"))
        with cols[1]:
            qty = st.number_input(
                "Qty", 1, 100, 1,
                disabled=not checked,
                key=_key(f"q_{i}"),
                label_visibility="collapsed",
            )
        if checked:
            selected_furniture.append({
                'name': f['display_name'],
                'capacity': f['added_customers_per_hour'] * qty,
            })

    if not selected_furniture:
        st.info("Select at least one furniture item.")
        return

    # Building + traffic for performance check
    col_pb, col_pt = st.columns(2)
    with col_pb:
        perf_building = st.selectbox(
            "Your building",
            [b.code for b in buildings] if buildings else [],
            format_func=lambda c: f"{c} — {next((b.capacity for b in buildings if b.code == c), 0)} cust/hr cap",
            key=_key("perf_bld"),
        )
    with col_pt:
        perf_traffic = st.number_input("Traffic Index", 1, 100, 30, key=_key("perf_ti"),
                                       help="Found in-game on the building info panel")

    perf_cap = next((b.capacity for b in buildings if b.code == perf_building), 0)

    # Check furniture bottleneck — warn if any furniture < traffic_index
    serving = [f['capacity'] for f in selected_furniture if f['capacity'] > 0]
    furniture_cap = min(serving) if serving else 0
    if furniture_cap < perf_traffic:
        st.warning(
            f"Furniture bottleneck ({furniture_cap}/hr) is below your traffic index ({perf_traffic}). "
            f"You may be losing customers!"
        )

    st.caption(
        f"Traffic Index: **{perf_traffic}** · "
        f"Building cap: **{perf_cap}/hr** · "
        f"Furniture min: **{furniture_cap}/hr**"
    )

    col_s, col_e = st.columns(2)
    with col_s:
        start_h = st.number_input("Open", 0, 23, 8, key=_key("sh"))
    with col_e:
        end_h = st.number_input("Close", 0, 23, 22, key=_key("eh"))

    if st.button("Run Health Check", type="primary", key=_key("run")):
        result = compute_performance(
            df, selected_biz, internal,
            perf_traffic, perf_cap, start_h, end_h,
        )

        if result is None:
            st.error(f"No revenue data found for '{selected_biz}'.")
            return

        _render_performance(result)


# ============================================================================
# RENDER HELPERS
# ============================================================================

def _render_bep(bep):
    """Render BEP analysis results."""
    # Optimal furniture table
    st.subheader("Optimal Furniture Setup")
    f_rows = []
    for f in bep.furniture:
        f_rows.append({
            'Furniture': format_item_name(f.name),
            'Products': ', '.join(format_item_name(p) for p in f.products_served) if f.products_served else 'Workstation',
            'Cap/unit': f"{f.capacity_each}/hr",
            'Qty': f.qty,
            'Total Cap': f"{f.total_capacity}/hr",
            'Unit $': f"${f.unit_price:,.0f}",
            'Total $': f"${f.total_price:,.0f}",
        })
    st.dataframe(pd.DataFrame(f_rows), use_container_width=True, hide_index=True)

    st.caption(
        f"Total furniture cost: **${bep.total_furniture_cost:,.0f}** · "
        f"Traffic Index: **{bep.traffic_index}** · "
        f"Building cap: **{bep.building_capacity}/hr** · "
        f"Employees: **{bep.n_employees}**"
    )

    # Daily projection
    st.subheader("Daily Projection")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Avg Customers/day", f"{bep.theo_daily_customers:.0f}")
    with c2:
        st.metric("Daily Revenue", f"${bep.theo_daily_revenue:,.0f}")
    with c3:
        st.metric("Daily Costs", f"${bep.total_daily_costs:,.0f}")
    with c4:
        color = "normal" if bep.is_profitable else "inverse"
        st.metric("Daily Profit", f"${bep.daily_profit:,.0f}", delta_color=color)

    # Cost breakdown
    with st.expander("Cost Breakdown"):
        st.markdown(f"""
| Cost | Daily |
|------|-------|
| Rent | ${bep.daily_rent:,.0f} |
| Wages ({bep.n_employees} employees) | ${bep.daily_wages:,.0f} |
| Wholesale (products) | ${bep.theo_daily_wholesale:,.0f} |
| **Total** | **${bep.total_daily_costs:,.0f}** |
""")
        st.markdown(f"""
| Revenue | Per Customer |
|---------|-------------|
| Revenue | ${bep.rev_per_customer:.2f} |
| Wholesale cost | ${bep.cost_per_customer:.2f} |
| Margin | ${bep.profit_per_customer:.2f} |
""")

    # BEP metrics
    st.subheader("Break-Even Point")
    c1, c2 = st.columns(2)
    with c1:
        if bep.bep_customers_per_day < float('inf'):
            st.metric("Min customers/day to break even", f"{bep.bep_customers_per_day:.0f}")
        else:
            st.metric("Min customers/day to break even", "N/A")
    with c2:
        if bep.bep_days_to_recover < float('inf') and bep.bep_days_to_recover > 0:
            st.metric("Days to recover furniture cost", f"{bep.bep_days_to_recover:.0f}")
        else:
            st.metric("Days to recover furniture cost", "N/A")

    if bep.is_profitable:
        pct_used = (bep.bep_customers_per_day / bep.theo_daily_customers * 100) if bep.theo_daily_customers > 0 else 0
        if pct_used < 50:
            st.success(f"Healthy margin — BEP at {pct_used:.0f}% of theoretical capacity.")
        elif pct_used < 80:
            st.info(f"Tight margin — BEP at {pct_used:.0f}% of theoretical capacity.")
        else:
            st.warning(f"Very tight — BEP at {pct_used:.0f}% of theoretical capacity. Little room for error.")
    else:
        st.error("This setup is NOT profitable with the given rent and wages.")


def _render_schedule(sched):
    """Render schedule coverage analysis."""
    st.subheader("Schedule Coverage")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Traffic Captured", f"{sched.coverage_pct:.0f}%")
    with c2:
        st.metric("Weekly Customers", f"{sched.current_weekly:,.0f}")
    with c3:
        st.metric("Max Possible (24/7)", f"{sched.max_weekly:,.0f}")

    # Suggestions
    if sched.missed_by_days:
        st.markdown("**Closed days with lost traffic:**")
        for d in sched.missed_by_days:
            st.caption(f"  {d['day']}: ~{d['lost_customers']:.0f} customers lost")

    if sched.missed_by_hours:
        st.markdown("**Top hours outside your schedule with traffic:**")
        for h in sched.missed_by_hours:
            st.caption(f"  {h['hour']}: ~{h['avg_daily_lost']:.0f} customers/day lost")

    if sched.coverage_pct >= 90:
        st.success("Your schedule captures most of the available traffic.")
    elif sched.coverage_pct >= 70:
        st.info("Good coverage. Check the suggestions above for potential improvements.")
    else:
        st.warning("You're missing significant traffic. Consider extending hours or opening more days.")


def _render_performance(r):
    """Render performance check results."""
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        delta = r.trend if r.trend != 'stable' else None
        st.metric("Performance", f"{r.performance_pct:.0f}%", delta=delta)
    with c2:
        st.metric("Avg Daily Revenue", f"${r.actual_avg_revenue:,.0f}")
    with c3:
        st.metric("Theoretical Avg", f"${r.theo_avg_revenue:,.0f}")
    with c4:
        st.metric("Rating", r.rating)

    actual = r.actual_data
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=actual['game_day'], y=actual['theoretical'],
        mode='lines', name='Theoretical',
        line=dict(color='rgba(255,100,100,0.7)', dash='dash'),
    ))
    fig.add_trace(go.Scatter(
        x=actual['game_day'], y=actual['revenue'],
        mode='lines+markers', name='Actual',
        line=dict(color='#1f77b4'),
        fill='tonexty', fillcolor='rgba(31,119,180,0.1)',
    ))
    fig.update_layout(
        title="Daily Revenue: Actual vs Theoretical",
        xaxis_title="Game Day", yaxis_title="Revenue ($)",
        height=350, hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=1, xanchor='right'),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Daily Detail"):
        display = actual[['game_day', 'revenue', 'theoretical', 'costs', 'profit']].copy()
        display.columns = ['Day', 'Revenue', 'Theoretical', 'Costs', 'Profit']
        st.dataframe(
            display.style.format({
                'Revenue': '${:,.0f}', 'Theoretical': '${:,.0f}',
                'Costs': '${:,.0f}', 'Profit': '${:,.0f}',
            }),
            use_container_width=True, hide_index=True,
        )


def _render_optimizer(opt):
    """Render optimizer comparison: current vs optimal setup."""
    # --- Current vs Optimal comparison ---
    st.subheader("Current vs Optimal")
    cols = st.columns(4)
    labels = ['Daily Profit', 'Daily Revenue', 'Daily Costs', 'Avg Customers']
    current = [opt.current_daily_profit, opt.current_daily_revenue, opt.current_daily_costs, opt.current_customers]
    optimal = [opt.best_daily_profit, opt.best_daily_revenue, opt.best_daily_costs, opt.best_customers]
    fmts = ['${:,.0f}', '${:,.0f}', '${:,.0f}', '{:,.0f}']

    for col, lbl, cur, best, fmt in zip(cols, labels, current, optimal, fmts):
        with col:
            delta = best - cur
            d_str = f"+{fmt.format(delta)}" if delta > 0 else fmt.format(delta)
            st.metric(lbl, fmt.format(best), delta=d_str if abs(delta) > 0.5 else None)

    if opt.improvement_pct > 5:
        st.success(f"Potential improvement: **+{opt.improvement_pct:.0f}%** daily profit with optimal setup.")
    elif opt.improvement_pct > 0:
        st.info(f"Minor improvement possible: **+{opt.improvement_pct:.0f}%**. Your setup is close to optimal.")
    else:
        st.success("Your current setup is already at or near optimal!")

    # --- Optimal schedule ---
    st.subheader("Optimal Schedule")
    opt_days_str = ', '.join(DAY_NAMES[i][:3] for i in range(7) if opt.best_days[i])
    closed_days = [DAY_NAMES[i][:3] for i in range(7) if not opt.best_days[i]]
    st.markdown(
        f"**Hours:** {opt.best_start:02d}:00 – {opt.best_end:02d}:00 · "
        f"**Open:** {opt_days_str}" +
        (f" · **Closed:** {', '.join(closed_days)}" if closed_days else "")
    )

    # --- Profit heatmap ---
    with st.expander("Hourly Profit Heatmap"):
        hm_data = []
        for dow in range(7):
            for h in range(24):
                hm_data.append({'Day': DAY_NAMES[dow][:3], 'Hour': h, 'Profit': opt.schedule_heatmap[dow][h]})
        hm_df = pd.DataFrame(hm_data)
        pivot = hm_df.pivot(index='Day', columns='Hour', values='Profit')
        pivot = pivot.reindex([DAY_NAMES[i][:3] for i in range(7)])

        fig = go.Figure(data=go.Heatmap(
            z=pivot.values, x=[f"{h:02d}" for h in range(24)],
            y=[DAY_NAMES[i][:3] for i in range(7)],
            colorscale=[[0, '#d32f2f'], [0.5, '#fff9c4'], [1, '#388e3c']],
            zmid=0, text=[[f"${v:.0f}" for v in row] for row in pivot.values],
            texttemplate="%{text}", textfont={"size": 9},
        ))
        fig.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0),
                          title="Net profit per hour (after wage cost)", xaxis_title="Hour")
        st.plotly_chart(fig, use_container_width=True)

    # --- Product contributions ---
    with st.expander("Product Profit Contributions"):
        p_rows = [{'Product': c['name'],
                    'Margin': f"${c['margin']:.2f}",
                    'Eff.Prob': f"{c['eff_ratio']:.0%}",
                    'Profit/Customer': f"${c['profit_contrib']:.2f}",
                    'In Optimal': '✓' if c['internal'] in opt.best_products else '✗'}
                   for c in sorted(opt.product_contributions, key=lambda x: -x['profit_contrib'])]
        st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)
