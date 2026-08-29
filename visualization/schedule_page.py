"""
Schedule Optimizer - Streamlit Page
UI for configuring business setup and employees
"""
import streamlit as st
import pandas as pd
from typing import List, Optional
from analysis.schedule_optimizer import optimize_schedule, optimize_schedule_variable




# Import models and constraints
from analysis.schedule_models import Building, Employee, Demand, DailySchedule, BusinessSetup
from analysis.schedule_constraints import (
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
    # SECTION 3b: Factory Planning (production-based, no customer demand)
    # ================================================================
    if business_type == "Factory":
        from visualization.factory_planning import render_factory_planning
        render_factory_planning()
    
    # ================================================================
    # SECTION 4: Furniture Selection
    # ================================================================
    # SECTION 4: Furniture Selection
    # SECTION 4: Furniture Selection
    st.subheader("🪑 Furniture Selection")

    df_furniture = get_furniture_for_business(business_type)

    # Store selections with quantities
    selected_furniture = []
    
    h1, h2, h3, h4, h5 = st.columns([3, 1, 1, 1, 1])

    with h1:
        st.markdown("**Furniture**")
    with h2:
        st.markdown("**Cust. Cap.**")
    with h3:
        st.markdown("**Unit Price**")
    with h4:
        st.markdown("**Qty**")
    with h5:
        st.markdown("**Total Price**")

    for idx, row in df_furniture.iterrows():
        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])

        with col1:
            is_selected = st.checkbox(
                row['furniture_name'],
                key=f"furniture_check_{idx}"
            )

        with col2:
            st.caption(f"📊 {row['customer_capacity']}")

        with col3:
            unit_price = parse_price(row['price'])
            st.caption(f"${unit_price:,.0f}")

        with col4:
            qty = st.number_input(
                "Qty",
                min_value=1,
                max_value=20,
                value=1,
                disabled=not is_selected,
                key=f"furniture_qty_{idx}",
                label_visibility="collapsed"
            )

        with col5:
            if is_selected:
                total_price_item = parse_price(row['price']) * qty
                st.caption(f"${total_price_item:,.0f}")
            else:
                st.caption("—")
        
        if is_selected:
            selected_furniture.append({
                'name': row['furniture_name'],
                'unit_capacity': int(row['customer_capacity']),
                'quantity': qty,
                'total_capacity': int(row['customer_capacity']) * qty,
                'unit_price': row['price'],
                'total_price': parse_price(row['price']) * qty,
                'is_workstation': row.get('is_workstation', False),
                'suitable_skills': row.get('suitable_skills', []),
            })

    # SECTION 5: Capacity Analysis
    if selected_furniture:
        st.divider()
        st.subheader("📊 Capacity Analysis")
        
        # Bottleneck = minima capacita' tra le SOLE furniture che servono clienti.
        # Le 0-capacita' (es. Cleaning Station) non sono stadi del flusso: escluse,
        # altrimenti azzererebbero la capacita' e la domanda di Customer Service.
        customer_furniture = [f for f in selected_furniture if f['total_capacity'] > 0]
        if customer_furniture:
            bottleneck = min(customer_furniture, key=lambda x: x['total_capacity'])
            effective_capacity = bottleneck['total_capacity']
        else:
            bottleneck = None
            effective_capacity = 0

        if bottleneck:
            st.warning(f"⚠️ **Bottleneck:** {bottleneck['name']} ({effective_capacity} capacity total)")
            st.info(f"✓ Your business can serve: **{effective_capacity} customers/hour**")

            with st.expander("💡 How to increase capacity"):
                st.markdown(f"""
                To increase from {effective_capacity} to higher capacity:
                - Add more **{bottleneck['name']}** units (currently {bottleneck['quantity']}x)
                - Each additional unit adds {bottleneck['unit_capacity']} capacity
                """)
        else:
            st.warning("⚠️ No customer-serving furniture selected (only 0-capacity items "
                       "like Cleaning Station). Add e.g. a Cash Register to set capacity.")
        
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
                capacity_limit=effective_capacity,
                business_name=business_type,  # Display name e.g. 'Coffee Shop'
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

    # --- Gestione stato del form PRIMA di creare i widget ---
    # Streamlit non permette di modificare la key di un widget dopo che e' stato
    # istanziato: quindi pulizia (dopo save/cancel) e caricamento (in edit) vanno
    # fatti qui, in cima, via flag impostati dai pulsanti.
    if st.session_state.pop('_reset_emp_form', False):
        for _k in ('emp_name', 'emp_wage', 'emp_role',
                   'demand_category', 'demand_constraint', 'demand_priority'):
            st.session_state.pop(_k, None)
    _load_uid = st.session_state.pop('_load_emp_uid', None)
    if _load_uid is not None:
        _emp = next((e for e in st.session_state.employees if e.uid == _load_uid), None)
        if _emp is not None:
            st.session_state['emp_name'] = _emp.name
            st.session_state['emp_wage'] = float(_emp.hourly_wage)
            st.session_state['emp_role'] = _emp.role

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
    
    # Use the specific business name (e.g. 'Coffee Shop') for role lookup, not the category
    business_name = getattr(st.session_state.business_setup, 'business_name', '') or st.session_state.get('selected_business_type', '')
    roles = get_roles_for_business_type(business_name)
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
            # Blocco nomi duplicati: evita due dipendenti con lo stesso nome
            # (confonde report e modifiche). Esclude quello in modifica.
            _norm = name.strip().lower()
            _dup = any(
                e.name.strip().lower() == _norm and i != edit_index
                for i, e in enumerate(st.session_state.employees)
            )
            if _dup:
                st.error(f"⚠️ An employee named '{name}' already exists. Use a different name.")
            else:
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

                # Reset: azzera modalita' edit e PULISCI i campi al prossimo run
                st.session_state.edit_employee_index = None
                st.session_state.temp_demands = []
                st.session_state['_reset_emp_form'] = True
                st.rerun()
    
    with col2:
        if employee_to_edit:
            if st.button("✗ Cancel Edit", use_container_width=True):
                st.session_state.edit_employee_index = None
                st.session_state.temp_demands = []
                st.session_state['_reset_emp_form'] = True
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
                        # Carica i valori del dipendente nei campi al prossimo run
                        st.session_state['_load_emp_uid'] = emp.uid
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
# STAFFING SUGGESTION (advice from furniture + hours + game data)
# ============================================================================

