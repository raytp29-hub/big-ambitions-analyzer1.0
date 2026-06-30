"""
Game Data Explorer Page
Analyzes game data (demand curves, product margins, business comparison)
without requiring player CSV upload.
"""
import sys
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.game_data import (
    get_business_categories,
    get_businesses_for_category,
    get_demand_multipliers,
    get_all_products_with_margins,
    get_business_comparison_data,
    get_products_for_business,
    get_employee_roles_for_business,
    format_item_name,
)


# ============================================================================
# CONSTANTS & MAPPINGS
# ============================================================================

# Neighbourhood ID -> display name (from cross-referencing game data)
NEIGHBOURHOOD_NAMES = {
    0: 'Murray Hill',
    1: 'Industry City',
    2: 'Midtown',
    3: "Hell's Kitchen",
    5: 'Lower Manhattan',
    6: 'Garment District',
}

# Product internal name -> in-game display name
# (localization strings not extractable from asset bundles)
PRODUCT_DISPLAY_NAMES = {
    'Smartphone1': 'Arty Fish Phone',
    'Smartphone2': 'ZanaMan Phone',
    'Smartwatch1': 'ZanaMan Smartwatch',
    'Smartwatch2': 'Arty Fish Smartwatch',
    'Headphones01': 'Rhythm By Tre Headphones',
    'Earbuds01': 'Noize Boss Earbuds',
}

# Categories to exclude from Game Data Explorer (no products/demand data)
_EXCLUDED_CATEGORIES = {'Warehouse'}


def _display_product_name(internal_name: str, formatted_name: str) -> str:
    """Return the best display name for a product."""
    if internal_name in PRODUCT_DISPLAY_NAMES:
        return PRODUCT_DISPLAY_NAMES[internal_name]
    return formatted_name


def _neighbourhood_display(neigh_ids: list) -> str:
    """Convert neighbourhood IDs to display names."""
    if not neigh_ids:
        return 'All'
    names = [NEIGHBOURHOOD_NAMES.get(n, f'Zone {n}') for n in neigh_ids]
    return ', '.join(names)


# ============================================================================
# MAIN PAGE
# ============================================================================

def render_game_data_explorer():
    st.title("Game Data Explorer")
    st.markdown("Strategic analysis based on game data — no CSV upload needed.")
    st.divider()

    tab1, tab2, tab3 = st.tabs([
        "Demand Curves",
        "Product Margins",
        "Business Comparison",
    ])

    with tab1:
        _render_demand_curves()
    with tab2:
        _render_product_margins()
    with tab3:
        _render_business_comparison()


# ============================================================================
# TAB 1: DEMAND CURVES
# ============================================================================

_DAY_ORDER = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _expand_hourly_to_24(hourly_data: list) -> list:
    """Expand hourly ranges to a 24-element list (one per hour)."""
    result = [0.0] * 24
    for h in hourly_data:
        for hour in range(h['start'], min(h['end'], 24)):
            result[hour] = h['multiplier']
    return result


def _build_business_list() -> list:
    """Build list of businesses excluding Warehouse/Factory and Headquarter."""
    all_businesses = []
    for cat in get_business_categories():
        if cat in _EXCLUDED_CATEGORIES:
            continue
        for biz in get_businesses_for_category(cat):
            if biz == 'Headquarter':
                continue
            all_businesses.append(format_item_name(biz))
    all_businesses.sort()
    return all_businesses


