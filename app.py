"""
Big Ambitions Business Analyzer
Main Streamlit Application
"""

import streamlit as st
import pandas as pd
from analysis.temporal_analyzer import TemporalAnalyzer
from core.data_cleaner import clean_big_ambitions_csv
from analysis.revenue_analyzer import extract_business_from_revenue
from analysis.profit_loss import calculate_profit_loss
import plotly.graph_objects as go
import plotly.express as px

# Import Schedule Optimizer page
from visualization.schedule_page import render_schedule_optimizer_page
from analysis.forecasting import ForecastingAnalyzer

from core.session_state_manager import init_global_session_state



init_global_session_state()

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Big Ambitions Analyzer",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# SIDEBAR - NAVIGATION
# ============================================================================

with st.sidebar:
    st.header("🎮 Big Ambitions Analyzer")
    st.markdown("---")
    
    # PAGE SELECTOR
    page = st.selectbox(
        "📍 Navigation",
        ["📊 Main Dashboard", "🗓️ Schedule Optimizer", "📈 Forecasting"],
        help="Choose which tool to use"
    )
    


    st.markdown("### 📂 Data Source")
        
        # Check if data exists in session state
    if "df" not in st.session_state:
            st.session_state.df = None
            
        # Sidebar Uploader (Global)
    uploaded_file = st.file_uploader(
            "Upload CSV/XLSM",
            type=['csv', 'xlsm'],
            help="Upload once, use everywhere!",
            key="main_uploader"
        )
        
    if uploaded_file is not None:
            # Only reload if it's a new file or we don't have data yet
            # (Streamlit re-runs script on interaction, so we need to be careful not to re-process unnecessarily if we cached it)
            # Actually with st.cache_data it is fast, but we want to store in session_state.
            
            file_content = uploaded_file.getvalue()
            df, error = clean_big_ambitions_csv(file_content)
            
            if error:
                st.error(f"Error: {error}")
            else:
                st.session_state.df = df
                st.success(f"Loaded {len(df)} rows!")
        
        # Show current data status
    if st.session_state.df is not None:
            st.caption(f"✅ Active Data: {len(st.session_state.df)} txns")
            if st.button("🗑️ Clear Data"):
                st.session_state.df = None
                st.rerun()
    st.markdown("---")
    
    # Status info
    st.markdown("""
    ### Status
    🟢 **Data Cleaner**: Ready  
    🟢 **Analytics**: Ready
    🟢 **Schedule Optimizer**: Ready ✨  
    � **Forecasting**: Ready 🚀
    
    ### About
    This tool helps you analyze your Big Ambitions
    business data with professional insights.
    
    **Version:** 2.0.0  
    **Updated:** December 2025
    """)
    

    st.divider()
    
    
             
    st.markdown("""
    ### Links
    - [GitHub](https://github.com/raytp29-hub/big-ambitions-analyzer1.0)
    - [Report Bug](https://github.com/raytp29-hub/big-ambitions-analyzer1.0/issues)
    """)

# ============================================================================
# PAGE ROUTING
# ============================================================================

if page == "🗓️ Schedule Optimizer":
    # ========================================================================
    # SCHEDULE OPTIMIZER PAGE
    # ========================================================================
    render_schedule_optimizer_page()

