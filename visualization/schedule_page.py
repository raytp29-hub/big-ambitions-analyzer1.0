"""
Schedule Optimizer - Streamlit Page
UI for configuring business setup and employees
"""
import streamlit as st
import pandas as pd
from typing import List, Optional
from analysis.schedule_optimizer import optimize_schedule




# Import models and constraints
from analysis.schedule_models import Building, Employee, Demand, DailySchedule, BusinessSetup
from analysis.schedule_constraints import (
    BUSINESS_TYPES,
    calculate_workstation_capacity,
    get_available_buildings,
    get_available_categories,
    get_building_capacity,
    get_business_tupes_for_category,
    get_furniture_for_business,
    get_roles_for_business_type,
    INSURANCE_LEVELS,
    DEMAND_PRIORITIES,
    get_all_demands_by_category,
    DAYS_OF_WEEK,
    DEFAULT_START_HOUR,
    DEFAULT_END_HOUR,
    parse_price
)


# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

"""def init_session_state():
    #Initialize session state variables
    if 'business_setup' not in st.session_state:
        st.session_state.business_setup = None
    
    if 'employees' not in st.session_state:
        st.session_state.employees = []
    
    if 'weekly_schedule' not in st.session_state:
        st.session_state.weekly_schedule = []
    
    if 'edit_employee_index' not in st.session_state:
        st.session_state.edit_employee_index = None
    
    # ← AGGIUNGI QUESTA RIGA
    if 'temp_demands' not in st.session_state:
        st.session_state.temp_demands = []"""

# ============================================================================
# STEP 1: BUSINESS SETUP
# ============================================================================

