"""
Big Ambitions Business Analyzer
Main Streamlit Application
"""

import streamlit as st
import pandas as pd
from core.data_cleaner import clean_big_ambitions_csv
from analysis.revenue_analyzer import extract_business_from_revenue
from analysis.profit_loss import calculate_profit_loss


# Page Configuration
st.set_page_config(
    page_title="Big Ambitions Analyzer",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Header
st.title("🎮 Big Ambitions Business Analyzer")
st.markdown("### Professional analytics for your Big Ambitions empire")

st.divider()

# File Upload
uploaded_file = st.file_uploader(
    "📂 Upload your Big Ambitions CSV/XLSM file",
    type=['csv', 'xlsm'],
    help="Export transactions from Big Ambitions and upload here"
)

if uploaded_file is not None:
    with st.spinner('🔄 Cleaning and processing data...'):
        # Read file content
        file_content = uploaded_file.getvalue()
        
        # Clean with your cleaner!
        df, error = clean_big_ambitions_csv(file_content)
    
    if error:
        st.error(f"❌ Error cleaning data: {error}")
        st.info("💡 Make sure you uploaded a valid Big Ambitions export file")
    else:
        st.success(f"✅ Successfully processed {len(df):,} transactions!")
        
        
        
        
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
                
                import plotly.express as px
                
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
    
        
        else:
            st.info("💡 No revenue data found in this file")
            st.divider()
                # In app.py, dopo il cleaning

        
        # Tabs for different views
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

else:
    # Welcome message when no file uploaded
    st.info("👆 **Upload a CSV file to get started!**")
    
    st.subheader("📖 How to use:")
    st.markdown("""
    1. **Export** your transaction data from Big Ambitions
    2. **Upload** the CSV/XLSM file using the uploader above
    3. **Analyze** your business performance with automated insights
    
    **Features coming soon:**
    - 📊 Revenue analysis per business
    - 💰 Profit & Loss statements
    - 📈 Trend analysis and forecasting
    - 🎯 Business optimization recommendations
    """)

# Sidebar
with st.sidebar:
    st.header("📊 Big Ambitions Analyzer")
    
    st.markdown("""
    ### Status
    🟢 **Data Cleaner**: Ready  
    🟡 **Analytics**: In Development  
    🔴 **Forecasting**: Coming Soon
    
    ### About
    This tool helps you analyze your Big Ambitions
    business data with professional insights.
    
    **Version:** 1.0.0  
    **Updated:** 2025
    """)
    
    st.divider()
    
    st.markdown("""
    ### Links
    - [GitHub](https://github.com/raytp29-hub/big-ambitions-analyzer1.0)
    - [Report Bug](https://github.com/raytp29-hub/big-ambitions-analyzer1.0/issues)
    """)

# Footer
st.divider()
st.caption("Made with ❤️ using Streamlit | Big Ambitions Analyzer v1.0")