elif page == "📈 Forecasting":
    # ========================================================================
    # FORECASTING PAGE
    # ========================================================================
    st.title("📈 Business Forecasting")
    st.markdown("### Predict future trends using linear regression")
    
    st.divider()
    
    st.divider()
    
    if st.session_state.df is None:
        st.info("👈 Please upload your data in the sidebar to start forecasting!")
    else:
        # Use data from session state
        df = st.session_state.df
        
        # FORECASTING UI
        analyzer = ForecastingAnalyzer(df)
            
            # extract business names for filter
        business_names, _, _ = extract_business_from_revenue(df)
        business_options = ["All Businesses"] + sorted(business_names)
            
        col1, col2, col3 = st.columns(3)
            
        with col1:
                selected_business = st.selectbox("Select Business", business_options)
            
        with col2:
                selected_metric = st.selectbox("Select Metric", ["profit", "revenue", "wages"])
                
        with col3:
            days_ahead = st.slider("Forecast Horizon (Days)", 7, 30, 14)
        forecast_method = st.radio("Forecast Method", ["Linear Regression", "Moving Average"], horizontal=True)
        method_key = "linear" if forecast_method == "Linear Regression" else "moving_average"
   
    # Run Forecast
        result = analyzer.forecast(selected_business, selected_metric, days_ahead, granularity="daily", method=method_key)
        
        if "error" in result:
            st.warning(result["error"])
        else:
            st.divider()
            
            # Metrics
            trend = result['trend']
            slope = trend['slope']
            r2 = trend['r_squared']
            
            # Calculate projected growth
            last_hist_val = result['historical']['y'].iloc[-1]
            last_forecast_val = result['forecast']['y'].iloc[-1]
            growth_abs = last_forecast_val - last_hist_val
            growth_pct = (growth_abs / last_hist_val * 100) if last_hist_val != 0 else 0
            
            m1, m2, m3 = st.columns(3)
            if method_key == "linear":
                m1.metric("Daily Trend (Slope)", f"${slope:,.0f}/day")
                m2.metric("R²", f"{r2:.2f}")
                m3.metric(f"Growth ({days_ahead}d)", f"${growth_abs:,.0f}", f"{growth_pct:+.1f}%")
            else:
                m1.metric(f"Moving Avg ({result.get('window', 7)}d)", f"${result['last_avg']:,.0f}")
                m2.metric("Method", "SMA")
                m3.metric(f"Projected ({days_ahead}d)", f"${result['last_avg']:,.0f}")
            # === TABS ===
            tab_forecast, tab_marketing = st.tabs(["📉 Forecast Visualization", "📢 Marketing Impact"])
            
            with tab_forecast:
                hist_df = result['historical'].copy()
                hist_df['Type'] = 'Historical'
                
                fore_df = result['forecast'].copy()
                fore_df['Type'] = 'Forecast'
                
                chart_df = pd.concat([hist_df, fore_df])
                
                fig = px.line(
                    chart_df,
                    x='x', 
                    y='y', 
                    color='Type',
                    title=f"{selected_metric.title()} Forecast - {selected_business}",
                    line_dash='Type' 
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                st.info(
                    "**How it works** "
                    "We use **Linear Regression** to calculate the trend of your past performance. "
                    "The 'slope' tells us how much your metric increases (or decreases) on average per day. "
                    "We then project this trend into the future."
                )

        with tab_marketing:
                from analysis.marketing_analyzer import MarketingAnalyzer
                mkt_analyzer = MarketingAnalyzer(df)
                
                mkt_business = st.selectbox("Analyze Business", business_options, key="mkt_biz_select")
                
                dim_result = mkt_analyzer.difference_in_means(mkt_business)
                
                if "error" in dim_result:
                    st.warning(dim_result["error"])
                else:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Avg Revenue (Marketing ON)", f"${dim_result['mean_revenue_on']:,.0f}")
                    m2.metric("Avg Revenue (Marketing OFF)", f"${dim_result['mean_revenue_off']:,.0f}")
                    m3.metric("Delta", f"${dim_result['delta']:,.0f}")
                    m4.metric("Delta %", f"{dim_result['delta_pct']:+.1f}%")           
                    
               
                    
                
else:
    # ========================================================================
    # MAIN DASHBOARD PAGE (your existing code)
    # ========================================================================
    
    # Header
    st.title("🎮 Big Ambitions Business Analyzer")
    st.markdown("### Professional analytics for your Big Ambitions empire")
    
    st.divider()
    
    # File Upload
    st.divider()
    
    if st.session_state.df is None:
        # Welcome message when no file uploaded
        st.info("👆 **Upload a CSV file to get started!**")
        
        st.subheader("📖 How to use:")
        st.markdown("""
        1. **Export** your transaction data from Big Ambitions
        2. **Upload** the CSV/XLSM file using the uploader above
        3. **Analyze** your business performance with automated insights
        
        **Features available:**
        - 📊 Revenue analysis per business
        - 💰 Profit & Loss statements
        - 📈 Trend analysis and forecasting
        - 🗓️ **NEW:** Employee Schedule Optimizer
        """)
        
        st.divider()
        
        st.subheader("✨ Try the Schedule Optimizer!")
        st.info("💡 No data upload needed! Use the sidebar to navigate to **Schedule Optimizer** and start optimizing your workforce.")
    else:
        df = st.session_state.df
        st.success(f"✅ Analyzing {len(df):,} transactions!")
        
        analyzer = TemporalAnalyzer(df)
            
        # Main Metrics
        st.subheader("📊 Overview")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="📋 Total Transactions",
                value=f"{len(df):,}"
            )
        
        with col2:
            st.metric(
                label="📅 Days Range",
                value=f"{df['day'].min()} - {df['day'].max()}"
            )
        
        with col3:
            st.metric(
                label="📝 Transaction Types",
                value=df['type'].nunique()
            )
        
        with col4:
            total_balance = df['balance'].iloc[-1] if len(df) > 0 else 0
            st.metric(
                label="💰 Final Balance",
                value=f"${total_balance:,.0f}"
            )
        
        st.divider()
            
            # extract revenue from data
        business_name, revenue_per_business, revenue_df = extract_business_from_revenue(df)
            
        if len(business_name) > 0:
                st.subheader("Revenue Analysis")
                
                col1, col2 = st.columns([1,2])
                
                with col1:
                    st.write("Total Revenue per Business:")
                    
                    # create dataFrame for visualization
                    revenue_display = pd.DataFrame({
                        "Business": revenue_per_business.index,
                        "Total Revenue": revenue_per_business.values
                    })
                    
                    revenue_display = revenue_display.sort_values("Total Revenue", ascending=False)
                    
                    # show dataframe
                    st.dataframe(
                        revenue_display.style.format({"Total Revenue": "${:,.2f}"}),
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Top performer
                    top_business = revenue_display.iloc[0]
                    st.success(f"🏆 Top Performer: **{top_business['Business']}** (${top_business['Total Revenue']:,.2f})")
                    
                with col2:
                    st.write("Revenue Distribution:")
                    
                    fig = px.bar(
                        revenue_display,
                        x="Business",
                        y="Total Revenue",
                        title="Revenue by Business",
                        color="Total Revenue",
                        color_continuous_scale="Viridis"
                    )
                    
                    fig.update_layout(
                        showlegend=False,
                        height=400,
                        xaxis_title="",
                        yaxis_title="Revenue ($)"
                    )
                    
                    fig.update_yaxes(tickformat='$,.0f')
                    st.plotly_chart(fig, use_container_width=True)
                    
                st.divider()
                
                # === P&L ANALYSIS ===
                st.subheader("💰 Profit & Loss Analysis")
                
                with st.spinner('📊 Calculating P&L for each business...'):
                    try:
                        pl_df = calculate_profit_loss(df)
                        
                        # Ordina per profit (dal più alto al più basso)
                        pl_df = pl_df.sort_values('profit', ascending=False)
                        
                        # Mostra tabella P&L
                        st.write("**Complete P&L Statement:**")
                        st.dataframe(
                            pl_df.style.format({
                                'revenue': '${:,.2f}',
                                'shared_revenue_based': '${:,.2f}',
                                'shared_equal_split': '${:,.2f}',
                                'wages': '${:,.2f}',
                                'marketing': '${:,.2f}',
                                'health_insurance': '${:,.2f}',
                                'hr_training': '${:,.2f}',
                                'total_direct_costs': '${:,.2f}',
                                'total_shared_costs': '${:,.2f}',
                                'total_costs': '${:,.2f}',
                                'profit': '${:,.2f}',
                                'margin_pct': '{:.1f}%'
                            }),
                            use_container_width=True,
                            hide_index=True
                        )
                        
                        # Highlight best performer
                        best_business = pl_df.iloc[0]
                        st.success(f"🏆 Most Profitable: **{best_business['business']}** - Profit: ${best_business['profit']:,.2f} ({best_business['margin_pct']:.1f}% margin)")
                        
                    except Exception as e:
                        st.error(f"❌ Error calculating P&L: {str(e)}")
                        st.info("💡 This might happen if there are data inconsistencies. Check your data!")
                    
                    # === TEMPORAL ANALYSIS ===
                    st.header("📈 Temporal Analysis")
                    
                    
                    # Selector granularity
                    granularity = st.selectbox("Aggregation", [
                        "daily", "weekly", "monthly", "auto"
                    ])
                    
                    temporal_df = analyzer.aggregate_by_period(granularity)
                    
                    fig = px.line(
                        temporal_df,
                        x="period",
                        y="profit",
                        color="business",
                        title="Profit Trend Over Time"
                    )
                    
                    labels_dict = temporal_df.groupby('period')['period_label'].first().to_dict()
                    
                    fig.update_xaxes(
                        tickvals = list(labels_dict.keys()),
                        ticktext = list(labels_dict.values())
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                
                # === CHARTS SECTION ===
                st.subheader("📊 Detailed Charts")
                
                fig1 = px.bar(
                    pl_df,
                    x="business",
                    y="profit", 
                    title="Profit by Business",
                    color="profit",
                    color_continuous_scale=["red", "yellow", "green"]   
                )
                
                fig2 = px.bar(
                    pl_df,
                    x="business",
                    y="margin_pct",
                    title="Profit Margin %"
                )
                
                fig3 = px.bar(
                    pl_df,
                    x="business",
                    y=["wages", "shared_revenue_based", "marketing", "health_insurance", "hr_training"],
                    barmode="stack",
                    title="Cost Breakdown",
                    labels={"value": "Amount ($)", "variable": "Category"},
                    color_discrete_map={
                        "wages": "#e7f316",
                        "shared_revenue_based": "#bc2210",
                        "marketing": "#225ae6",
                        "health_insurance": "#0cc05a",
                        "hr_training": "#14bcc2"
                    }
                )
                
                fig3.update_yaxes(tickformat='$,.0f')
                fig3.update_layout(height=500)
                
                # === WATERFALL CHART ===
                fig5 = go.Figure()
                
                for i, business_row in pl_df.iterrows():
                    x_list = ["Revenue", "Direct Costs", "Shared Costs", "Profit"]
                    y_list = [
                        business_row["revenue"],
                        -business_row["total_direct_costs"],
                        -business_row["total_shared_costs"],
                        business_row["profit"]
                    ]
                    
                    measure = ["relative", "relative", "relative", "total"]
                    
                    fig5.add_trace(go.Waterfall(
                        x=x_list,
                        y=y_list,
                        measure=measure,
                        text=y_list,
                        textposition="outside",
                        texttemplate='$%{y:,.0f}',
                        visible=(i==0),
                        name=business_row["business"],
                        increasing={"marker": {"color": "#2ecc71"}},    
                        decreasing={"marker": {"color": "#e74c3c"}},      
                        totals={"marker": {"color": "#3498db"}}
                    ))
                
                buttons = []
                
                for i in range(len(pl_df)):
                    business_name = pl_df.iloc[i]["business"]
                    
                    visible = [False] * len(pl_df)
                    visible[i] = True
                    
                    buttons.append(dict(
                        label=business_name,
                        method="update",
                        args=[{"visible": visible},
                            {"title.text": f"<b>P&L Waterfall - {business_name}</b>"}
                        ]
                    ))
                
                fig5.update_layout(
                    title=f"P&L Waterfall - {pl_df.iloc[0]['business']}",
                    height=500,
                    updatemenus=[dict(
                        buttons=buttons,
                        direction="down",
                        showactive=True,
                        x=0.5,
                        y=1.2,
                        xanchor="left",
                        yanchor="top"
                    )]
                )
                
                # Display charts in columns
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Profit")
                    st.plotly_chart(fig1, use_container_width=True)
                    st.plotly_chart(fig3, use_container_width=True)
                    
                with col2:
                    st.subheader("Margin %")
                    st.plotly_chart(fig2, use_container_width=True)
                    st.plotly_chart(fig5, use_container_width=True)
                
            
        else:
            st.info("💡 No revenue data found in this file")
        
        st.divider()
        
        # === WAGE COST ANALYSIS ===
        st.subheader("💼 Wage Cost Analysis")
        
        # Controlli in 2 colonne
        col1, col2 = st.columns(2)

        with col1:
            wage_granularity = st.selectbox(
                "Time Period",
                ["daily", "weekly", "monthly"],
                index=1,  # Default to weekly
                key="wage_granularity"
            )

        with col2:
            # Estrai lista business dai dati
            business_list = sorted(df[df['type'] == 'Revenue']['description'].apply(
                lambda x: x.replace(' Revenue', '').strip()
            ).unique())
            
            # Aggiungi opzione "All"
            business_options = ["All Businesses"] + business_list
            
            selected_business = st.selectbox(
                "Business",
                options=business_options,
                key="wage_business_filter"
            )

        # Usa TemporalAnalyzer per aggregare
        wage_temporal_df = analyzer.aggregate_by_period(wage_granularity)
        
        # Filtra per business se selezionato
        if selected_business != "All Businesses":
            wage_temporal_df = wage_temporal_df[wage_temporal_df['business'] == selected_business]

        # Aggrega wages per periodo
        wage_by_period = wage_temporal_df.groupby('period_label').agg({
            'wages': 'sum',
            'period': 'first'
        }).reset_index()

        # Ordina per periodo
        wage_by_period = wage_by_period.sort_values('period')

        # === METRICHE CHIAVE ===
        if len(wage_by_period) > 0:
            col1, col2, col3 = st.columns(3)
            
            total_wages = wage_by_period['wages'].sum()
            avg_wages = wage_by_period['wages'].mean()
            last_period_wages = wage_by_period['wages'].iloc[-1]
            
            with col1:
                st.metric("Total Wage Costs", f"${total_wages:,.2f}")
            
            with col2:
                st.metric(f"Average {wage_granularity.title()}", f"${avg_wages:,.2f}")
            
            with col3:
                # Calcola variazione rispetto al periodo precedente
                if len(wage_by_period) >= 2:
                    prev_wages = wage_by_period['wages'].iloc[-2]
                    delta_wages = last_period_wages - prev_wages
                    delta_pct = (delta_wages / prev_wages * 100) if prev_wages > 0 else 0
                    st.metric(
                        "Last Period", 
                        f"${last_period_wages:,.2f}",
                        delta=f"{delta_pct:+.1f}%",
                        delta_color="inverse"
                    )
                else:
                    st.metric("Last Period", f"${last_period_wages:,.2f}")
            
            # === GRAFICO TREND ===
            fig_wages = px.line(
                wage_by_period,
                x='period_label',
                y='wages',
                title=f"Wage Costs Over Time - {selected_business} ({wage_granularity.title()})",
                markers=True
            )
            
            fig_wages.update_layout(
                xaxis_title="Period",
                yaxis_title="Wage Cost ($)",
                height=400
            )
            
            fig_wages.update_traces(
                line_color='#e74c3c',
                line_width=3,
                marker=dict(size=8)
            )
            
            st.plotly_chart(fig_wages, use_container_width=True)
            
            # === BREAKDOWN PER BUSINESS (solo se "All Businesses") ===
            if selected_business == "All Businesses":
                with st.expander("📊 Wage Breakdown by Business"):
                    wage_by_business = wage_temporal_df.groupby(['period_label', 'business']).agg({
                        'wages': 'sum',
                        'period': 'first'
                    }).reset_index()
                    
                    wage_by_business = wage_by_business.sort_values('period')
                    
                    fig_wages_business = px.bar(
                        wage_by_business,
                        x='period_label',
                        y='wages',
                        color='business',
                        title=f"Wage Costs by Business ({wage_granularity.title()})",
                        barmode='stack'
                    )
                    
                    fig_wages_business.update_layout(
                        xaxis_title="Period",
                        yaxis_title="Wage Cost ($)",
                        height=400
                    )
                    
                    st.plotly_chart(fig_wages_business, use_container_width=True)
                    
                    # Tabella dettagliata
                    st.markdown("**Detailed Breakdown:**")
                    pivot_wages = wage_by_business.pivot(
                        index='business',
                        columns='period_label',
                        values='wages'
                    ).fillna(0)
                    
                    # Aggiungi totale per riga
                    pivot_wages['Total'] = pivot_wages.sum(axis=1)
                    
                    # Ordina per totale decrescente
                    pivot_wages = pivot_wages.sort_values('Total', ascending=False)
                    
                    st.dataframe(
                        pivot_wages.style.format('${:,.2f}'),
                        use_container_width=True
                    )
            else:
                # Mostra dettagli per singolo business
                with st.expander(f"📋 Detailed Period Breakdown for {selected_business}"):
                    # Tabella con tutti i periodi
                    st.dataframe(
                        wage_by_period[['period_label', 'wages']].style.format({
                            'wages': '${:,.2f}'
                        }),
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Statistiche aggiuntive
                    st.markdown("**Statistics:**")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Min Period", f"${wage_by_period['wages'].min():,.2f}")
                    with col2:
                        st.metric("Max Period", f"${wage_by_period['wages'].max():,.2f}")
                    with col3:
                        std_wages = wage_by_period['wages'].std()
                        st.metric("Std Deviation", f"${std_wages:,.2f}")

        else:
            st.info(f"No wage data found for {selected_business}")

        st.divider()
                    
        # === TABS SECTION ===
        tab1, tab2, tab3 = st.tabs(["📋 Data Preview", "📊 Statistics", "🔍 Filters"])
        
        with tab1:
            st.subheader("Transaction Data")
            
            # Number of rows to display
            num_rows = st.slider("Number of rows to display:", 10, 100, 20)
            
            st.dataframe(
                df.head(num_rows),
                use_container_width=True,
                height=400
            )
            
            # Download button
            st.download_button(
                label="💾 Download Cleaned Data (CSV)",
                data=df.to_csv(index=False),
                file_name="big_ambitions_cleaned.csv",
                mime="text/csv"
            )
        
        with tab2:
            st.subheader("Data Statistics")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Numeric Columns Summary:**")
                st.dataframe(df.describe(), use_container_width=True)
            
            with col2:
                st.write("**Transaction Types:**")
                type_counts = df['type'].value_counts()
                st.dataframe(type_counts, use_container_width=True)
        
        with tab3:
            st.subheader("Filter Data")
            
            # Filter by transaction type
            selected_types = st.multiselect(
                "Select transaction types:",
                options=df['type'].unique(),
                default=df['type'].unique()
            )
            
            # Filter by day range
            min_day, max_day = int(df['day'].min()), int(df['day'].max())
            day_range = st.slider(
                "Select day range:",
                min_day, max_day,
                (min_day, max_day)
            )
            
            # Apply filters
            filtered_df = df[
                (df['type'].isin(selected_types)) &
                (df['day'] >= day_range[0]) &
                (df['day'] <= day_range[1])
            ]
            
            st.metric("Filtered Transactions", f"{len(filtered_df):,}")
            st.dataframe(filtered_df, use_container_width=True, height=300)



# Footer
st.divider()
st.caption("Made with ❤️ using Streamlit | Big Ambitions Analyzer v2.0 | Now with Schedule Optimizer! ✨")