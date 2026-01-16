"""
Centralized Session State Management
Prevents state reset on page navigation
"""
import streamlit as st

def init_global_session_state():
    """
    Initialize ALL session state keys used across the app.
    Call this ONCE in app.py before page routing.
    """
    # Schedule Optimizer State
    if 'business_setup' not in st.session_state:
        st.session_state.business_setup = None
    
    if 'selected_business_type' not in st.session_state:
        st.session_state.selected_business_type = None
    
    if 'selected_furniture' not in st.session_state:
        st.session_state.selected_furniture = []
    
    if 'total_furniture_cost' not in st.session_state:
        st.session_state.total_furniture_cost = 0
    
    if 'effective_capacity' not in st.session_state:
        st.session_state.effective_capacity = 0
    
    if 'max_simultaneous_employees' not in st.session_state:
        st.session_state.max_simultaneous_employees = 0
    
    if 'employees' not in st.session_state:
        st.session_state.employees = []
    
    if 'weekly_schedule' not in st.session_state:
        st.session_state.weekly_schedule = []
    
    if 'edit_employee_index' not in st.session_state:
        st.session_state.edit_employee_index = None
    
    if 'temp_demands' not in st.session_state:
        st.session_state.temp_demands = []
    
    if 'optimization_result' not in st.session_state:
        st.session_state.optimization_result = None