def render_business_setup():
    """Step 1: Business setup with furniture selection"""
    st.header("📍 Step 1: Business Setup")
    
    # ================================================================
    # SECTION 1: Business Category Selection
    # ================================================================
    st.subheader("Business Category")
    
    categories = get_available_categories()
    business_category = st.selectbox(
        "Select Category",
        options=categories,
        key="business_category"
    )
    
    # ================================================================
    # SECTION 2: Business Type Selection
    # ================================================================
    st.subheader("Business Type")
    
    business_types = get_business_tupes_for_category(business_category)
    business_type = st.selectbox(
        "Select Business Type",
        options=business_types,
        key="business_type"
    )
    
    # ================================================================
    # SECTION 3: Building Size Selection
    # ================================================================
    st.subheader("Building Size")
    
    available_buildings = get_available_buildings(business_category)
    building_code = st.selectbox(
        "Select Building",
        options=available_buildings,
        format_func=lambda x: f"{x} - {get_building_capacity(business_category, x)} capacity limit",
        key="building_code"
    )
    
    building_capacity_limit = get_building_capacity(business_category, building_code)
    st.info(f"🏢 Building Max Capacity: {building_capacity_limit} customers/hour")
    
    # ================================================================
    # SECTION 4: Furniture Selection
    # ================================================================
    # SECTION 4: Furniture Selection
    # SECTION 4: Furniture Selection
    st.subheader("🪑 Furniture Selection")

    df_furniture = get_furniture_for_business(business_type)

    # Store selections with quantities
    selected_furniture = []
    
    h1, h2, h3, h4 = st.columns([3,1,1,1])
    
    with h1:
        st.markdown("Furniture")
    with h2:
        st.markdown("Costumer Capacity")
    with h3:
        st.markdown("Quantity")
    with h4:
        st.markdown("Total Quantity")

    for idx, row in df_furniture.iterrows():
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        
        with col1:
            is_selected = st.checkbox(
                row['furniture_name'],
                key=f"furniture_check_{idx}"
            )
        
        with col2:
            st.caption(f"📊 {row['customer_capacity']}")
        
        with col3:
            # Quantity selector (only active if selected)
            qty = st.number_input(
                "Qty",
                min_value=1,
                max_value=20,
                value=1,
                disabled=not is_selected,
                key=f"furniture_qty_{idx}",
                label_visibility="collapsed"
            )
        
        with col4:
            if is_selected:
                total_cap = int(row['customer_capacity']) * qty
                st.caption(f"→ {total_cap}")
            else:
                st.caption("—")
        
        if is_selected:
            selected_furniture.append({
                'name': row['furniture_name'],
                'unit_capacity': int(row['customer_capacity']),
                'quantity': qty,
                'total_capacity': int(row['customer_capacity']) * qty,
                'unit_price': row['price'],
                'total_price': parse_price(row['price']) * qty
            })

    # SECTION 5: Capacity Analysis
    if selected_furniture:
        st.divider()
        st.subheader("📊 Capacity Analysis")
        
        # Find bottleneck (furniture with minimum TOTAL capacity)
        bottleneck = min(selected_furniture, key=lambda x: x['total_capacity'])
        effective_capacity = bottleneck['total_capacity']
        
        # Show bottleneck warning
        st.warning(f"⚠️ **Bottleneck:** {bottleneck['name']} ({effective_capacity} capacity total)")
        st.info(f"✓ Your business can serve: **{effective_capacity} customers/hour**")
        
        with st.expander("💡 How to increase capacity"):
            st.markdown(f"""
            To increase from {effective_capacity} to higher capacity:
            - Add more **{bottleneck['name']}** units (currently {bottleneck['quantity']}x)
            - Each additional unit adds {bottleneck['unit_capacity']} capacity
            """)
        
        # Calculate total cost
        total_cost = sum(f['total_price'] for f in selected_furniture)
        
        # Metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Effective Capacity", f"{effective_capacity}/h")
        
        with col2:
            st.metric("Total Furniture Cost", f"${total_cost:,.0f}")
        
        with col3:
            service_rate = 10
            employees_needed = effective_capacity / service_rate
            st.metric("Estimated Employees", f"~{employees_needed:.0f}")
        
        # ================================================================
        # SECTION 6: Confirm Button
        # ================================================================
        st.divider()
        
        if st.button("✓ Confirm Business Setup", type="primary", use_container_width=True):
            # Create Building object
            building = Building(
                business_type=business_category,
                code=building_code,
                capacity_limit=effective_capacity
            )
            
            # Calculate max simultaneous employees
            max_simultaneous = calculate_workstation_capacity(selected_furniture, business_category)
            
            # Save to session state
            st.session_state.business_setup = building
            st.session_state.selected_business_type = business_type
            st.session_state.selected_furniture = selected_furniture
            st.session_state.total_furniture_cost = total_cost
            st.session_state.effective_capacity = effective_capacity
            st.session_state.max_simultaneous_employees = max_simultaneous  # ← NUOVO
            
            st.success(f"✓ Business setup confirmed: {business_type} in building {building_code}")
            st.info(f"📊 Max {max_simultaneous} employees can work simultaneously")  # ← NUOVO
            st.rerun()
    
    else:
        st.info("👆 Select at least one furniture item to proceed")

# ============================================================================
# STEP 2: EMPLOYEE CONFIGURATION
# ============================================================================

