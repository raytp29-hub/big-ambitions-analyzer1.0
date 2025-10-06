"""
Big Ambitions Business Analyzer
Main Streamlit Application
"""

import streamlit as st
import pandas as pd
from core.data_cleaner import clean_big_ambitions_csv

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