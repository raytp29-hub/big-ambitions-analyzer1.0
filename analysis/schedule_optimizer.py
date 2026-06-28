"""
Schedule Optimization Engine using PuLP
Minimizes wage costs while maximizing employee satisfaction
"""


from operator import lshift
from typing import List, Dict, Tuple
from dataclasses import dataclass
import pulp
from analysis.schedule_models import Employee, DailySchedule, BusinessSetup, OptimizationResult
from analysis.schedule_constraints import (
    get_role_workstations,
    compute_peak_customers,
    compute_role_demand,
)


SHIFTS = {
    'morning': {
        'start': 6,
        'end': 14,
        'hours': 8,
        'label': 'Morning (6:00-14:00)'
    },
    'afternoon': {
        'start': 14,
        'end': 22,
        'hours': 8,
        'label': 'Afternoon (14:00-22:00)'
    },
    'night': {
        'start': 22,
        'end': 6,  # Next day
        'hours': 8,
        'label': 'Night (22:00-6:00)'
    }
}


DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


DEMAND_SHIFT_CONFLICTS = {
    'no_morning': ['morning'],
    'no_afternoon': ['afternoon'],
    'no_evening': ['afternoon', 'night'],  # 18:00-22:00 overlaps both
    'no_night': ['night']
}