def render_employee_configuration():
    """Step 2: Add/Edit employees with demands"""
    st.header("👥 Step 2: Employee Configuration")
    
    if not st.session_state.business_setup:
        st.warning("⚠️ Please complete Step 1: Business Setup first")
        return
    
    # Check if editing
    edit_index = st.session_state.edit_employee_index
    if edit_index is not None and edit_index < len(st.session_state.employees):
        st.info(f"✏️ Editing Employee: {st.session_state.employees[edit_index].name}")
        employee_to_edit = st.session_state.employees[edit_index]
        # Load demands into temp
        if not st.session_state.temp_demands:
            st.session_state.temp_demands = employee_to_edit.demands.copy()
    else:
        employee_to_edit = None
    
    # ========================================
    # EMPLOYEE BASIC INFO
    # ========================================
    st.subheader("Employee Details")
    
    col1, col2 = st.columns(2)
    
    with col1:
        name = st.text_input(
            "Name",
            value=employee_to_edit.name if employee_to_edit else "",
            placeholder="e.g., John Doe",
            key="emp_name"
        )
    
    with col2:
        hourly_wage = st.number_input(
            "Hourly Wage ($)",
            min_value=0.0,
            value=float(employee_to_edit.hourly_wage) if employee_to_edit else 15.0,
            step=0.5,
            format="%.2f",
            key="emp_wage"
        )
    
    roles = get_roles_for_business_type(st.session_state.business_setup.business_type)
    role = st.selectbox(
        "Role",
        options=roles,
        index=roles.index(employee_to_edit.role) if employee_to_edit and employee_to_edit.role in roles else 0,
        key="emp_role"
    )
    
    st.divider()
    
    # ========================================
    # ADD DEMAND FORM
    # ========================================
    st.subheader("Add Demand")
    
    all_demands_dict = get_all_demands_by_category()
    
    col1, col2, col3, col4 = st.columns([2, 3, 2, 1])
    
    with col1:
        category = st.selectbox(
            "Category",
            options=list(all_demands_dict.keys()),
            key="demand_category",
            format_func=lambda x: x.capitalize()
        )
    
    with col2:
        # Demand options based on category
        category_demands = all_demands_dict[category]
        demand_options = list(category_demands.keys())
        
        constraint = st.selectbox(
            "Demand",
            options=demand_options,
            format_func=lambda x: category_demands[x],
            key="demand_constraint"
        )
    
    with col3:
        priority = st.selectbox(
            "Priority",
            options=DEMAND_PRIORITIES,
            format_func=lambda x: x.replace('_', ' ').title(),
            key="demand_priority"
        )
    
    with col4:
        st.write("")  # Spacing
        st.write("")  # Spacing
        if st.button("➕ Add", key="add_demand_btn", use_container_width=True):
            new_demand = Demand(
                category=category,
                constraint=constraint,
                priority=priority
            )
            st.session_state.temp_demands.append(new_demand)
            st.rerun()
    
    # ========================================
    # DEMANDS TABLE
    # ========================================
    if st.session_state.temp_demands:
        st.divider()
        st.subheader("Current Demands")
        
        # Create dataframe for display
        demands_data = []
        for idx, demand in enumerate(st.session_state.temp_demands):
            # Get display text
            category_dict = all_demands_dict[demand.category]
            if demand.constraint in category_dict:
                demand_display = category_dict[demand.constraint]
            else:
                demand_display = demand.constraint
            
            demands_data.append({
                'Index': idx,
                'Category': demand.category.capitalize(),
                'Demand': demand_display,
                'Priority': demand.priority.replace('_', ' ').title()
            })
        
        df_demands = pd.DataFrame(demands_data)
        
        # Show table without action buttons (we'll add them separately)
        st.dataframe(
            df_demands.drop(columns=['Index']),
            use_container_width=True,
            hide_index=True
        )
        
        # Action buttons in columns
        st.markdown("**Actions:**")
        cols = st.columns(min(len(st.session_state.temp_demands), 5))
        for idx in range(len(st.session_state.temp_demands)):
            col_idx = idx % 5
            with cols[col_idx]:
                demand_name = st.session_state.temp_demands[idx].constraint[:15] + "..."
                if st.button(f"🗑️ {demand_name}", key=f"del_demand_{idx}", use_container_width=True):
                    st.session_state.temp_demands.pop(idx)
                    st.rerun()
    
    st.divider()
    
    # ========================================
    # SAVE EMPLOYEE BUTTON
    # ========================================
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button(
            "✓ Save Employee" if employee_to_edit else "➕ Add Employee",
            type="primary",
            use_container_width=True,
            disabled=not name
        ):
            new_employee = Employee(
                name=name,
                role=role,
                hourly_wage=hourly_wage,
                demands=st.session_state.temp_demands.copy()
            )
            
            if employee_to_edit:
                st.session_state.employees[edit_index] = new_employee
                st.success(f"✓ Employee updated: {name}")
            else:
                st.session_state.employees.append(new_employee)
                st.success(f"✓ Employee added: {name}")
            
            # Reset
            st.session_state.edit_employee_index = None
            st.session_state.temp_demands = []
            st.rerun()
    
    with col2:
        if employee_to_edit:
            if st.button("✗ Cancel Edit", use_container_width=True):
                st.session_state.edit_employee_index = None
                st.session_state.temp_demands = []
                st.rerun()


