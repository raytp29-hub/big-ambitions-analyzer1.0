"""
Business Health Check Page
Compares actual player performance vs theoretical potential.
Requires: CSV uploaded + Schedule Optimizer configured.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from analysis.health_check import compute_health_check
from analysis.revenue_analyzer import extract_business_from_revenue
from core.game_data import display_to_internal


def render_health_check_page():
    st.title("Business Health Check")
    st.markdown(
        "Compare your actual business performance against the theoretical potential "
        "calculated from game data, building capacity, and operating hours."
    )

    # ================================================================
    # A. CHECK PREREQUISITES
    # ================================================================
    has_csv = st.session_state.get('df') is not None
    has_optimizer = st.session_state.get('business_setup') is not None
    has_schedule = bool(st.session_state.get('weekly_schedule'))

    if not has_csv and not has_optimizer:
        st.info(
            "This page requires:\n"
            "1. **CSV Upload** — upload your game CSV in the sidebar\n"
            "2. **Schedule Optimizer** — configure your business setup (type, building, furniture, schedule)"
        )
        return

    if not has_csv:
        st.warning("Upload your game CSV in the sidebar to see actual performance data.")
        return

    if not has_optimizer or not has_schedule:
        st.warning(
            "Configure your business in the **Schedule Optimizer** page first "
            "(business type, building size, furniture, and operating hours)."
        )
        return

    # ================================================================
    # B. BUSINESS MATCHING
    # ================================================================
    df = st.session_state.df
    business_names, _, _ = extract_business_from_revenue(df)

    if not business_names:
        st.error("No revenue data found in the CSV. Make sure the CSV contains revenue entries.")
        return

    # Get optimizer business info
    setup = st.session_state.business_setup
    optimizer_biz_display = setup.business_name  # e.g., "Coffee Shop"
    optimizer_biz_internal = display_to_internal(optimizer_biz_display)
    effective_capacity = st.session_state.get('effective_capacity', 0)
    weekly_schedule = st.session_state.get('weekly_schedule', [])

    # Auto-match: try to find the optimizer business in CSV names
    default_idx = 0
    for i, name in enumerate(sorted(business_names)):
        if name.lower() == optimizer_biz_display.lower():
            default_idx = i
            break

    col_select, col_info = st.columns([2, 3])
    with col_select:
        selected_csv_biz = st.selectbox(
            "Select business from CSV",
            sorted(business_names),
            index=default_idx,
            help="Choose which business from your CSV to analyze"
        )
    with col_info:
        st.markdown(
            f"**Optimizer config:** {optimizer_biz_display} · "
            f"**Capacity:** {effective_capacity}/h · "
            f"**Open days:** {sum(1 for ds in weekly_schedule if ds.is_open)}/7"
        )

    st.divider()

    # ================================================================
    # COMPUTE HEALTH CHECK
    # ================================================================
    result = compute_health_check(
        df=df,
        business_display_name=selected_csv_biz,
        business_internal_name=optimizer_biz_internal,
        effective_capacity=effective_capacity,
        weekly_schedule=weekly_schedule,
    )

    if result['n_days'] == 0:
        st.error(f"No revenue data found for '{selected_csv_biz}' in the CSV.")
        return

    # ================================================================
    # C. KPI METRIC CARDS
    # ================================================================
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        score = result['performance_score']
        st.metric(
            "Performance Score",
            f"{score:.0f}%",
            delta=f"{result['trend_direction']}" if result['trend_direction'] != 'stable' else None,
        )
    with c2:
        st.metric(
            "Avg Daily Revenue",
            f"${result['avg_daily_revenue']:,.0f}",
        )
    with c3:
        st.metric(
            "Profit Margin",
            f"{result['profit_margin']:.1f}%",
        )
    with c4:
        st.metric(
            "Cost / Revenue",
            f"{result['cost_revenue_ratio']:.0f}%",
        )

    st.divider()

    # ================================================================
    # D. GAUGE CHART + E. DAILY TREND (side by side)
    # ================================================================
    col_gauge, col_trend = st.columns([1, 2])

    with col_gauge:
        _render_gauge(result)

    with col_trend:
        _render_daily_trend(result)

    st.divider()

    # ================================================================
    # F. DIAGNOSTICS
    # ================================================================
    _render_diagnostics(result)

    # ================================================================
    # G. DETAIL TABLE
    # ================================================================
    _render_detail_table(result)


def _render_gauge(result: dict):
    """Render performance gauge chart."""
    score = min(result['performance_score'], 120)  # Cap visual at 120%
    rating = result['rating']

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={'suffix': '%', 'font': {'size': 36}},
        title={'text': f"Rating: {rating}", 'font': {'size': 16}},
        gauge={
            'axis': {'range': [0, 120], 'tickwidth': 1},
            'bar': {'color': '#1f77b4'},
            'steps': [
                {'range': [0, 40], 'color': '#ff4444'},
                {'range': [40, 65], 'color': '#ffaa44'},
                {'range': [65, 85], 'color': '#ffdd44'},
                {'range': [85, 120], 'color': '#44bb44'},
            ],
            'threshold': {
                'line': {'color': 'white', 'width': 3},
                'thickness': 0.8,
                'value': score,
            },
        },
    ))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def _render_daily_trend(result: dict):
    """Render actual vs theoretical revenue trend chart."""
    comp = result['daily_comparison']
    if comp.empty:
        st.info("No daily data available for trend chart.")
        return

    fig = go.Figure()

    # Theoretical line (dashed)
    fig.add_trace(go.Scatter(
        x=comp['game_day'],
        y=comp['theoretical'],
        mode='lines',
        name='Theoretical',
        line=dict(color='rgba(255,100,100,0.7)', width=2, dash='dash'),
    ))

    # Actual revenue line
    fig.add_trace(go.Scatter(
        x=comp['game_day'],
        y=comp['revenue'],
        mode='lines+markers',
        name='Actual Revenue',
        line=dict(color='#1f77b4', width=2),
        marker=dict(size=5),
        fill='tonexty',
        fillcolor='rgba(31,119,180,0.1)',
    ))

    fig.update_layout(
        title="Daily Revenue: Actual vs Theoretical",
        xaxis_title="Game Day",
        yaxis_title="Revenue ($)",
        height=280,
        margin=dict(l=20, r=20, t=40, b=10),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        hovermode='x unified',
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_diagnostics(result: dict):
    """Render diagnostic insights."""
    st.subheader("Diagnostic Insights")

    diagnostics = result['diagnostics']
    if not diagnostics:
        st.info("No diagnostics available.")
        return

    for diag in diagnostics:
        icon = diag['icon']
        msg = diag['message']
        severity = diag['severity']

        if severity == 'error':
            st.error(f"{icon} {msg}")
        elif severity == 'warning':
            st.warning(f"{icon} {msg}")
        elif severity == 'success':
            st.success(f"{icon} {msg}")
        else:
            st.info(f"{icon} {msg}")

    # Show theoretical breakdown
    theo = result['theoretical']
    if theo['revenue_per_customer'] > 0:
        st.caption(
            f"Theoretical model: **${theo['revenue_per_customer']:.2f}** avg revenue/customer · "
            f"**${theo['avg_daily']:.0f}** theoretical avg daily revenue · "
            f"**{result['n_days']}** days of data analyzed"
        )


def _render_detail_table(result: dict):
    """Render detailed daily comparison table."""
    comp = result['daily_comparison']
    if comp.empty:
        return

    with st.expander("Daily Performance Detail", expanded=False):
        display_df = comp[['game_day', 'revenue', 'theoretical', 'performance_pct', 'costs', 'profit']].copy()
        display_df.columns = ['Day', 'Revenue', 'Theoretical', 'Performance %', 'Costs', 'Profit']

        st.dataframe(
            display_df.style.format({
                'Revenue': '${:,.0f}',
                'Theoretical': '${:,.0f}',
                'Performance %': '{:.0f}%',
                'Costs': '${:,.0f}',
                'Profit': '${:,.0f}',
            }),
            use_container_width=True,
            hide_index=True,
        )