def _render_demand_curves():
    st.subheader("Demand Curves")
    st.markdown(
        "Visualize when each business type has peak customer demand. "
        "The **demand multiplier** is a relative factor: "
        "**1.0 = peak demand (100%)**, 0.5 = half the peak, 0.0 = no customers."
    )

    all_businesses = _build_business_list()

    selected_business = st.selectbox(
        "Select Business",
        options=all_businesses,
        key="demand_business_select",
    )

    # --- Posizioni dipendenti del business (ruoli assumibili) ---
    if selected_business:
        roles = get_employee_roles_for_business(selected_business.replace(' ', ''))
        if roles:
            st.markdown(
                "**👥 Employee roles:** "
                + "  ".join(f"`{r}`" for r in roles)
            )

    # --- HEATMAP for selected business ---
    if selected_business:
        internal = selected_business.replace(' ', '')
        mults = get_demand_multipliers(internal)
        if mults:
            # Build 7x24 matrix: daily x hourly combined
            hourly_24 = _expand_hourly_to_24(mults['hourly'])
            matrix = np.zeros((7, 24))
            for d in mults['daily']:
                day_idx = d['day'] - 1
                for hour in range(24):
                    matrix[day_idx][hour] = round(d['multiplier'] * hourly_24[hour], 3)

            fig_heat = px.imshow(
                matrix,
                x=[f"{h:02d}:00" for h in range(24)],
                y=_DAY_ORDER,
                color_continuous_scale='YlOrRd',
                aspect='auto',
                title=f"Demand Heatmap — {selected_business}",
                labels={'color': 'Demand (0-1)'},
                zmin=0,
                zmax=1,
            )
            fig_heat.update_layout(
                xaxis_title="Hour",
                yaxis_title="Day",
                height=350,
            )
            st.plotly_chart(fig_heat, use_container_width=True)

            # Optimal hours insight
            threshold = 0.5
            avg_hourly = [sum(matrix[d][h] for d in range(7)) / 7 for h in range(24)]
            good_hours = [h for h, v in enumerate(avg_hourly) if v >= threshold]
            if good_hours:
                st.info(
                    f"**Suggested opening hours:** {good_hours[0]:02d}:00 — "
                    f"{good_hours[-1] + 1:02d}:00 "
                    f"(hours where avg demand >= 50% of peak)"
                )

            # Daily and hourly bar charts
            col_d, col_h = st.columns(2)
            with col_d:
                daily_df = pd.DataFrame(mults['daily'])
                fig_daily = px.bar(
                    daily_df,
                    x='name',
                    y='multiplier',
                    title=f"Daily Demand — {selected_business}",
                    color='multiplier',
                    color_continuous_scale='YlOrRd',
                    range_color=[0, 1],
                )
                fig_daily.update_layout(
                    xaxis_title="Day",
                    yaxis_title="Demand (0 = no customers, 1 = peak)",
                    yaxis_range=[0, 1.1],
                    height=300,
                    showlegend=False,
                )
                st.plotly_chart(fig_daily, use_container_width=True)

            with col_h:
                hourly_df = pd.DataFrame({
                    'hour': [f"{h:02d}:00" for h in range(24)],
                    'multiplier': hourly_24,
                })
                fig_hourly = px.bar(
                    hourly_df,
                    x='hour',
                    y='multiplier',
                    title=f"Hourly Demand — {selected_business}",
                    color='multiplier',
                    color_continuous_scale='YlOrRd',
                    range_color=[0, 1],
                )
                fig_hourly.update_layout(
                    xaxis_title="Hour",
                    yaxis_title="Demand (0 = no customers, 1 = peak)",
                    yaxis_range=[0, 1.1],
                    height=300,
                    showlegend=False,
                )
                st.plotly_chart(fig_hourly, use_container_width=True)

    # --- COMPARISON OVERLAY ---
    st.divider()
    st.subheader("Hourly Demand Comparison")
    compare_businesses = st.multiselect(
        "Select businesses to compare",
        options=all_businesses,
        default=[all_businesses[0]] if all_businesses else [],
        max_selections=5,
        key="demand_compare_select",
    )

    if compare_businesses:
        fig_cmp = go.Figure()
        for biz_name in compare_businesses:
            internal = biz_name.replace(' ', '')
            mults = get_demand_multipliers(internal)
            if mults:
                hourly_24 = _expand_hourly_to_24(mults['hourly'])
                fig_cmp.add_trace(go.Scatter(
                    x=list(range(24)),
                    y=hourly_24,
                    mode='lines+markers',
                    name=biz_name,
                    line=dict(width=2),
                    marker=dict(size=5),
                ))

        fig_cmp.update_layout(
            title="Hourly Demand Overlay",
            xaxis_title="Hour",
            yaxis_title="Demand (0 = no customers, 1 = peak)",
            yaxis_range=[0, 1.1],
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(24)),
                ticktext=[f"{h:02d}" for h in range(24)],
            ),
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_cmp, use_container_width=True)