# ============================================================================
# STEP 3: EMPLOYEES SUMMARY
# ============================================================================

def render_employees_summary():
    """Step 3: Display and manage employee list"""
    st.header("📊 Step 3: Employees Summary")
    
    if not st.session_state.employees:
        st.info("No employees added yet. Add employees in Step 2.")
        return
    
    st.markdown(f"**Total Employees:** {len(st.session_state.employees)}")
    
    # Render each employee in a card-like format
    for idx, emp in enumerate(st.session_state.employees):
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 4, 2])
            
            with col1:
                st.markdown(f"**{emp.name}**")
                st.caption(f"{emp.role}")
            
            with col2:
                st.metric("Wage/h", f"${emp.hourly_wage:.2f}")
            
            with col3:
                # Demands dropdown
                if emp.demands:
                    all_demands_dict = get_all_demands_by_category()
                    demands_list = []
                    for demand in emp.demands:
                        # Get display text
                        category_dict = all_demands_dict.get(demand.category, {})
                        if demand.constraint in category_dict:
                            demand_text = category_dict[demand.constraint]
                        else:
                            demand_text = demand.constraint
                        
                        demands_list.append(f"• {demand_text} ({demand.priority})")
                    
                    with st.expander(f"📋 Demands ({len(emp.demands)})", expanded=False):
                        for demand_text in demands_list:
                            st.markdown(demand_text)
                else:
                    st.caption("No demands")
            
            with col4:
                # Action buttons
                edit_col, del_col = st.columns(2)
                with edit_col:
                    if st.button("✏️", key=f"edit_{idx}", use_container_width=True):
                        st.session_state.edit_employee_index = idx
                        st.session_state.temp_demands = emp.demands.copy()
                        st.rerun()
                
                with del_col:
                    if st.button("🗑️", key=f"delete_{idx}", use_container_width=True):
                        st.session_state.employees.pop(idx)
                        st.success(f"Deleted: {emp.name}")
                        st.rerun()
            
            st.divider()

# ============================================================================
# STEP 4: OPERATING HOURS
# ============================================================================

def render_operating_hours():
    """Step 4: Configure weekly operating hours"""
    st.header("📅 Step 4: Operating Hours")
    
    if not st.session_state.business_setup:
        st.warning("⚠️ Please complete Step 1: Business Setup first")
        return
    
    st.markdown("Configure operating hours for each day of the week:")
    
    # Initialize weekly schedule if empty
    if not st.session_state.weekly_schedule:
        st.session_state.weekly_schedule = [
            DailySchedule(day_name=day) for day in DAYS_OF_WEEK
        ]
    
    # Form for all days
    with st.form("operating_hours_form"):
        updated_schedule = []
        
        for idx, day in enumerate(DAYS_OF_WEEK):
            current = st.session_state.weekly_schedule[idx] if idx < len(st.session_state.weekly_schedule) else DailySchedule(day_name=day)
            
            st.markdown(f"### {day}")
            col1, col2, col3 = st.columns([1, 2, 2])
            
            with col1:
                is_open = st.checkbox(
                    "Open",
                    value=current.is_open,
                    key=f"open_{day}"
                )
            
            with col2:
                start_hour = st.number_input(
                    "Start Hour",
                    min_value=0,
                    max_value=23,
                    value=current.start_hour if current.is_open else DEFAULT_START_HOUR,
                    disabled=not is_open,
                    key=f"start_{day}",
                    help="24-hour format (0-23)"
                )
            
            with col3:
                end_hour = st.number_input(
                    "End Hour",
                    min_value=0,
                    max_value=23,
                    value=current.end_hour if current.is_open else DEFAULT_END_HOUR,
                    disabled=not is_open,
                    key=f"end_{day}",
                    help="24-hour format (0-23)"
                )
            
            updated_schedule.append(DailySchedule(
                day_name=day,
                is_open=is_open,
                start_hour=start_hour,
                end_hour=end_hour
            ))
        
        # Save button
        if st.form_submit_button("✓ Save Operating Hours", type="primary", use_container_width=True):
            st.session_state.weekly_schedule = updated_schedule
            st.success("✓ Operating hours saved!")
            st.rerun()
    
    # Show summary
    if st.session_state.weekly_schedule:
        st.divider()
        st.subheader("Summary")
        
        total_hours = sum(day.hours_open for day in st.session_state.weekly_schedule)
        open_days = sum(1 for day in st.session_state.weekly_schedule if day.is_open)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Open Days", open_days)
        with col2:
            st.metric("Total Weekly Hours", total_hours)
        
        # Show schedule
        for day in st.session_state.weekly_schedule:
            if day.is_open:
                st.text(f"  {day}")