def generate_shifts_for_day(day_schedule: DailySchedule) -> Dict[str, Dict]:
    """
    Generate dynamic shifts based on actual business operating hours.
    
    Args:
        day_schedule: DailySchedule with start/end hours
    
    Returns:
        Dict of shift_name → shift_info (start, end, hours, type)
    """
    if not day_schedule.is_open:
        return {}
    
    start = day_schedule.start_hour
    end = day_schedule.end_hour
    total_hours = day_schedule.hours_open
    
    shifts = {}
    
    # Case 1: Business open ≥16 hours → 2 shifts of 8h each
    if total_hours >= 16:
        shifts['shift_1'] = {
            'start': start,
            'end': start + 8,
            'hours': 8,
            'type': classify_shift_type(start, start + 8)
        }
        shifts['shift_2'] = {
            'start': start + 8,
            'end': start + 16,
            'hours': 8,
            'type': classify_shift_type(start + 8, start + 16)
        }
    
    # Case 2: Business open 8-16 hours → 2 overlapping shifts of 8h
    elif total_hours >= 8:
        shifts['shift_1'] = {
            'start': start,
            'end': min(start + 8, end),
            'hours': min(8, total_hours),
            'type': classify_shift_type(start, start + 8)
        }
        
        # Second shift starts halfway through
        shift_2_start = start + (total_hours // 2)
        shifts['shift_2'] = {
            'start': shift_2_start,
            'end': end,
            'hours': end - shift_2_start,
            'type': classify_shift_type(shift_2_start, end)
        }
    
    # Case 3: Business open <8 hours → 1 shift covering all hours
    else:
        shifts['shift_1'] = {
            'start': start,
            'end': end,
            'hours': total_hours,
            'type': classify_shift_type(start, end)
        }
    
    return shifts


def classify_shift_type(start_hour: int, end_hour: int) -> str:
    """
    Classify shift as morning/afternoon/night based on when it occurs.
    Used to check compatibility with employee demands (no_morning, etc.)
    
    Args:
        start_hour: Shift start (0-23)
        end_hour: Shift end (0-23 or >23 if wraps)
    
    Returns:
        'morning', 'afternoon', or 'night'
    """
    # Shift type based on START time
    if start_hour < 12:
        return 'morning'
    elif start_hour < 18:
        return 'afternoon'
    else:
        return 'night'


def check_shift_compatible_with_demands(
    shift_info: Dict,
    employee: Employee
) -> Tuple[bool, List[str]]:
    """
    Check if a shift is compatible with employee's schedule demands.
    
    Args:
        shift_info: Dict with start, end, hours, type
        employee: Employee with demands
    
    Returns:
        (is_compatible, list_of_conflicting_demands)
    """
    shift_start = shift_info['start']
    shift_end = shift_info['end']
    conflicts = []
    
    # Check each schedule demand
    for demand in employee.demands:
        if demand.category != 'schedule':
            continue
        
        constraint = demand.constraint
        
        # Check time-based constraints
        if constraint == 'no_morning' and shift_start < 10:
            conflicts.append(f"{constraint} (shift starts at {shift_start}:00)")
        
        elif constraint == 'no_afternoon' and 14 <= shift_start < 16:
            conflicts.append(f"{constraint} (shift during 14-16)")
        
        elif constraint == 'no_evening' and 18 <= shift_start < 22:
            conflicts.append(f"{constraint} (shift during 18-22)")
        
        elif constraint == 'no_night' and (shift_start >= 22 or shift_end <= 6):
            conflicts.append(f"{constraint} (shift during night hours)")
    
    return (len(conflicts) == 0, conflicts)




# ============================================================================
# SATISFACTION HELPERS
# ============================================================================

def _forbidden_shift_sum(emp_name, constraint, x, daily_shifts):
    """Somma delle x dei turni 'vietati' da una richiesta di tipo 'avoid'
    (no_morning, no_afternoon, no_evening, no_night, no_cleaning, free_weekend).
    Se la somma e' 0, la richiesta e' soddisfatta."""
    if constraint == 'free_weekend':
        return pulp.lpSum(
            x[emp_name][day][sh]
            for day in ('Saturday', 'Sunday')
            if day in daily_shifts and daily_shifts[day]
            for sh in daily_shifts[day]
        )
    forbidden_types = {
        'no_morning': {'morning'},
        'no_afternoon': {'afternoon'},
        'no_evening': {'afternoon', 'night'},
        'no_night': {'night'},
        'no_cleaning': {'night'},
    }.get(constraint, set())
    return pulp.lpSum(
        x[emp_name][day][sh]
        for day in DAYS_OF_WEEK
        if day in daily_shifts and daily_shifts[day]
        for sh, info in daily_shifts[day].items()
        if info['type'] in forbidden_types
    )


# ============================================================================
# MAIN OPTIMIZATION FUNCTION
# ============================================================================

def optimize_schedule(
    business_setup: BusinessSetup,
    employees: List[Employee],
    weekly_schedule: List[DailySchedule],
    max_simultaneous: int,
    selected_furniture: List[Dict] = None,
    cleaning_per_shift: int = 1,
    security_per_shift: int = 1,
    alpha: float = 1.0,
    beta: float = 0.5
) -> OptimizationResult:
    """Main optimization function using PuLP."""
    
    print("="*60)
    print("SCHEDULE OPTIMIZATION")
    print("="*60)
    print(f"Employees: {len(employees)}")
    print(f"Business capacity: {business_setup.capacity_limit}/h")
    print(f"Max simultaneous: {max_simultaneous}")
    print(f"Operating days: {sum(1 for d in weekly_schedule if d.is_open)}/7")
    print(f"Optimization weights: α={alpha} (cost), β={beta} (satisfaction)")
    print("="*60)
    
    # ========================================================================
    # STEP 1: Generate dynamic shifts for each day
    # ========================================================================
    print("\n[Step 1] Generating shifts...")
    
    daily_shifts = {}  # day_name → {shift_name: shift_info}
    
    for day_schedule in weekly_schedule:
        if day_schedule.is_open:
            shifts = generate_shifts_for_day(day_schedule)
            daily_shifts[day_schedule.day_name] = shifts
            
            print(f"  {day_schedule.day_name}: {len(shifts)} shifts ({day_schedule.start_hour}-{day_schedule.end_hour})")
            for shift_name, shift_info in shifts.items():
                print(f"    - {shift_name}: {shift_info['start']}-{shift_info['end']} ({shift_info['hours']}h, {shift_info['type']})")
        else:
            daily_shifts[day_schedule.day_name] = {}
            print(f"  {day_schedule.day_name}: CLOSED")
    
    print(f"✓ Generated {sum(len(s) for s in daily_shifts.values())} total shifts")
    
        # ========================================================================
        # STEP 2: Create decision variables
        # ========================================================================
    print("\n[Step 2] Creating decision variables...")

    # Create PulP problem (minimizzation)

    prob = pulp.LpProblem("Employee_Schedule_Optimization", pulp.LpMinimize)

    # Decision variables: x[employee_name][day][shifgt] = 0 or 1
    x = {}


    for emp in employees:
        x[emp.name] = {}
        
        for day in DAYS_OF_WEEK:
            x[emp.name][day] = {}
            
            if day in daily_shifts and daily_shifts[day]:
                for shift_name in daily_shifts[day].keys():
                    # Create binary variable
                    var_name = f"x_{emp.name}_{day}_{shift_name}"
                    x[emp.name][day][shift_name] = pulp.LpVariable(
                        var_name,
                        cat='Binary'
                    )
    total_vars = sum(
        len(x[emp.name][day])
        for emp in employees
        for day in DAYS_OF_WEEK
        if day in x[emp.name]
    )
    print(f"✓ Created {total_vars} binary decision variables")
    print(f"  ({len(employees)} employees × {len([d for d in weekly_schedule if d.is_open])} days × ~2 shifts)")        
    
    
    # ========================================================================
    # STEP 3: Active-employee variables + objective function
    # ========================================================================
    print("\n[Step 3] Creating active-employee vars and objective...")

    # y[employee_name] = 1 se il dipendente è ATTIVO questa settimana, 0 se scartato
    y = {}
    for emp in employees:
        y[emp.name] = pulp.LpVariable(f"y_{emp.name}", cat='Binary')

    # Collegamento x <= y: se y=0 il dipendente non può lavorare nessun turno
    for emp in employees:
        for day in DAYS_OF_WEEK:
            if day in daily_shifts and daily_shifts[day]:
                for shift_name in daily_shifts[day].keys():
                    prob += x[emp.name][day][shift_name] <= y[emp.name], \
                        f"link_{emp.name}_{day}_{shift_name}"

    # Satisfaction points by priority (usati nello Step 5 per il punteggio)
    SATISFACTION_POINTS = {
        'critical': 100,
        'important': 80,
        'nice_to_have': 50
    }

    # Obiettivo: minimizza il costo salariale settimanale.
    # + penalità minima su Σy: a parità di costo, preferisci meno dipendenti attivi.
    total_cost_expr = pulp.lpSum(
        emp.hourly_wage * shift_info['hours'] * x[emp.name][day][shift_name]
        for emp in employees
        for day in DAYS_OF_WEEK
        if day in daily_shifts and daily_shifts[day]
        for shift_name, shift_info in daily_shifts[day].items()
    )
    # L'obiettivo viene impostato in fondo (sezione 4.9), dopo aver creato le
    # variabili di soddisfazione, cosi' include costo E soddisfazione insieme.
    print(f"  Cost expression built (objective set later, with satisfaction)")
        
        
     # ========================================================================
    # STEP 4: Add constraints
    # ========================================================================
    print("\n[Step 4] Adding constraints...")
    
    constraint_count = 0
    
    # ------------------------------------------------------------------------
    # 4.1: Part-time / Full-time constraints
    # ------------------------------------------------------------------------
    for emp in employees:
        # Calculate total hours worked per week
        total_hours = pulp.lpSum(
            shift_info['hours'] * x[emp.name][day][shift_name]
            for day in DAYS_OF_WEEK
            if day in daily_shifts and daily_shifts[day]
            for shift_name, shift_info in daily_shifts[day].items()
        )
        
        # Check for part-time/full-time demands
        for demand in emp.demands:
            if demand.category == 'schedule':
                if demand.constraint == 'part_time' and demand.priority == 'critical':
                    # Part-time: 10-30 hours/week (condizionato su y: se y=0 nessun minimo)
                    prob += total_hours >= 10 * y[emp.name], f"{emp.name}_min_part_time"
                    prob += total_hours <= 30 * y[emp.name], f"{emp.name}_max_part_time"
                    constraint_count += 2
                    print(f"  ✓ {emp.name}: Part-time (10-30h/week)")

                elif demand.constraint == 'full_time' and demand.priority == 'critical':
                    # Full-time: 30-50 hours/week (condizionato su y)
                    prob += total_hours >= 30 * y[emp.name], f"{emp.name}_min_full_time"
                    prob += total_hours <= 50 * y[emp.name], f"{emp.name}_max_full_time"
                    constraint_count += 2
                    print(f"  ✓ {emp.name}: Full-time (30-50h/week)")
    
    # ------------------------------------------------------------------------
    # 4.2: Days per week constraints
    # ------------------------------------------------------------------------
    for emp in employees:
        for demand in emp.demands:
            if demand.category == 'schedule' and demand.priority == 'critical':
                if demand.constraint == 'four_days':
                    # Work max 4 days per week
                    days_worked = pulp.lpSum(
                        pulp.lpSum(x[emp.name][day][shift_name] for shift_name in daily_shifts[day].keys())
                        for day in DAYS_OF_WEEK
                        if day in daily_shifts and daily_shifts[day]
                    )
                    prob += days_worked <= 4, f"{emp.name}_max_four_days"
                    constraint_count += 1
                    print(f"  ✓ {emp.name}: Max 4 days/week")
                
                elif demand.constraint == 'five_days':
                    # Work max 5 days per week
                    days_worked = pulp.lpSum(
                        pulp.lpSum(x[emp.name][day][shift_name] for shift_name in daily_shifts[day].keys())
                        for day in DAYS_OF_WEEK
                        if day in daily_shifts and daily_shifts[day]
                    )
                    prob += days_worked <= 5, f"{emp.name}_max_five_days"
                    constraint_count += 1
                    print(f"  ✓ {emp.name}: Max 5 days/week")
    
    # ------------------------------------------------------------------------
    # 4.3: No morning/afternoon/evening/night constraints
    # ------------------------------------------------------------------------
    for emp in employees:
        blocked_shifts = {}  # shift_type → list of demand reasons
        
        for demand in emp.demands:
            if demand.category == 'schedule' and demand.priority == 'critical':
                if demand.constraint == 'no_morning':
                    blocked_shifts['morning'] = demand.constraint
                elif demand.constraint == 'no_afternoon':
                    blocked_shifts['afternoon'] = demand.constraint
                elif demand.constraint == 'no_evening':
                    blocked_shifts['afternoon'] = demand.constraint
                    blocked_shifts['night'] = demand.constraint
                elif demand.constraint == 'no_night':
                    blocked_shifts['night'] = demand.constraint
        
        # Apply blocks
        for day in DAYS_OF_WEEK:
            if day in daily_shifts and daily_shifts[day]:
                for shift_name, shift_info in daily_shifts[day].items():
                    shift_type = shift_info['type']
                    if shift_type in blocked_shifts:
                        prob += x[emp.name][day][shift_name] == 0, f"{emp.name}_{day}_{shift_name}_blocked"
                        constraint_count += 1
        
        if blocked_shifts:
            print(f"  ✓ {emp.name}: Blocked {list(blocked_shifts.keys())} shifts")
            
 
 
    # ------------------------------------------------------------------------
    # 4.3b: No cleaning constraint 
    # ------------------------------------------------------------------------           
            
    for emp in employees:
        blocked_shifts = {}
        
        for demand in emp.demands:
            if demand.category == 'schedule' and demand.priority == 'critical':
                if demand.constraint == 'no_cleaning':
                    blocked_shifts['night'] = 'no_cleaning'
                    
        
        for day in DAYS_OF_WEEK:
            if day in daily_shifts and daily_shifts[day]:
                for shift_name, shift_info in daily_shifts[day].items():
                    shift_type = shift_info['type']
                    if shift_type in blocked_shifts:
                        prob += x[emp.name][day][shift_name] == 0
                        constraint_count += 1 
        if blocked_shifts:
            print(f"  ✓ {emp.name}: Blocked {list(blocked_shifts.keys())} shifts")
                
    
    
    
    
    for emp in employees:
        for day in DAYS_OF_WEEK:
            if day in daily_shifts and daily_shifts[day]:
                turni_day = pulp.lpSum(
                    x[emp.name][day][shift_name]
                    for shift_name in daily_shifts[day].keys()
                )
                
                prob += turni_day <= 1, f"{emp.name}_{day}_one_shift_max"
                constraint_count += 1
    
    
    
    
    # ------------------------------------------------------------------------
    # 4.4: Free weekend constraint
    # ------------------------------------------------------------------------
    for emp in employees:
        for demand in emp.demands:
            if demand.category == 'schedule' and demand.constraint == 'free_weekend' and demand.priority == 'critical':
                # No work on Saturday or Sunday
                for weekend_day in ['Saturday', 'Sunday']:
                    if weekend_day in daily_shifts and daily_shifts[weekend_day]:
                        for shift_name in daily_shifts[weekend_day].keys():
                            prob += x[emp.name][weekend_day][shift_name] == 0, f"{emp.name}_{weekend_day}_{shift_name}_off"
                            constraint_count += 1
                print(f"  ✓ {emp.name}: Free weekends")
    
    # ------------------------------------------------------------------------
    # 4.5: Max simultaneous employees per shift
    # ------------------------------------------------------------------------
    for day in DAYS_OF_WEEK:
        if day in daily_shifts and daily_shifts[day]:
            for shift_name in daily_shifts[day].keys():
                # Sum of all employees working this shift <= max_simultaneous
                employees_in_shift = pulp.lpSum(
                    x[emp.name][day][shift_name] for emp in employees
                )
                prob += employees_in_shift <= max_simultaneous, f"max_employees_{day}_{shift_name}"
                constraint_count += 1
    
    print(f"  ✓ Max {max_simultaneous} employees per shift")
    
    # ------------------------------------------------------------------------
    # 4.6: Minimum coverage (at least 1 employee per open shift)
    # ------------------------------------------------------------------------
    for day in DAYS_OF_WEEK:
        if day in daily_shifts and daily_shifts[day]:
            for shift_name in daily_shifts[day].keys():
                # Sum of all employees working this shift >= 1
                employees_in_shift = pulp.lpSum(
                    x[emp.name][day][shift_name] for emp in employees
                )
                prob += employees_in_shift >= 1, f"min_coverage_{day}_{shift_name}"
                constraint_count += 1
    
    print(f"  ✓ Minimum 1 employee per shift (coverage)")

    # ------------------------------------------------------------------------
    # 4.7: Vincolo A - capacità funzionale (postazioni per ruolo)
    # Per ogni turno: dipendenti attivi di un ruolo <= postazioni di quel ruolo.
    # ------------------------------------------------------------------------
    role_stations = get_role_workstations(selected_furniture or [])

    emps_by_role = {}
    for emp in employees:
        emps_by_role.setdefault(emp.role, []).append(emp)

    for role, role_emps in emps_by_role.items():
        n_stations = len(role_stations.get(role, []))
        if n_stations == 0:
            continue  # ruolo senza postazioni (es. Security): nessun tetto da furniture
        role_key = role.replace(' ', '')
        for day in DAYS_OF_WEEK:
            if day in daily_shifts and daily_shifts[day]:
                for shift_name in daily_shifts[day].keys():
                    active_in_role = pulp.lpSum(
                        x[emp.name][day][shift_name] for emp in role_emps
                    )
                    prob += active_in_role <= n_stations, \
                        f"capacity_{role_key}_{day}_{shift_name}"
                    constraint_count += 1
    print(f"  ✓ Vincolo A: tetto postazioni per ruolo")

    # ------------------------------------------------------------------------
    # 4.8: Vincolo B - domanda variabile (fabbisogno per ruolo dal flusso clienti)
    # Per ogni (ruolo, turno): dipendenti attivi del ruolo >= fabbisogno dal picco.
    # ------------------------------------------------------------------------
    peak = compute_peak_customers(
        business_setup.business_name,
        business_setup.capacity_limit,
        daily_shifts,
    )
    role_demand = compute_role_demand(
        list(emps_by_role.keys()),
        peak,
        role_stations,
        cleaning_per_shift=cleaning_per_shift,
        headcount_per_shift=security_per_shift,
    )
    for (role, day, shift_name), need in role_demand.items():
        if need <= 0 or role not in emps_by_role:
            continue
        active_in_role = pulp.lpSum(
            x[emp.name][day][shift_name] for emp in emps_by_role[role]
        )
        prob += active_in_role >= need, \
            f"demand_{role.replace(' ', '')}_{day}_{shift_name}"
        constraint_count += 1
    print(f"  ✓ Vincolo B: fabbisogno per ruolo dal flusso clienti")

    # ------------------------------------------------------------------------
    # 4.9: Soddisfazione soft - richieste NON-critical nell'obiettivo
    # Le critical sono gia' vincoli hard; qui premiamo important/nice_to_have.
    # Solo richieste 'schedule' (le altre dipendono dal business, non dai turni).
    # ------------------------------------------------------------------------
    BIG_M = 60  # tetto ore/giorni settimanali plausibile (per i vincoli a due lati)
    satisfaction_terms = []  # accumulatore di points * s

    for emp in employees:
        hours_e = pulp.lpSum(
            info['hours'] * x[emp.name][day][sh]
            for day in DAYS_OF_WEEK if day in daily_shifts and daily_shifts[day]
            for sh, info in daily_shifts[day].items()
        )
        days_e = pulp.lpSum(
            x[emp.name][day][sh]
            for day in DAYS_OF_WEEK if day in daily_shifts and daily_shifts[day]
            for sh in daily_shifts[day]
        )

        for i, demand in enumerate(emp.demands):
            if demand.priority == 'critical' or demand.category != 'schedule':
                continue

            points = SATISFACTION_POINTS[demand.priority]
            tag = f"{emp.name}_{i}".replace(' ', '_')
            s = pulp.LpVariable(f"sat_{tag}", cat='Binary')
            prob += s <= y[emp.name], f"satlink_{tag}"
            constraint_count += 1

            c = demand.constraint
            if c in ('no_morning', 'no_afternoon', 'no_evening', 'no_night', 'no_cleaning', 'free_weekend'):
                forbidden = _forbidden_shift_sum(emp.name, c, x, daily_shifts)
                prob += s <= 1 - forbidden, f"satavoid_{tag}"
                constraint_count += 1
            elif c == 'part_time':
                prob += hours_e >= 10 * s, f"satptlo_{tag}"
                prob += hours_e <= 30 + BIG_M * (1 - s), f"satpthi_{tag}"
                constraint_count += 2
            elif c == 'full_time':
                prob += hours_e >= 30 * s, f"satftlo_{tag}"
                prob += hours_e <= 50 + BIG_M * (1 - s), f"satfthi_{tag}"
                constraint_count += 2
            elif c == 'four_days':
                prob += days_e <= 4 + BIG_M * (1 - s), f"sat4d_{tag}"
                constraint_count += 1
            elif c == 'five_days':
                prob += days_e <= 5 + BIG_M * (1 - s), f"sat5d_{tag}"
                constraint_count += 1
            else:
                continue  # tipo schedule non gestito: nessun premio

            satisfaction_terms.append(points * s)

    sat_total = pulp.lpSum(satisfaction_terms)
    print(f"  ✓ Soddisfazione soft: {len(satisfaction_terms)} richieste non-critical pesate")

    # Obiettivo finale: alpha*costo - beta*soddisfazione + spareggio su y.
    prob += (
        alpha * total_cost_expr
        + 0.01 * pulp.lpSum(y[emp.name] for emp in employees)
        - beta * sat_total
    ), "objective"
    print(f"  Objective set: alpha*cost - beta*satisfaction (alpha={alpha}, beta={beta})")

    print(f"✓ Added {constraint_count} total constraints")
    
    
    
    
    
    # ========================================================================
    # STEP 5: Solve and extract results
    # ========================================================================
    print("\n[Step 5] Solving optimization problem...")
    
    import time
    start_time = time.time()
    
    # Solve the problem
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))  # msg=0 = silent mode
    
    solver_time = time.time() - start_time
    
    # Check if solution is optimal
    if status == pulp.LpStatusOptimal:
        print(f"✓ Optimal solution found in {solver_time:.2f}s")
        success = True
        status_msg = "Optimal"
    else:
        print(f"✗ Optimization failed: {pulp.LpStatus[status]}")
        success = False
        status_msg = pulp.LpStatus[status]
        
        return OptimizationResult(
            success=False,
            status=status_msg,
            total_cost=0.0,
            total_satisfaction=0.0,
            schedule={},
            daily_shifts=daily_shifts,  
            unmet_demands=[],
            solver_time=solver_time
        )
    
    # ------------------------------------------------------------------------
    # Extract schedule from solution
    # ------------------------------------------------------------------------
    print("\n[Extracting schedule...]")
    
    schedule = {}  # employee_name → day → [shift_names]
    
    for emp in employees:
        schedule[emp.name] = {}
        
        for day in DAYS_OF_WEEK:
            schedule[emp.name][day] = []
            
            if day in daily_shifts and daily_shifts[day]:
                for shift_name in daily_shifts[day].keys():
                    # Check if variable is 1 (employee works this shift)
                    if x[emp.name][day][shift_name].varValue == 1:
                        schedule[emp.name][day].append(shift_name)
    
    # Print schedule
    for emp_name, emp_schedule in schedule.items():
        print(f"\n  {emp_name}:")
        for day, shifts in emp_schedule.items():
            if shifts:
                shift_details = []
                for shift_name in shifts:
                    shift_info = daily_shifts[day][shift_name]
                    shift_details.append(f"{shift_name} ({shift_info['start']}-{shift_info['end']})")
                print(f"    {day}: {', '.join(shift_details)}")
    
    # ------------------------------------------------------------------------
    # Calculate actual costs and hours
    # ------------------------------------------------------------------------
    actual_cost = 0.0
    employee_hours = {}
    
    for emp in employees:
        total_hours_worked = 0
        
        for day in DAYS_OF_WEEK:
            if day in daily_shifts and daily_shifts[day]:
                for shift_name in daily_shifts[day].keys():
                    if x[emp.name][day][shift_name].varValue == 1:
                        shift_hours = daily_shifts[day][shift_name]['hours']
                        total_hours_worked += shift_hours
                        actual_cost += emp.hourly_wage * shift_hours
        
        employee_hours[emp.name] = total_hours_worked
    
    print(f"\n[Cost breakdown:]")
    for emp in employees:
        hours = employee_hours[emp.name]
        cost = emp.hourly_wage * hours
        print(f"  {emp.name}: {hours}h @ ${emp.hourly_wage}/h = ${cost:.2f}")
    
    print(f"\n  Total weekly cost: ${actual_cost:.2f}")
    
    
    
    # Helper Function: Calcola le ore totali lavorate
    
    def calculate_total_hours(emp_schedule, daily_shift):
        total = 0
        
        for day, shifts in emp_schedule.items():
            for shift_name in shifts:
                total += daily_shift[day][shift_name]['hours']
        return total
    
    
    # Helper per contare giorni lavorativi
    
    def count_working_days(emp_schedule):
        return sum(1 for day, shift in emp_schedule.items() if len(shift) > 0)
    
    
    # Helper controllo turni 
    
    def has_shift_type(emp_schedule, daily_shift, shift_type):
        for day, shift in emp_schedule.items():
            for shift_name in shift:
                if daily_shift[day][shift_name]['type'] == shift_type:
                    return True
        return False
    
    
    
    
    
    
    total_satisfaction = 0
    max_possible_satisfaction = 0
    
    for emp in employees:
        emp_schedule = schedule[emp.name]
        total_hours = calculate_total_hours(emp_schedule, daily_shifts)
        giorni_lavorativi = count_working_days(emp_schedule)

        # 5a: la soddisfazione conta solo per i dipendenti effettivamente in turno.
        # Un dipendente scartato (y=0, 0 turni) non entra ne' al numeratore ne' al denominatore.
        if giorni_lavorativi == 0:
            continue
        
        
        for demand in emp.demands:
            if demand.category != 'schedule':
                continue  # non valutabile senza config business (insurance/env/equipment)
            points = SATISFACTION_POINTS[demand.priority]
            max_possible_satisfaction += points
            
            is_satisfied = False
            
            
            if demand.constraint == 'part_time':
                if 10 <= total_hours <= 30:
                    is_satisfied = True
                    

                    
            elif demand.constraint == 'full_time':
                if 30 <= total_hours <= 50:
                    is_satisfied = True
                    

            
            elif demand.constraint == 'four_days':
                if giorni_lavorativi <= 4:
                    is_satisfied = True
     
                    

            elif demand.constraint == 'five_days':
                if giorni_lavorativi <= 5:
                    is_satisfied = True
                    

                
                    
            elif demand.constraint == 'free_weekend':
                if not schedule[emp.name]['Saturday'] and not schedule[emp.name]['Sunday']:
                    is_satisfied = True

            
            elif demand.constraint == 'no_morning':
                has_morning = has_shift_type(emp_schedule, daily_shifts, 'morning')
                
                if not has_morning:
                    is_satisfied = True

    
            elif demand.constraint == 'no_afternoon':
                if not has_shift_type(emp_schedule, daily_shifts, 'afternoon'):
                    is_satisfied = True
                    


            elif demand.constraint == 'no_night':
                if not has_shift_type(emp_schedule, daily_shifts, 'night'):
                    is_satisfied = True
                    

                
            elif demand.constraint == 'no_evening':
                has_afternoon = has_shift_type(emp_schedule, daily_shifts, 'afternoon')
                has_night = has_shift_type(emp_schedule, daily_shifts, 'night')
                
                if not has_afternoon and not has_night:
                    is_satisfied = True
                               
            

            elif demand.constraint == 'no_cleaning':
                if not has_shift_type(emp_schedule, daily_shifts, 'night'):
                    is_satisfied = True
                    
            
            if is_satisfied:
                total_satisfaction += points
    
    
    if max_possible_satisfaction > 0:
        satisfaction_pct = total_satisfaction / max_possible_satisfaction * 100
        sat_str = f"{satisfaction_pct:.1f}%"
    else:
        # Nessuna richiesta tra i dipendenti attivi: niente da soddisfare -> N/A
        satisfaction_pct = None
        sat_str = "N/A"
    print(f"  Total satisfaction: {sat_str} ({total_satisfaction}/{max_possible_satisfaction} points)")
            
    
    
    
    # ------------------------------------------------------------------------
    # Return results
    # ------------------------------------------------------------------------
    return OptimizationResult(
        success=success,
        status=status_msg,
        total_cost=actual_cost,
        total_satisfaction=satisfaction_pct,
        schedule=schedule,
        daily_shifts=daily_shifts,
        unmet_demands=[],
        solver_time=solver_time
    )