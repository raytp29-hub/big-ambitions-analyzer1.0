"""
Schedule Optimization Engine using PuLP
Minimizes wage costs while maximizing employee satisfaction
"""


import math
import uuid
from operator import lshift
from collections import defaultdict
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
    # Shift type based on START time (mod 24 per i turni overnight: 24->0, 25->1...)
    h = start_hour % 24
    if h < 12:
        return 'morning'
    elif h < 18:
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

    # Normalizza l'identita': i dipendenti creati prima dell'introduzione di
    # `uid` (o rimasti in session_state da una vecchia classe) potrebbero non
    # averlo. Glielo assegniamo qui, cosi' il solver ha sempre una chiave univoca.
    for _emp in employees:
        if getattr(_emp, 'uid', None) is None:
            _emp.uid = uuid.uuid4().hex

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
        x[emp.uid] = {}
        
        for day in DAYS_OF_WEEK:
            x[emp.uid][day] = {}
            
            if day in daily_shifts and daily_shifts[day]:
                for shift_name in daily_shifts[day].keys():
                    # Create binary variable
                    var_name = f"x_{emp.uid}_{day}_{shift_name}"
                    x[emp.uid][day][shift_name] = pulp.LpVariable(
                        var_name,
                        cat='Binary'
                    )
    total_vars = sum(
        len(x[emp.uid][day])
        for emp in employees
        for day in DAYS_OF_WEEK
        if day in x[emp.uid]
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
        y[emp.uid] = pulp.LpVariable(f"y_{emp.uid}", cat='Binary')

    # Collegamento x <= y: se y=0 il dipendente non può lavorare nessun turno
    for emp in employees:
        for day in DAYS_OF_WEEK:
            if day in daily_shifts and daily_shifts[day]:
                for shift_name in daily_shifts[day].keys():
                    prob += x[emp.uid][day][shift_name] <= y[emp.uid], \
                        f"link_{emp.uid}_{day}_{shift_name}"

    # Satisfaction points by priority (usati nello Step 5 per il punteggio)
    SATISFACTION_POINTS = {
        'critical': 100,
        'important': 80,
        'nice_to_have': 50
    }

    # Obiettivo: minimizza il costo salariale settimanale.
    # + penalità minima su Σy: a parità di costo, preferisci meno dipendenti attivi.
    total_cost_expr = pulp.lpSum(
        emp.hourly_wage * shift_info['hours'] * x[emp.uid][day][shift_name]
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
            shift_info['hours'] * x[emp.uid][day][shift_name]
            for day in DAYS_OF_WEEK
            if day in daily_shifts and daily_shifts[day]
            for shift_name, shift_info in daily_shifts[day].items()
        )
        
        # Check for part-time/full-time demands
        for demand in emp.demands:
            if demand.category == 'schedule':
                if demand.constraint == 'part_time' and demand.priority == 'critical':
                    # Part-time: 10-30 hours/week (condizionato su y: se y=0 nessun minimo)
                    prob += total_hours >= 10 * y[emp.uid], f"{emp.uid}_min_part_time"
                    prob += total_hours <= 30 * y[emp.uid], f"{emp.uid}_max_part_time"
                    constraint_count += 2
                    print(f"  ✓ {emp.name}: Part-time (10-30h/week)")

                elif demand.constraint == 'full_time' and demand.priority == 'critical':
                    # Full-time: 30-50 hours/week (condizionato su y)
                    prob += total_hours >= 30 * y[emp.uid], f"{emp.uid}_min_full_time"
                    prob += total_hours <= 50 * y[emp.uid], f"{emp.uid}_max_full_time"
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
                        pulp.lpSum(x[emp.uid][day][shift_name] for shift_name in daily_shifts[day].keys())
                        for day in DAYS_OF_WEEK
                        if day in daily_shifts and daily_shifts[day]
                    )
                    prob += days_worked <= 4, f"{emp.uid}_max_four_days"
                    constraint_count += 1
                    print(f"  ✓ {emp.name}: Max 4 days/week")
                
                elif demand.constraint == 'five_days':
                    # Work max 5 days per week
                    days_worked = pulp.lpSum(
                        pulp.lpSum(x[emp.uid][day][shift_name] for shift_name in daily_shifts[day].keys())
                        for day in DAYS_OF_WEEK
                        if day in daily_shifts and daily_shifts[day]
                    )
                    prob += days_worked <= 5, f"{emp.uid}_max_five_days"
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
                        prob += x[emp.uid][day][shift_name] == 0, f"{emp.uid}_{day}_{shift_name}_blocked"
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
                        prob += x[emp.uid][day][shift_name] == 0
                        constraint_count += 1 
        if blocked_shifts:
            print(f"  ✓ {emp.name}: Blocked {list(blocked_shifts.keys())} shifts")
                
    
    
    
    
    for emp in employees:
        for day in DAYS_OF_WEEK:
            if day in daily_shifts and daily_shifts[day]:
                turni_day = pulp.lpSum(
                    x[emp.uid][day][shift_name]
                    for shift_name in daily_shifts[day].keys()
                )
                
                prob += turni_day <= 1, f"{emp.uid}_{day}_one_shift_max"
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
                            prob += x[emp.uid][weekend_day][shift_name] == 0, f"{emp.uid}_{weekend_day}_{shift_name}_off"
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
                    x[emp.uid][day][shift_name] for emp in employees
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
                    x[emp.uid][day][shift_name] for emp in employees
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
                        x[emp.uid][day][shift_name] for emp in role_emps
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
    role_headcount = {role: len(emps) for role, emps in emps_by_role.items()}
    role_demand = compute_role_demand(
        list(emps_by_role.keys()),
        peak,
        role_stations,
        cleaning_per_shift=cleaning_per_shift,
        headcount_per_shift=security_per_shift,
        role_headcount=role_headcount,
    )
    for (role, day, shift_name), need in role_demand.items():
        if need <= 0 or role not in emps_by_role:
            continue
        active_in_role = pulp.lpSum(
            x[emp.uid][day][shift_name] for emp in emps_by_role[role]
        )
        prob += active_in_role >= need, \
            f"demand_{role.replace(' ', '')}_{day}_{shift_name}"
        constraint_count += 1
    print(f"  ✓ Vincolo B: fabbisogno per ruolo dal flusso clienti [v4 water-fill]")

    # --- Diagnostica pre-solve: individua i colli di bottiglia strutturali -----
    # Conferma che gira il codice nuovo e segnala perche' sarebbe infeasible.
    print("  [Diagnostica Vincolo B - fabbisogno vs organico/postazioni]")
    for role in emps_by_role:
        hc = role_headcount.get(role, 0)
        n_st = len(role_stations.get(role, []))
        per_day = defaultdict(int)
        per_shift_max = 0
        for (r, day, sh), need in role_demand.items():
            if r != role:
                continue
            per_day[day] += need
            per_shift_max = max(per_shift_max, need)
            if n_st and need > n_st:
                print(f"    ⚠ {role} {day}/{sh}: need {need} > postazioni {n_st} (Vincolo A blocca)")
        worst_day = max(per_day.values()) if per_day else 0
        flag = "OK" if worst_day <= hc else f"⚠ supera organico {hc}"
        print(f"    {role}: organico={hc}, postazioni={n_st}, "
              f"max need/turno={per_shift_max}, max need/giorno={worst_day} -> {flag}")
    # Carico totale richiesto per turno vs max_simultaneous
    demand_per_shift = defaultdict(int)
    for (r, day, sh), need in role_demand.items():
        demand_per_shift[(day, sh)] += need
    for (day, sh), tot in demand_per_shift.items():
        if tot > max_simultaneous:
            print(f"    ⚠ {day}/{sh}: somma fabbisogni ruoli {tot} > max_simultaneous {max_simultaneous}")

    # ------------------------------------------------------------------------
    # 4.9: Soddisfazione soft - richieste NON-critical nell'obiettivo
    # Le critical sono gia' vincoli hard; qui premiamo important/nice_to_have.
    # Solo richieste 'schedule' (le altre dipendono dal business, non dai turni).
    # ------------------------------------------------------------------------
    BIG_M = 60  # tetto ore/giorni settimanali plausibile (per i vincoli a due lati)
    satisfaction_terms = []  # accumulatore di points * s

    for emp in employees:
        hours_e = pulp.lpSum(
            info['hours'] * x[emp.uid][day][sh]
            for day in DAYS_OF_WEEK if day in daily_shifts and daily_shifts[day]
            for sh, info in daily_shifts[day].items()
        )
        days_e = pulp.lpSum(
            x[emp.uid][day][sh]
            for day in DAYS_OF_WEEK if day in daily_shifts and daily_shifts[day]
            for sh in daily_shifts[day]
        )

        for i, demand in enumerate(emp.demands):
            if demand.priority == 'critical' or demand.category != 'schedule':
                continue

            points = SATISFACTION_POINTS[demand.priority]
            tag = f"{emp.uid}_{i}".replace(' ', '_')
            s = pulp.LpVariable(f"sat_{tag}", cat='Binary')
            prob += s <= y[emp.uid], f"satlink_{tag}"
            constraint_count += 1

            c = demand.constraint
            if c in ('no_morning', 'no_afternoon', 'no_evening', 'no_night', 'no_cleaning', 'free_weekend'):
                forbidden = _forbidden_shift_sum(emp.uid, c, x, daily_shifts)
                # Soft corretto: s=1 => forbidden=0 (richiesta soddisfatta);
                # s=0 => nessun limite (BIG_M la disattiva). NON usare
                # "s <= 1 - forbidden": forzerebbe forbidden<=1 come vincolo hard.
                prob += forbidden <= BIG_M * (1 - s), f"satavoid_{tag}"
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
    print(f"  ✓ Soddisfazione soft: {len(satisfaction_terms)} richieste non-critical pesate [v3 soft-avoid-fix]")

    # Obiettivo finale: alpha*costo - beta*soddisfazione + spareggio su y.
    prob += (
        alpha * total_cost_expr
        + 0.01 * pulp.lpSum(y[emp.uid] for emp in employees)
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
        schedule[emp.uid] = {}
        
        for day in DAYS_OF_WEEK:
            schedule[emp.uid][day] = []
            
            if day in daily_shifts and daily_shifts[day]:
                for shift_name in daily_shifts[day].keys():
                    # Check if variable is 1 (employee works this shift)
                    if x[emp.uid][day][shift_name].varValue == 1:
                        schedule[emp.uid][day].append(shift_name)
    
    # Mappa uid -> nome (i print devono restare leggibili)
    name_of = {emp.uid: emp.name for emp in employees}

    # Print schedule
    for emp_uid, emp_schedule in schedule.items():
        print(f"\n  {name_of.get(emp_uid, emp_uid)}:")
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
                    if x[emp.uid][day][shift_name].varValue == 1:
                        shift_hours = daily_shifts[day][shift_name]['hours']
                        total_hours_worked += shift_hours
                        actual_cost += emp.hourly_wage * shift_hours
        
        employee_hours[emp.uid] = total_hours_worked
    
    print(f"\n[Cost breakdown:]")
    for emp in employees:
        hours = employee_hours[emp.uid]
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
        emp_schedule = schedule[emp.uid]
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
                if not schedule[emp.uid]['Saturday'] and not schedule[emp.uid]['Sunday']:
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


# ============================================================================
# NUOVO MODELLO: TURNI A LUNGHEZZA VARIABILE (domanda oraria)
# ============================================================================

def optimize_schedule_variable(
    business_setup,
    employees,
    weekly_schedule,
    max_simultaneous,
    selected_furniture=None,
    cleaning_per_shift: int = 1,
    security_per_shift: int = 1,
    alpha: float = 1.0,
    beta: float = 0.5,
    max_shift_len: int = 8,
    customers_per_guard: int = 0,
) -> OptimizationResult:
    """Solver a TURNI VARIABILI.

    Ogni dipendente/giorno sceglie UNA finestra contigua (durata tra la durata
    del picco clienti e `max_shift_len`). La domanda e' calcolata per ORA dalla
    curva di gioco; il monte ore settimanale e' un vincolo HARD per contratto
    (full 30-50, part 10-30, altrimenti <=50). Floor di 1 CS per ogni ora aperta
    (niente buchi di vendita).
    """
    import time
    from analysis.schedule_constraints import (
        get_role_workstations, hours_range, peak_duration,
        generate_shift_templates, compute_hourly_role_demand,
    )

    # uid safety (oggetti vecchi in session_state)
    for _e in employees:
        if getattr(_e, 'uid', None) is None:
            _e.uid = uuid.uuid4().hex

    print("=" * 60)
    print("SCHEDULE OPTIMIZATION — turni variabili [v6: security-picco + soddisfazione]")
    print("=" * 60)
    print(f"Employees: {len(employees)} | capacity: {business_setup.capacity_limit}/h "
          f"| max simultaneous: {max_simultaneous}")

    # --- ore di apertura per giorno ---
    open_hours = {}
    for d in weekly_schedule:
        open_hours[d.day_name] = hours_range(d.start_hour, d.end_hour) if d.is_open else []
    open_days = [day for day in DAYS_OF_WEEK if open_hours.get(day)]

    # --- template di turno per giorno (min = durata picco, max = max_shift_len) ---
    templates = {}
    for day in open_days:
        hrs = open_hours[day]
        start, end = hrs[0], hrs[-1] + 1
        min_len = peak_duration(business_setup.business_name, hrs)
        templates[day] = generate_shift_templates(start, end, min_len, max_shift_len)
        print(f"  {day}: {start % 24}-{end % 24} ({len(hrs)}h) | min turno {min_len}h "
              f"| {len(templates[day])} template")

    role_stations = get_role_workstations(selected_furniture or [])
    emps_by_role = {}
    for e in employees:
        emps_by_role.setdefault(e.role, []).append(e)
    role_headcount = {r: len(es) for r, es in emps_by_role.items()}

    # banda oraria contrattuale per dipendente (hard) e capacita' erogabile per ruolo
    def band(e):
        cons = {d.constraint for d in e.demands if d.category == 'schedule'}
        if 'full_time' in cons:
            return (30, 50)
        if 'part_time' in cons:
            return (10, 30)
        return (0, 50)

    def emp_max_hours(e):
        return min(band(e)[1], len(open_days) * max_shift_len, 50)

    role_capacity = {
        role: sum(emp_max_hours(e) for e in es) for role, es in emps_by_role.items()
    }

    demand, demand_info, econ = compute_hourly_role_demand(
        business_setup.business_name,
        business_setup.capacity_limit,
        {day: open_hours[day] for day in open_days},
        role_stations,
        role_headcount,
        cleaning_per_shift=cleaning_per_shift,
        security_per_shift=security_per_shift,
        max_shift_len=max_shift_len,
        role_capacity=role_capacity,
        customers_per_guard=customers_per_guard,
    )

    prob = pulp.LpProblem("Schedule_Variable", pulp.LpMinimize)

    # --- variabili: x[uid][day][ti] scelta del template, y[uid] attivo ---
    x = {}
    for e in employees:
        x[e.uid] = {}
        for day in open_days:
            x[e.uid][day] = {
                ti: pulp.LpVariable(f"x_{e.uid}_{day}_{ti}", cat='Binary')
                for ti in range(len(templates[day]))
            }
    y = {e.uid: pulp.LpVariable(f"y_{e.uid}", cat='Binary') for e in employees}

    # un turno/giorno + link a y
    for e in employees:
        for day in open_days:
            prob += pulp.lpSum(x[e.uid][day].values()) <= y[e.uid], f"one_{e.uid}_{day}"

    def covering(day, h):
        return [ti for ti, (s, en) in enumerate(templates[day]) if s <= h < en]

    # copertura per ORA con SLACK + Vincolo A + max sim. La copertura non e' hard:
    # se l'organico non basta si lascia scoperto (slack>0) invece di Infeasible.
    # SLACK ECONOMICO per il ruolo di vendita: il floor di 1 (no buchi) ha penalita'
    # ALTA, mentre il CS EXTRA sopra il floor e' penalizzato col valore economico
    # (profitto/cliente × clienti serviti) -> lo aggiunge solo se rende piu' del salario.
    BIG_PEN = 10000.0       # floor vendita / vendita senza profitto noto: copri quasi sempre
    PRESENCE_PEN = 200.0    # presenza (security/cleaning): copri se l'organico lo consente
    slack_report = []       # (role, var) per il report scopertura
    slack_pen_terms = []    # termini di penalita' per l'obiettivo
    for day in open_days:
        for h in open_hours[day]:
            cov = covering(day, h)
            tag_h = f"{day}_{h}"
            prob += pulp.lpSum(
                x[e.uid][day][ti] for e in employees for ti in cov
            ) <= max_simultaneous, f"maxsim_{tag_h}"
            for role, es in emps_by_role.items():
                rk = role.replace(' ', '')
                present = pulp.lpSum(x[e.uid][day][ti] for e in es for ti in cov)
                need = demand.get((role, day, h), 0)
                n_st = len(role_stations.get(role, []))
                if need > 0:
                    selling = demand_info.get(role, {}).get('selling', False)
                    ev = econ.get((role, day, h), 0.0)
                    if selling and ev > 0:
                        # floor di 1 protetto (penalita' alta) -> gap REALE
                        s_floor = pulp.LpVariable(f"slkF_{rk}_{tag_h}", lowBound=0)
                        prob += present + s_floor >= 1, f"covF_{rk}_{tag_h}"
                        slack_pen_terms.append(BIG_PEN * s_floor)
                        slack_report.append((role, s_floor, 'real'))
                        extra = need - 1
                        if extra > 0:
                            # CS extra: penalita' = valore economico -> gap OPZIONALE (margine)
                            s_extra = pulp.LpVariable(
                                f"slkE_{rk}_{tag_h}", lowBound=0, upBound=extra
                            )
                            prob += present + s_floor + s_extra >= need, f"covE_{rk}_{tag_h}"
                            slack_pen_terms.append(ev * s_extra)
                            slack_report.append((role, s_extra, 'optional'))
                    else:
                        # presenza (o vendita senza profitto noto): slack unico -> gap REALE
                        pen = BIG_PEN if selling else PRESENCE_PEN
                        u = pulp.LpVariable(f"slk_{rk}_{tag_h}", lowBound=0)
                        prob += present + u >= need, f"cov_{rk}_{tag_h}"
                        slack_pen_terms.append(pen * u)
                        slack_report.append((role, u, 'real'))
                if n_st > 0:
                    prob += present <= n_st, f"capA_{rk}_{tag_h}"

    # --- monte ore HARD per dipendente (band() definita sopra) ---
    H = {}
    for e in employees:
        H[e.uid] = pulp.lpSum(
            (en - s) * x[e.uid][day][ti]
            for day in open_days
            for ti, (s, en) in enumerate(templates[day])
        )
        lo, hi = band(e)
        prob += H[e.uid] <= hi * y[e.uid], f"hmax_{e.uid}"
        if lo > 0:
            prob += H[e.uid] >= lo * y[e.uid], f"hmin_{e.uid}"

    # --- soddisfazione SOFT (richieste non-critical 'schedule') nell'obiettivo ---
    # part/full sono gia' HARD (banda); qui premiamo avoid (no_morning...) e days.
    # I pesi sono in SCALA DOLLARI (non "punti"): un Important pesa 800 cosi' che,
    # anche dopo il fattore beta, violarlo costi piu' del risparmio salariale di un
    # tipico turno -> "quasi sempre rispettato" ma ancora cedibile se il risparmio
    # e' enorme (es. evitare di attivare un dipendente intero). nice_to_have resta
    # debole. Il punteggio % di soddisfazione (report) usa SATP, qui invariato.
    SOFT_PEN = {'important': 800, 'nice_to_have': 80}
    BIG_M = 60
    tmpl_type = {
        day: [classify_shift_type(s, en) for (s, en) in templates[day]]
        for day in open_days
    }
    AVOID_TYPES = {
        'no_morning': {'morning'},
        'no_afternoon': {'afternoon'},
        'no_evening': {'afternoon', 'night'},
        'no_night': {'night'},
        'no_cleaning': {'night'},
    }

    # --- vincoli HARD per le richieste 'schedule' CRITICAL ---------------------
    # full_time/part_time sono gia' hard via band(). Tutto il resto (free_weekend,
    # four/five_days, no_morning/...) nel vecchio optimize_schedule era hard ma in
    # questo solver a turni variabili NON era enforced affatto (il loop soft fa
    # `continue` sui critical). Lo aggiungiamo qui: un Critical e' inviolabile.
    n_hard_crit = 0
    for e in employees:
        days_e_hard = pulp.lpSum(
            x[e.uid][day][ti]
            for day in open_days for ti in range(len(templates[day]))
        )
        for dm in e.demands:
            if dm.category != 'schedule' or dm.priority != 'critical':
                continue
            c = dm.constraint
            if c in ('full_time', 'part_time'):
                continue  # gia' garantito dalla banda hard
            if c in AVOID_TYPES:
                for day in open_days:
                    for ti in range(len(templates[day])):
                        if tmpl_type[day][ti] in AVOID_TYPES[c]:
                            prob += x[e.uid][day][ti] == 0, \
                                f"hardavoid_{e.uid}_{c}_{day}_{ti}"
                            n_hard_crit += 1
            elif c == 'free_weekend':
                for day in ('Saturday', 'Sunday'):
                    if day in open_days:
                        for ti in range(len(templates[day])):
                            prob += x[e.uid][day][ti] == 0, \
                                f"hardwknd_{e.uid}_{day}_{ti}"
                            n_hard_crit += 1
            elif c == 'four_days':
                prob += days_e_hard <= 4, f"hard4d_{e.uid}"
                n_hard_crit += 1
            elif c == 'five_days':
                prob += days_e_hard <= 5, f"hard5d_{e.uid}"
                n_hard_crit += 1
    if n_hard_crit:
        print(f"  ✓ Vincoli HARD critical (no-weekend/giorni/turni): {n_hard_crit}")

    sat_terms = []
    for e in employees:
        days_e = pulp.lpSum(
            x[e.uid][day][ti]
            for day in open_days for ti in range(len(templates[day]))
        )
        for i, dm in enumerate(e.demands):
            if dm.category != 'schedule' or dm.priority == 'critical':
                continue
            if dm.constraint in ('full_time', 'part_time'):
                continue  # gia' garantite dalla banda hard
            pts = SOFT_PEN.get(dm.priority, 0)
            tag = f"{e.uid}_{i}"
            sv = pulp.LpVariable(f"sat_{tag}", cat='Binary')
            prob += sv <= y[e.uid], f"satlink_{tag}"
            c = dm.constraint
            if c in AVOID_TYPES:
                forbidden = pulp.lpSum(
                    x[e.uid][day][ti]
                    for day in open_days
                    for ti in range(len(templates[day]))
                    if tmpl_type[day][ti] in AVOID_TYPES[c]
                )
                prob += forbidden <= BIG_M * (1 - sv), f"satavoid_{tag}"
            elif c == 'free_weekend':
                forbidden = pulp.lpSum(
                    x[e.uid][day][ti]
                    for day in ('Saturday', 'Sunday') if day in open_days
                    for ti in range(len(templates[day]))
                )
                prob += forbidden <= BIG_M * (1 - sv), f"satwknd_{tag}"
            elif c == 'four_days':
                prob += days_e <= 4 + BIG_M * (1 - sv), f"sat4_{tag}"
            elif c == 'five_days':
                prob += days_e <= 5 + BIG_M * (1 - sv), f"sat5_{tag}"
            else:
                continue
            sat_terms.append(pts * sv)

    # --- obiettivo: PRIMA copri (penalita' alta su scopertura), poi minimizza costo,
    #     a parita' premia la soddisfazione (beta) ---
    cost_expr = pulp.lpSum(
        e.hourly_wage * (en - s) * x[e.uid][day][ti]
        for e in employees
        for day in open_days
        for ti, (s, en) in enumerate(templates[day])
    )
    prob += (
        alpha * cost_expr
        + 0.01 * pulp.lpSum(y.values())
        + pulp.lpSum(slack_pen_terms)
        - beta * pulp.lpSum(sat_terms)
    ), "objective"

    # --- diagnostica pre-solve: domanda ideale vs capata all'organico ---
    _ppc = next(iter(demand_info.values()), {}).get('ppc', 0.0)
    print(f"  [Profitto/cliente stimato: ${_ppc:.2f} -> slack CS extra valutato economicamente]"
          if _ppc > 0 else "  [Profitto/cliente non disponibile -> slack a penalita' piatta]")
    print("  [Diagnostica copertura oraria vs organico]")
    for role, hc in role_headcount.items():
        n_st = len(role_stations.get(role, []))
        di = demand_info.get(role, {})
        tag = "vendita" if di.get('selling') else "presenza"
        ideal = di.get('ideal', 0)
        assigned = di.get('assigned', 0)
        cap_hours = di.get('cap', 0)
        unc = di.get('uncovered', 0)
        note = "piena" if ideal <= cap_hours else f"CAPATA a {cap_hours}h"
        warn = f" | ⚠ {unc} ore senza copertura" if unc else ""
        print(f"    {role} ({tag}): organico={hc} postazioni={n_st} | "
              f"ideale={ideal}h assegnate={assigned}h (cap {cap_hours}h) -> {note}{warn}")
    print("  [Banda ore per dipendente]")
    for e in employees:
        lo, hi = band(e)
        print(f"    {e.name} [{e.role}]: banda {lo}-{hi}h, max erogabili {emp_max_hours(e)}h")

    # --- solve ---
    # timeLimit OBBLIGATORIO: senza, CBC puo' restare nel branch-and-bound quasi
    # all'infinito sui modelli piu' duri (es. security continua + scaling = molti
    # vincoli di copertura + slack). Col limite, CBC ritorna la MIGLIORE soluzione
    # intera trovata (incumbent) anche se non prova l'ottimalita'.
    SOLVE_TIME_LIMIT = 45  # secondi
    t0 = time.time()
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=SOLVE_TIME_LIMIT))
    solver_time = time.time() - t0

    # Accetta anche un incumbent feasible non provato ottimo (timeout): le variabili
    # hanno comunque un valore. Scarta solo Infeasible/Unbounded o assenza di soluzione.
    has_incumbent = any(v.varValue is not None for v in y.values())
    proven_optimal = (status == pulp.LpStatusOptimal)
    usable = proven_optimal or (
        status not in (pulp.LpStatusInfeasible, pulp.LpStatusUnbounded)
        and has_incumbent
    )
    if not usable:
        print(f"✗ {pulp.LpStatus[status]}")
        return OptimizationResult(
            success=False, status=pulp.LpStatus[status], total_cost=0.0,
            total_satisfaction=None, schedule={},
            daily_shifts={day: {} for day in DAYS_OF_WEEK},
            unmet_demands=[], solver_time=solver_time,
        )
    if proven_optimal:
        print(f"✓ Optimal in {solver_time:.2f}s")
    else:
        print(f"⏱ Time limit ({SOLVE_TIME_LIMIT}s): uso la migliore soluzione trovata "
              f"(non provata ottima) [{pulp.LpStatus[status]}]")

    # --- report scopertura: gap REALI (servono addetti) vs OPZIONALI (margine) ---
    real_gaps, opt_gaps = {}, {}
    for role, u, kind in slack_report:
        v = u.varValue or 0
        if v > 1e-6:
            (opt_gaps if kind == 'optional' else real_gaps)[role] = \
                (opt_gaps if kind == 'optional' else real_gaps).get(role, 0.0) + v

    per_emp_cap = min(50, len(open_days) * max_shift_len) or 1
    coverage_report = {}
    for role in set(real_gaps) | set(opt_gaps):
        r = real_gaps.get(role, 0.0)
        o = opt_gaps.get(role, 0.0)
        coverage_report[role] = {
            'real': r,
            'optional': o,
            'suggest': int(math.ceil(r / per_emp_cap)) if r > 1e-6 else 0,
        }

    if real_gaps:
        print("  ⚠ Gap REALI (servono addetti):")
        for role, v in sorted(real_gaps.items()):
            print(f"      {role}: {v:.0f}h scoperte -> ~+{coverage_report[role]['suggest']} addetti")
    if opt_gaps:
        print("  ℹ Copertura extra non coperta (margine, opzionale):")
        for role, v in sorted(opt_gaps.items()):
            print(f"      {role}: {v:.0f}h -> potresti servire piu' clienti con piu' addetti")
    if not real_gaps and not opt_gaps:
        print("  Copertura piena: nessuna ora scoperta")

    # --- estrazione: daily_shifts + schedule dalle finestre scelte ---
    daily_shifts = {day: {} for day in DAYS_OF_WEEK}
    schedule = {e.uid: {day: [] for day in DAYS_OF_WEEK} for e in employees}

    for e in employees:
        for day in open_days:
            for ti, (s, en) in enumerate(templates[day]):
                if x[e.uid][day][ti].varValue == 1:
                    sid = f"{s:02d}-{en:02d}"
                    daily_shifts[day][sid] = {
                        'start': s, 'end': en, 'hours': en - s,
                        'type': classify_shift_type(s, en),
                    }
                    schedule[e.uid][day].append(sid)

    # --- costo e ore ---
    actual_cost = 0.0
    print("\n[Schedule]")
    for e in employees:
        worked = []
        h_tot = 0
        for day in open_days:
            for sid in schedule[e.uid][day]:
                info = daily_shifts[day][sid]
                h_tot += info['hours']
                worked.append(f"{day[:3]} {info['start'] % 24:02d}-{info['end'] % 24:02d}")
        actual_cost += e.hourly_wage * h_tot
        if worked:
            print(f"  {e.name} [{e.role}] {h_tot}h @ ${e.hourly_wage}/h: {', '.join(worked)}")
        else:
            print(f"  {e.name} [{e.role}]: scartato")
    print(f"\n  Total weekly cost: ${actual_cost:.2f}")

    # --- soddisfazione (richieste 'schedule' valutate sullo schedule realizzato) ---
    def types_worked(uid):
        return {daily_shifts[d][sid]['type'] for d in open_days for sid in schedule[uid][d]}

    def days_worked(uid):
        return sum(1 for d in DAYS_OF_WEEK if schedule[uid][d])

    SATP = {'critical': 100, 'important': 80, 'nice_to_have': 50}
    total_sat = 0
    max_sat = 0
    unmet_soft = []  # (uid, nome, constraint, priorita', punti) richieste schedule non soddisfatte
    for e in employees:
        if days_worked(e.uid) == 0:
            continue
        tw = types_worked(e.uid)
        hrs = sum(daily_shifts[d][sid]['hours'] for d in open_days for sid in schedule[e.uid][d])
        for dm in e.demands:
            if dm.category != 'schedule':
                continue
            pts = SATP[dm.priority]
            max_sat += pts
            c = dm.constraint
            ok = False
            if c == 'full_time':
                ok = 30 <= hrs <= 50
            elif c == 'part_time':
                ok = 10 <= hrs <= 30
            elif c == 'four_days':
                ok = days_worked(e.uid) <= 4
            elif c == 'five_days':
                ok = days_worked(e.uid) <= 5
            elif c == 'free_weekend':
                ok = (not schedule[e.uid]['Saturday']) and (not schedule[e.uid]['Sunday'])
            elif c == 'no_morning':
                ok = 'morning' not in tw
            elif c == 'no_afternoon':
                ok = 'afternoon' not in tw
            elif c == 'no_night':
                ok = 'night' not in tw
            elif c == 'no_evening':
                ok = ('afternoon' not in tw) and ('night' not in tw)
            elif c == 'no_cleaning':
                ok = 'night' not in tw
            if ok:
                total_sat += pts
            else:
                unmet_soft.append((e.uid, e.name, c, dm.priority, pts))
    sat_pct = (total_sat / max_sat * 100) if max_sat > 0 else None
    print(f"  Satisfaction: {'N/A' if sat_pct is None else f'{sat_pct:.1f}%'} "
          f"({total_sat}/{max_sat})")
    # Quali richieste hanno fatto perdere punti (i critical qui non compaiono mai:
    # sono hard). Ti dice esattamente da dove arriva il % mancante.
    if unmet_soft:
        print(f"  Richieste NON soddisfatte ({sum(t[-1] for t in unmet_soft)} punti persi):")
        for _uid, name, c, prio, pts in unmet_soft:
            print(f"    - {name}: {c} ({prio}, -{pts})")

    # --- consigli generali (dai soli fatti del solver, testo EN per la UI) ---
    from analysis.schedule_advice import build_recommendations, format_console
    recommendations = build_recommendations(
        employees=employees,
        schedule=schedule,
        demand=demand,
        demand_info=demand_info,
        coverage_report=coverage_report,
        unmet_soft=unmet_soft,
        open_days=open_days,
        open_hours=open_hours,
        max_shift_len=max_shift_len,
        business_name=business_setup.business_name,
        econ=econ,
        ppc=_ppc,
    )
    for _ln in format_console(recommendations):
        print(_ln)

    unmet_list = [f"{role}: {v:.0f}h" for role, v in sorted(real_gaps.items())]
    return OptimizationResult(
        success=True, status=("Optimal" if proven_optimal else "Feasible (time-limited)"),
        total_cost=actual_cost,
        total_satisfaction=sat_pct, schedule=schedule, daily_shifts=daily_shifts,
        unmet_demands=unmet_list, solver_time=solver_time,
        coverage_report=coverage_report,
        recommendations=recommendations,
    )