st.divider()

# ============================================================================
# STEP 5: RENDER OPTIMIZATION
# ============================================================================

def render_optimization():
    if not st.session_state.business_setup:
        st.warning("Complete Step 1")
        return 
    
    if not st.session_state.max_simultaneous_employees:
        st.warning("Complete Step 1")
        return
    
    if not st.session_state.employees:
        st.warning("Add at least 1 employee in Step 2")
        return
    
    if not st.session_state.weekly_schedule:
        st.warning("Configure operating hours in Step 4")
        return

    st.header("🚀 Step 5: Optimization")

    alpha = 1.0
    beta = 0.5

    if st.button("🚀 Run Optimization", type="primary"):
        # Previeni doppia esecuzione
        if st.session_state.get('is_optimizing', False):
            st.warning("⏳ Optimization already in progress...")
            st.stop()
        
        # Verifica nomi dipendenti unici
        employee_names = [emp.name for emp in st.session_state.employees]
        if len(employee_names) != len(set(employee_names)):
            st.error("❌ Error: Employee names must be unique! Found duplicates.")
            st.stop()
        
        with st.spinner("Optimizing schedules..."):
            try:
                result = optimize_schedule(
                    business_setup=st.session_state.business_setup,
                    employees=st.session_state.employees,
                    weekly_schedule=st.session_state.weekly_schedule,
                    max_simultaneous=st.session_state.max_simultaneous_employees,
                    alpha=alpha,
                    beta=beta
                )
                st.session_state.optimization_result = result
            except Exception as e:
                st.error(f"❌ Optimization error: {type(e).__name__}")
                st.error(f"Details: {str(e)}")
                st.info("This might be due to:")
                st.code("""
    - Duplicate employee names
    - Invalid constraint configuration
    - PuLP solver issue
                """)
                # Salva un risultato di errore
                st.session_state.optimization_result = None
        
        
        
        # Pulisci vecchi risultati
        if 'optimization_result' in st.session_state:
            del st.session_state.optimization_result
        
        # Imposta flag
        st.session_state.is_optimizing = True
        
        with st.spinner("Optimizing schedules..."):
            try:
                result = optimize_schedule(
                    business_setup=st.session_state.business_setup,
                    employees=st.session_state.employees,
                    weekly_schedule=st.session_state.weekly_schedule,
                    max_simultaneous=st.session_state.max_simultaneous_employees,
                    alpha=alpha,
                    beta=beta
                )
                st.session_state.optimization_result = result
            finally:
                # Assicurati che il flag venga sempre resettato
                st.session_state.is_optimizing = False
        

            
            

    # Mostra risultati solo se esistono
    if 'optimization_result' in st.session_state:
        result = st.session_state.optimization_result
        
        # ✅ PRIMA controlla se result è None
        if result is None:
            st.warning("⚠️ Previous optimization encountered an error. Please try again.")
        elif not result.success:  # <-- Cambia da "if" a "elif"
            st.error(f"❌ Optimization failed: {result.status}")
            st.warning("""
            **Possible causes:**
            - Employee constraints are too restrictive
            - Not enough employees to cover all shifts
            - Conflicting demands (e.g., free weekends + full-time may be impossible)
            
            **Suggestions:**
            - Add more employees
            - Reduce critical demands to 'important' priority
            - Adjust operating hours
            - Increase max simultaneous employees per shift
            """)
            
            st.info(f"Solver attempted solution for {result.solver_time:.2f}s")
        else:  # <-- success=True
            st.success(f"✅ Optimization successful! (solved in {result.solver_time:.2f}s)")
            
            # Metriche
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Weekly Cost", f"${result.total_cost:.2f}")
            with col2:
                st.metric("Employee Satisfaction", f"{result.total_satisfaction:.1f}%")
            
            # Schedule table
            st.subheader("📅 Optimized Weekly Schedule")
            
           
            schedule_data = {}
            daily_shifts = result.daily_shifts
            
            for emp in st.session_state.employees:
                schedule_data[emp.name] = []
                
                for day in DAYS_OF_WEEK:
                    shifts = result.schedule[emp.name][day]
                    if shifts:
                        shifts_info = daily_shifts[day][shifts[0]]
                        schedule_data[emp.name].append(
                            f"{shifts_info['start']}-{shifts_info['end']}"
                        )
                    else:
                        schedule_data[emp.name].append('-')
            
            df = pd.DataFrame(schedule_data, index=DAYS_OF_WEEK)
            st.dataframe(df, use_container_width=True)
    
    
        