def render_staffing_suggestion():
    st.header("🧑‍💼 Staffing Suggestion")

    setup = st.session_state.get('business_setup')
    furniture = st.session_state.get('selected_furniture')
    week = st.session_state.get('weekly_schedule')
    if not setup or not furniture:
        st.info("Complete the business setup (with furniture) to see a staffing suggestion.")
        return
    if not week:
        st.info("Set the operating hours to see a staffing suggestion.")
        return

    from analysis.schedule_constraints import (
        compute_staffing_recommendation, hours_range, get_role_workstations,
    )

    role_ws = get_role_workstations(furniture)
    if not role_ws:
        st.info("No workstations selected yet — add furniture to get a suggestion.")
        return

    open_hours = {
        d.day_name: (hours_range(d.start_hour, d.end_hour) if d.is_open else [])
        for d in week
    }
    biz = getattr(setup, 'business_name', '') or st.session_state.get('selected_business_type', '')
    cap = getattr(setup, 'capacity_limit', 0)
    recs = compute_staffing_recommendation(biz, cap, open_hours, role_ws)

    st.caption(
        "Suggested hiring based on your furniture, opening hours and the game's demand "
        "curve — no employees needed yet. 'Why' shows the drivers behind each number."
    )
    any_shown = False
    for role, r in sorted(recs.items()):
        if r['headcount'] <= 0:
            continue
        any_shown = True
        mix = []
        if r['full_time']:
            mix.append(f"{r['full_time']} full-time")
        if r['part_time']:
            mix.append(f"{r['part_time']} part-time")
        mix_txt = " + ".join(mix) if mix else f"{r['headcount']}"
        st.markdown(f"**{role}** — hire **{r['headcount']}**  ({mix_txt})")
        st.caption(
            f"Why: up to **{r['peak']}** at once during peak · open span **{r['span']}h/day** "
            f"· ~**{r['hours']}h/week** of work needed · {r['stations']} station(s)"
        )
    if not any_shown:
        st.caption("No staffing needed for the current setup.")


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
            st.session_state.is_optimizing = True
            try:
                # NUOVO modello a turni variabili (fallback: optimize_schedule)
                result = optimize_schedule_variable(
                    business_setup=st.session_state.business_setup,
                    employees=st.session_state.employees,
                    weekly_schedule=st.session_state.weekly_schedule,
                    max_simultaneous=st.session_state.max_simultaneous_employees,
                    selected_furniture=st.session_state.selected_furniture,
                    alpha=alpha,
                    beta=beta,
                )
                st.session_state.optimization_result = result
            except Exception as e:
                st.error(f"❌ Optimization error: {type(e).__name__}")
                st.error(f"Details: {str(e)}")
                st.session_state.optimization_result = None
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
                sat_display = "N/A" if result.total_satisfaction is None else f"{result.total_satisfaction:.1f}%"
                st.metric("Employee Satisfaction", sat_display)

            # --- Coverage: real gaps (need staff) vs extra (service margin) ---
            cov = result.coverage_report or {}
            real = {r: d for r, d in cov.items() if d.get('real', 0) > 0.5}
            opt = {r: d for r, d in cov.items() if d.get('optional', 0) > 0.5}
            if real:
                rows_txt = "\n".join(
                    f"- **{r}**: {d['real']:.0f}h uncovered → hire **~{d['suggest']} more "
                    f"employee{'' if d['suggest']==1 else 's'}**"
                    for r, d in sorted(real.items())
                )
                st.warning("⚠️ **Incomplete coverage — more employees needed**\n\n" + rows_txt)
            if opt:
                rows_txt = "\n".join(
                    f"- **{r}**: {d['optional']:.0f}h of extra coverage left unfilled"
                    for r, d in sorted(opt.items())
                )
                st.info("ℹ️ **Service margin**: with more staff you could serve more customers "
                        "during peak hours (this is not a sales gap, it's a cost trade-off).\n\n" + rows_txt)
            if not real and not opt:
                st.success("✅ Full coverage: no uncovered hours.")

            

            # --- Comparison with the actual business wage (baseline = weekly average) ---
            st.markdown("**Comparison with the current business**")
            df_tx = st.session_state.get('df')
            if df_tx is None:
                st.caption("💡 Import transactions on the main page to compare the planned "
                           "cost with the business's actual wage.")
            else:
                from analysis.temporal_analyzer import TemporalAnalyzer
                ta = TemporalAnalyzer(df_tx)
                wk_all = ta.aggregate_by_period('weekly')
                biz_names = (
                    sorted(wk_all['business'].dropna().unique().tolist())
                    if 'business' in wk_all.columns else []
                )
                if not biz_names or 'wages' not in wk_all.columns:
                    st.caption("No wage data in the imported file.")
                else:
                    sel_biz = st.selectbox(
                        "Business to compare", options=biz_names, key="cmp_wage_business"
                    )
                    wk = wk_all[wk_all['business'] == sel_biz]
                    n_days = int(getattr(ta, 'total_days', 0) or 0)
                    if len(wk) > 0 and n_days > 0:
                        # Tasso settimanale "vero": wage totale del business sui dati,
                        # normalizzato a 7 giorni. Evita che una settimana parziale a
                        # fine periodo abbassi artificialmente la media.
                        total_wages = float(wk['wages'].sum())
                        avg_weekly = total_wages / n_days * 7
                        delta = result.total_cost - avg_weekly
                        c1, c2 = st.columns(2)
                        with c1:
                            st.metric("Avg weekly wage", f"${avg_weekly:,.2f}")
                        with c2:
                            st.metric(
                                "Δ planned − actual", f"${delta:,.2f}",
                                delta=f"{delta:,.2f}", delta_color="inverse"
                            )
                        st.caption(
                            f"Baseline = total business wage ÷ {n_days} days × 7 "
                            f"(weekly rate, normalized for partial weeks). "
                            f"Base salaries only (no insurance/HR), consistent with the optimizer."
                        )
                    else:
                        st.caption("No wage data for the selected business.")

            # Schedule table
            st.subheader("📅 Optimized Weekly Schedule")
            
           
            import streamlit.components.v1 as components
            from visualization.schedule_grid import (
                build_station_rows, assign_shift_employees, build_day_html
            )

            stations = build_station_rows(st.session_state.selected_furniture)
            assignment = assign_shift_employees(result, st.session_state.employees, stations)

            grid_col, panel_col = st.columns([3, 1])

            with grid_col:
                open_days = [d.day_name for d in st.session_state.weekly_schedule if d.is_open]
                if not open_days:
                    st.info("No open days.")
                elif not stations:
                    st.info("No workstation selected: grid unavailable.")
                else:
                    sel_day = st.radio("Day", open_days, horizontal=True, key="grid_day")
                    grid_html = build_day_html(
                        sel_day, result, stations, assignment, st.session_state.employees
                    )
                    components.html(
                        grid_html,
                        height=70 + 49 * (len(stations) + 1),
                        scrolling=False,
                    )

            with panel_col:
                dropped = [
                    e.name for e in st.session_state.employees
                    if not any(result.schedule[e.uid][d] for d in DAYS_OF_WEEK)
                ]
                st.markdown(f"**Dropped ({len(dropped)})**")
                st.caption("\n".join(f"• {n}" for n in dropped) if dropped else "none")

                st.markdown("**Active per role**")
                role_counts = {}
                for e in st.session_state.employees:
                    if any(result.schedule[e.uid][d] for d in DAYS_OF_WEEK):
                        role_counts[e.role] = role_counts.get(e.role, 0) + 1
                if role_counts:
                    for role, n in sorted(role_counts.items()):
                        st.caption(f"{role}: {n}")
                else:
                    st.caption("—")
    
            # --- Recommendations: plain-language explanation of the schedule's choices ---
            recs = result.recommendations or []
            if recs:
                st.markdown("### 💡 Recommendations")
                st.caption("Why the schedule looks like this, and what you could change. "
                           "Quantified in staff-hours/headcount.")
                _ICON = {'high': '⚠️', 'medium': '🔸', 'low': '·', 'info': 'ℹ️'}
                _order = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
                for r in sorted(recs, key=lambda x: _order.get(x.severity, 9)):
                    with st.container(border=True):
                        st.markdown(f"{_ICON.get(r.severity, '•')} **{r.title}**")
                        if r.detail:
                            st.caption(r.detail)
                        if r.suggestion:
                            st.markdown(f"➡️ {r.suggestion}")
    
        
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

    render_staffing_suggestion()
    st.divider()
    
    
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