# ============================================================================
# TAB 2: PRODUCT MARGINS
# ============================================================================

def _render_product_margins():
    st.subheader("Product Margins")
    st.markdown(
        "Compare wholesale cost vs market price across all products. "
        "**Market Price** is the default selling price set by the game — "
        "it is the same for each product regardless of which business sells it."
    )

    products = get_all_products_with_margins()

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        categories = ['All'] + [c for c in get_business_categories() if c not in _EXCLUDED_CATEGORIES]
        cat_filter = st.selectbox("Category", categories, key="margin_cat")
    with col2:
        sort_by = st.selectbox("Sort by", [
            "Margin ($)", "Margin (%)", "Market Price", "Wholesale Price"
        ], key="margin_sort")
    with col3:
        show_impact = st.checkbox("Show Impact", value=True, key="margin_impact")

    # Build business list for selected category
    if cat_filter != 'All':
        biz_in_cat = set(
            format_item_name(b) for b in get_businesses_for_category(cat_filter)
        )
    else:
        biz_in_cat = None

    # Filter products
    filtered = []
    for p in products:
        if biz_in_cat is not None:
            if not any(b['business'] in biz_in_cat for b in p['businesses']):
                continue
        filtered.append(p)

    if not filtered:
        st.warning("No products found for this filter.")
        return

    # Build DataFrame
    rows = []
    for p in filtered:
        display_name = _display_product_name(p['internal_name'], p['name'])
        biz_names = ', '.join(b['business'] for b in p['businesses'])
        avg_impact = sum(b['impact'] for b in p['businesses']) / len(p['businesses'])
        rows.append({
            'Product': display_name,
            'Wholesale': p['wholesale'],
            'Market Price': p['market'],
            'Margin ($)': p['margin'],
            'Margin (%)': p['margin_pct'],
            'Sales Ratio': p['sales_ratio'],
            'Avg Impact': round(avg_impact, 2),
            'Sold By': biz_names,
            '# Shops': p['n_businesses'],
        })

    df = pd.DataFrame(rows)

    # Sort
    sort_col_map = {
        "Margin ($)": "Margin ($)",
        "Margin (%)": "Margin (%)",
        "Market Price": "Market Price",
        "Wholesale Price": "Wholesale",
    }
    df = df.sort_values(sort_col_map[sort_by], ascending=False)

    # Display columns
    display_cols = ['Product', 'Wholesale', 'Market Price', 'Margin ($)', 'Margin (%)']
    if show_impact:
        display_cols += ['Avg Impact', 'Sales Ratio']
    display_cols += ['Sold By']

    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Products", len(df))
    m2.metric("Avg Margin ($)", f"${df['Margin ($)'].mean():,.2f}")
    m3.metric("Avg Margin (%)", f"{df['Margin (%)'].mean():,.1f}%")

    # Table
    st.dataframe(
        df[display_cols].style.format({
            'Wholesale': '${:,.2f}',
            'Market Price': '${:,.2f}',
            'Margin ($)': '${:,.2f}',
            'Margin (%)': '{:.1f}%',
            'Avg Impact': '{:.2f}',
            'Sales Ratio': '{:.0%}',
        }),
        use_container_width=True,
        height=400,
        hide_index=True,
    )

    # Bar chart — adapts to sort mode
    st.divider()
    top_n = min(20, len(df))

    if sort_by == "Margin (%)":
        # When sorted by %, show % bars
        fig_margin = px.bar(
            df.head(top_n),
            x='Product',
            y='Margin (%)',
            color='Margin ($)',
            color_continuous_scale='Greens',
            title=f"Top {top_n} Products by Margin (%)",
        )
        fig_margin.update_layout(
            xaxis_title="",
            yaxis_title="Margin (%)",
            height=400,
            xaxis_tickangle=-45,
        )
    else:
        # Default: show $ bars
        fig_margin = px.bar(
            df.head(top_n),
            x='Product',
            y='Margin ($)',
            color='Margin (%)',
            color_continuous_scale='Greens',
            title=f"Top {top_n} Products by Margin ($)",
        )
        fig_margin.update_layout(
            xaxis_title="",
            yaxis_title="Margin ($)",
            height=400,
            xaxis_tickangle=-45,
        )
    st.plotly_chart(fig_margin, use_container_width=True)

    # Scatter: margin vs sales ratio
    if show_impact:
        fig_scatter = px.scatter(
            df,
            x='Margin ($)',
            y='Sales Ratio',
            size='Avg Impact',
            color='# Shops',
            hover_name='Product',
            title="Margin vs Sales Ratio",
            color_continuous_scale='Viridis',
            labels={
                '# Shops': 'Shops selling it',
                'Avg Impact': 'Demand Impact',
                'Sales Ratio': 'Purchase Rate',
            },
        )
        fig_scatter.update_layout(
            height=400,
            coloraxis_colorbar_title_text="# Business types<br>selling it",
        )
        st.caption(
            "📐 **Size** = Demand Impact · "
            "🎨 **Color** = In how many shop types this product is sold · "
            "📈 **Purchase Rate** = % of customers who buy it"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)