# ============================================================================
# MAIN RENDER FUNCTION
# ============================================================================

def render_schedule_optimizer_page():
    """Main render function for Schedule Optimizer page"""
    
    
    st.title("🗓️ Schedule Optimizer")
    st.markdown("Configure your business and employees for optimal scheduling")
    
    st.divider()
    
    # Render all steps
    render_business_setup()
    st.divider()
    
    render_employee_configuration()
    st.divider()
    
    render_employees_summary()
    st.divider()
    
    render_operating_hours()
    st.divider()
    render_optimization()

    # Show complete setup summary at bottom
    if ('business_setup' in st.session_state and
        st.session_state.business_setup and
        'employees' in st.session_state and
        st.session_state.employees and
        'weekly_schedule' in st.session_state and
        st.session_state.weekly_schedule):

        # Business info
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Business**")
            st.write(f"Type: {st.session_state.business_setup.business_type}")
            st.write(f"Building: {st.session_state.business_setup.code}")
            st.write(f"Capacity: {st.session_state.business_setup.capacity_limit} customers/h")

        with col2:
            st.markdown("**Operating Hours**")
            total_hours = sum(day.hours_open for day in st.session_state.weekly_schedule)
            open_days = sum(1 for day in st.session_state.weekly_schedule if day.is_open)
            st.write(f"Open Days: {open_days}/7")
            st.write(f"Total Weekly Hours: {total_hours}h")

        # Employee list
        st.markdown("**Employees**")
        st.write(f"Total: {len(st.session_state.employees)} employees")

        employee_summary = []
        for emp in st.session_state.employees:
            employee_summary.append(f"- **{emp.name}** - {emp.role} (${emp.hourly_wage:.2f}/h) - {len(emp.demands)} demands")

        for emp_text in employee_summary:
            st.markdown(emp_text)
    


# ============================================================================
# STANDALONE EXECUTION
# ============================================================================

if __name__ == "__main__":
    st.set_page_config(
        page_title="Schedule Optimizer",
        page_icon="🗓️",
        layout="wide"
    )
    render_schedule_optimizer_page()