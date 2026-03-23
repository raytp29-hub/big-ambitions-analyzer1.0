import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go


from analysis.health_check import NEIGHBOURHOOD_NAMES, compute_bep, compute_performance, rank_products, rank_zone
from analysis.schedule_constraints import get_available_buildings, get_available_categories, get_building_capacity, get_business_tupes_for_category
from core.game_data import get_demand_multipliers
from analysis.revenue_analyzer import extract_business_from_revenue



def render_health_check_page():
    st.title("Business Health Check")
    
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
        
    st.dataframe(pd.DataFrame(zone_rows))
    
    
    
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
        
        
        col5, col6, col7 = st.columns(3)
        with col5:
            st.metric("Setup Cost", f"${result.setup_cost:,.2f}")
        with col6:
            st.metric("Employees Needed", result.employees)
        with col7:
            st.metric("Break Even", f"{result.break_even:.0f} days")
            
    
        demand = get_demand_multipliers(internal_name)
        
        hourly_24 = [0.0] * 24
        for h in demand['hourly']:
            for hour in range(h['start'], min(h['end'], 24)):
                hourly_24[hour] = h['multiplier']

        matrix = np.zeros((7, 24))
        day_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for d in demand['daily']:
            day_idx = d['day'] - 1
            for hour in range(24):
                matrix[day_idx][hour] = round(d['multiplier'] * hourly_24[hour], 3)

        fig = px.imshow(matrix, x=[f"{h:02d}:00" for h in range(24)], y=day_order,
                        color_continuous_scale='YlOrRd', title="Demand Heatmap")
        st.plotly_chart(fig, use_container_width=True)
        
        
        
    # SECTION 4 THEO VS EFFECTIVE
    
    if st.session_state.df is not None:
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
                yaxis=dict(range=[0, max(perf.daily_data['revenue'].max(), perf.theo_revenue) * 1.1])
            )
            st.plotly_chart(fig, use_container_width=True)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Performance", f"{perf.performance_pct:0f}%")
            with col2:
                st.metric("Rating", perf.rating)
            with col3:
                st.metric("Avg Daily Revenue", f"${perf.actual_revenue:,.0f}")
            with col4:
                st.metric("Days Analyzed", perf.n_days)
                
                
                
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

            st.plotly_chart(fig_wages, use_container_width=True)
            
            
            col5, col6 = st.columns(2)
            wage_diff = perf.actual_wages - perf.theo_wages
            with col5:
                st.metric("Actual Daily Wages", f"${perf.actual_wages:,.0f}")
            with col6:
                st.metric("Theoretical Daily Wages", f"${perf.theo_wages:,.0f}", 
                        delta=f"${wage_diff:+,.0f}", delta_color="inverse")

                
    else:
        st.info("Upload your CSV in the sidebar to compare actual vs theoretical performance")