# ============================================================================
# TAB 3: BUSINESS COMPARISON
# ============================================================================

def _render_business_comparison():
    st.subheader("Business Comparison")
    st.markdown("Compare all player-creatable businesses side by side.")

    data = get_business_comparison_data()

    # Filter out Warehouse/Factory
    data = [d for d in data if d['category'] not in _EXCLUDED_CATEGORIES]

    # Table
    rows = []
    for d in data:
        rows.append({
            'Business': d['name'],
            'Category': d['category'],
            'Products': d['n_products'],
            'Avg Margin ($)': d['avg_margin'],
            'Furniture': d['n_furniture'],
            'Roles': d['n_roles'],
            'Skills': ', '.join(d['roles']),
            'Avg Daily Demand': d['avg_daily_demand'],
            'Neighbourhood': _neighbourhood_display(d['neighbourhood_limits']),
        })

    df = pd.DataFrame(rows)

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        cat_filter = st.selectbox(
            "Filter by Category",
            ['All'] + sorted(df['Category'].unique().tolist()),
            key="cmp_cat",
        )
    with col2:
        sort_by = st.selectbox(
            "Sort by",
            ['Business', 'Avg Margin ($)', 'Products', 'Avg Daily Demand'],
            key="cmp_sort",
        )

    if cat_filter != 'All':
        df = df[df['Category'] == cat_filter]

    asc = sort_by == 'Business'
    df = df.sort_values(sort_by, ascending=asc)

    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Businesses", len(df))
    m2.metric("Avg Products/Business", f"{df['Products'].mean():.1f}")
    m3.metric("Avg Margin ($)", f"${df['Avg Margin ($)'].mean():,.2f}")

    st.dataframe(
        df.style.format({
            'Avg Margin ($)': '${:,.2f}',
            'Avg Daily Demand': '{:.2f}',
        }),
        use_container_width=True,
        height=400,
        hide_index=True,
    )

    st.caption(
        "**Avg Daily Demand**: average demand multiplier across all 7 days "
        "(1.0 = full demand every day, lower = some slow days like weekends). "
        "**Neighbourhood**: zones where this business can operate ('All' = no restrictions)."
    )

    # --- Comparison Chart ---
    st.divider()
    st.subheader("Compare Businesses")

    compare_options = sorted(df['Business'].tolist())
    selected = st.multiselect(
        "Select businesses to compare (min 2)",
        compare_options,
        default=compare_options[:3] if len(compare_options) >= 3 else compare_options,
        max_selections=5,
        key="cmp_select",
    )

    if len(selected) >= 2:
        cmp_df = df[df['Business'].isin(selected)].copy()

        # Radar chart with actual values as hover text
        metrics = ['Products', 'Avg Margin ($)', 'Furniture', 'Roles', 'Avg Daily Demand']
        display_labels = ['Products', 'Avg Margin', 'Furniture', 'Staff Roles', 'Daily Demand']

        # Normalize to 0-1 for radar shape, keep actual values for hover
        norm_data = {}
        actual_data = {}
        for m in metrics:
            col_max = df[m].max()
            col_min = df[m].min()
            rng = col_max - col_min if col_max != col_min else 1
            norm_data[m] = [(v - col_min) / rng for v in cmp_df[m]]
            actual_data[m] = list(cmp_df[m])

        # Plotly default color sequence for consistent trace/hover colors
        _RADAR_COLORS = [
            'rgba(99,110,250,{a})',   # blue
            'rgba(239,85,59,{a})',    # red
            'rgba(0,204,150,{a})',    # green
            'rgba(171,99,250,{a})',   # purple
            'rgba(255,161,90,{a})',   # orange
        ]

        fig_radar = go.Figure()
        for i, (_, row) in enumerate(cmp_df.iterrows()):
            values = [norm_data[m][i] for m in metrics]
            values.append(values[0])  # close polygon

            # Build hover text with actual values
            hover_texts = []
            for j, m in enumerate(metrics):
                actual = actual_data[m][i]
                if m == 'Avg Margin ($)':
                    hover_texts.append(f"${actual:,.2f}")
                elif m == 'Avg Daily Demand':
                    hover_texts.append(f"{actual:.2f}")
                else:
                    hover_texts.append(f"{int(actual)}")
            hover_texts.append(hover_texts[0])  # close

            color_tpl = _RADAR_COLORS[i % len(_RADAR_COLORS)]
            fill_color = color_tpl.format(a='0.25')
            line_color = color_tpl.format(a='1')
            hover_bg = color_tpl.format(a='0.85')

            fig_radar.add_trace(go.Scatterpolar(
                r=values,
                theta=display_labels + [display_labels[0]],
                fill='toself',
                fillcolor=fill_color,
                name=row['Business'],
                line=dict(color=line_color, width=2),
                text=hover_texts,
                hovertemplate='%{theta}: %{text}<extra>%{fullData.name}</extra>',
                hoverlabel=dict(
                    bgcolor='rgba(30,30,30,0.92)',
                    font_color=line_color,
                    font_size=13,
                    bordercolor=line_color,
                ),
            ))

        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=False, range=[0, 1.05]),
            ),
            title="Business Comparison (hover for actual values)",
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig_radar, use_container_width=True)
        st.caption(
            "Chart shows normalized values (0-1 scale) to compare metrics with "
            "different units on the same axes. **Hover** over each point to see "
            "the actual value."
        )

        # Detail: products per business
        with st.expander("Product Details for Selected Businesses"):
            for biz_name in selected:
                internal = biz_name.replace(' ', '')
                products = get_products_for_business(internal)
                if products:
                    st.markdown(f"**{biz_name}**")
                    prod_rows = []
                    for p in products:
                        prod_rows.append({
                            'Product': _display_product_name(p['internal_name'], p['name']),
                            'Wholesale': p['wholesale'],
                            'Market': p['market'],
                            'Margin': p['market'] - p['wholesale'],
                            'Impact': p['impact'],
                        })
                    prod_df = pd.DataFrame(prod_rows)
                    st.dataframe(
                        prod_df.style.format({
                            'Wholesale': '${:,.2f}',
                            'Market': '${:,.2f}',
                            'Impact': '{:.2f}',
                            'Margin': '${:,.2f}',
                        }),
                        hide_index=True,
                        use_container_width=True,
                    )
