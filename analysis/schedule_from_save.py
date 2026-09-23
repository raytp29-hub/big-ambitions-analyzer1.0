"""
analysis/schedule_from_save.py
Carica nello Schedule Optimizer un business VERO dal save .hsg.

Prima gli step 1-4 della pagina si compilavano a mano (categoria, taglia,
mobili, dipendenti con le loro richieste, orari). Qui li ricaviamo dal save:

    Step 1  Building + mobili   ← snapshot.businesses, snapshot.furniture, game data
    Step 2  Dipendenti          ← snapshot.employees (+ skills, demands), shifts
    Step 4  Orari               ← snapshot.opening_hours
    Domanda clienti             ← hour_reports (clienti reali per giorno × ora),
                                  al posto della curva del gioco

Il risultato è un SavedScheduleSetup con gli STESSI oggetti che la pagina
mette in session_state (Building, Employee, DailySchedule, selected_furniture):
l'optimizer non sa da dove arrivano, e l'utente può ancora modificarli.

Tutto il resto (ruoli, postazioni, clienti per ora) riusa analysis/staffing_fit.py,
così Health Check e Schedule Optimizer vedono lo stesso business allo stesso modo.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from analysis.business_alerts import hours_in_slot
from analysis.schedule_models import Building, DailySchedule, Demand, Employee
from core.data_loader import DataBundle


DAY_NAMES_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Richieste del gioco → vincoli dello Schedule Optimizer (category, constraint).
# Le chiavi di constraint sono quelle di schedule_constraints (SCHEDULE_DEMANDS ecc.).
JOB_DEMAND_MAP = {
    "ba:jobdemand_fulltime":             ("schedule", "full_time"),
    "ba:jobdemand_parttime":             ("schedule", "part_time"),
    "ba:jobdemand_fourdaysweek":         ("schedule", "four_days"),
    "ba:jobdemand_fivedaysweek":         ("schedule", "five_days"),
    "ba:jobdemand_nomornings":           ("schedule", "no_morning"),
    "ba:jobdemand_noafternoons":         ("schedule", "no_afternoon"),
    "ba:jobdemand_noevenings":           ("schedule", "no_evening"),
    "ba:jobdemand_nonights":             ("schedule", "no_night"),
    "ba:jobdemand_freeweekends":         ("schedule", "free_weekend"),
    "ba:jobdemand_nocleaning":           ("schedule", "no_cleaning"),
    "ba:jobdemand_bronzehealthinsurance": ("benefits", "bronze_insurance"),
    "ba:jobdemand_silverhealthinsurance": ("benefits", "silver_insurance"),
    "ba:jobdemand_goldhealthinsurance":   ("benefits", "gold_insurance"),
    "ba:jobdemand_peacefulworkenvironment": ("environment", "peaceful_environment"),
    "ba:jobdemand_cleanworkplace":        ("environment", "clean_environment"),
    # tutto il resto (sedia, monitor, water cooler...) → equipment, col nome del gioco
}

# job_demands[].priority nel game data → priorità dell'optimizer
PRIORITY_MAP = {2: "critical", 1: "important", 0: "nice_to_have"}


# ============================================================================
# DATACLASS
# ============================================================================

@dataclass
class SavedScheduleSetup:
    """Tutto quello che la pagina mette in session_state, ricavato dal save."""
    address: str
    business_name: str
    display_type: str                 # "Fast Food Restaurant" (nome che usa la pagina)
    category: str                     # "Retail", "Office"...
    building: Building
    selected_furniture: list          # stesso formato dello Step 1 della pagina
    max_simultaneous: int
    effective_capacity: int
    total_furniture_cost: float
    employees: list                   # list[Employee]
    weekly_schedule: list             # list[DailySchedule], lunedì → domenica
    customers_by_hour: Optional[dict] # {(giorno, ora): clienti}; None = curva del gioco
    customers_source: str             # "observed" | "game curve"
    current_weekly_cost: float        # salari dei turni attuali nel save
    current_weekly_hours: int
    notes: list = field(default_factory=list)   # avvisi per l'utente
    employee_ids: list = field(default_factory=list)   # id del save, allineati a `employees`


# ============================================================================
# RICHIESTE DEI DIPENDENTI
# ============================================================================

def _default_priorities() -> dict[str, int]:
    from core.game_data import _game_data
    return {j["demandName"]: j.get("priority", 1) for j in _game_data.get("job_demands", [])}


def _default_demand_label(key: str) -> str:
    from core.localization import display_name
    return display_name(key, default=key.rsplit("_", 1)[-1].title())


def to_demand(key: str, priorities: dict[str, int], label=_default_demand_label) -> Demand:
    """ba:jobdemand_* → Demand dell'optimizer, con la priorità che dà il gioco."""
    category, constraint = JOB_DEMAND_MAP.get(key, ("equipment", None))
    if constraint is None:
        constraint = label(key)
    priority = PRIORITY_MAP.get(priorities.get(key, 1), "important")
    return Demand(category=category, constraint=constraint, priority=priority)


# ============================================================================
# RUOLO DI UN DIPENDENTE
# ============================================================================

def employee_role(shift_roles: list[str], skills: dict[str, float], business_skills: set[str],
                  skill_name) -> str:
    """
    1) il ruolo della postazione su cui lavora più spesso (cosa FA davvero);
    2) se non ha turni: la sua skill più alta fra quelle del tipo di business;
    3) altrimenti "Unassigned".
    """
    roles = [r for r in shift_roles if r and r != "Unassigned station"]
    if roles:
        return Counter(roles).most_common(1)[0][0]
    relevant = {k: v for k, v in skills.items() if k in business_skills}
    if relevant:
        return skill_name(max(relevant, key=relevant.get))
    return "Unassigned"


def _unique_names(names: list[str]) -> list[str]:
    """La pagina rifiuta nomi duplicati: 'Ann', 'Ann' → 'Ann', 'Ann (2)'."""
    seen: dict[str, int] = {}
    out = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n} ({seen[n]})")
    return out


# ============================================================================
# MOBILI E ORARI
# ============================================================================

def build_selected_furniture(furniture: dict[str, int], business_skills: set[str],
                             item_lookup=None, item_label=None, skill_name=None) -> list[dict]:
    """
    Gli oggetti che contano per l'optimizer (postazioni e mobili che portano
    clienti), nello STESSO formato dei dict che crea lo Step 1 della pagina.
    Le postazioni multi-skill (computer) tengono solo le skill del business.
    """
    from core.game_data import get_item_by_id, item_name, skill_display
    item_lookup = item_lookup or get_item_by_id
    item_label = item_label or item_name
    skill_name = skill_name or skill_display

    selected = []
    for key, qty in sorted(furniture.items()):
        item = item_lookup(key)
        if not item:
            continue
        capacity = int(item.get("addedCustomersPerHour") or 0)
        is_ws = bool(item.get("assignable"))
        if not is_ws and capacity <= 0:
            continue                       # decorazioni, sedie, piante...
        skills = [s for s in (item.get("suitableSkills") or []) if s in business_skills] if is_ws else []
        if is_ws and not skills:
            continue                       # postazione di un altro mestiere
        price = float(item.get("defaultMarketPrice") or 0)
        qty = int(qty)
        selected.append({
            "name": item_label(item),
            "unit_capacity": capacity,
            "quantity": qty,
            "total_capacity": capacity * qty,
            "unit_price": f"${price:,.0f}",
            "total_price": price * qty,
            "is_workstation": is_ws,
            "suitable_skills": [skill_name(s) for s in skills],
            "item_key": key,
        })
    return selected


def effective_capacity(selected_furniture: list[dict], building_capacity: int) -> int:
    """
    Regola dello Step 1 (collo di bottiglia = lo "stadio" che serve meno
    clienti/ora), mai oltre la capacità del building. Differenza: le postazioni
    dello stesso ruolo sono UNO stadio e si sommano (49 computer + 1 laptop in
    uno studio legale = 50/h, non 1/h del laptop).
    """
    stages: dict[str, int] = {}
    for f in selected_furniture:
        if f["total_capacity"] <= 0:
            continue
        stage = ("role:" + ",".join(f["suitable_skills"])) if f["is_workstation"] else f["name"]
        stages[stage] = stages.get(stage, 0) + f["total_capacity"]
    bottleneck = min(stages.values()) if stages else 0
    if building_capacity > 0:
        return min(bottleneck, building_capacity) if bottleneck else building_capacity
    return bottleneck


def build_weekly_schedule(open_hours: dict[int, set]) -> list[DailySchedule]:
    """
    {1: {11..23}} → DailySchedule lunedì..domenica.
    Il gioco usa 24 per "mezzanotte"; la pagina accetta ore 0-23 e tratta
    fine < inizio come apertura oltre mezzanotte → 24 diventa 0.
    Più fasce nello stesso giorno (non presenti nel save di test) vengono
    fuse dalla prima all'ultima ora.
    """
    week = []
    for idx, day_name in enumerate(DAY_NAMES_FULL, start=1):
        hours = sorted(open_hours.get(idx, set()))
        if not hours:
            week.append(DailySchedule(day_name=day_name, is_open=False))
            continue
        start, end = hours[0], hours[-1] + 1
        week.append(DailySchedule(day_name=day_name, is_open=True,
                                  start_hour=start, end_hour=end % 24))
    return week


def to_named_days(customers: dict[tuple[int, int], float]) -> dict[tuple[str, int], float]:
    """{(1, 12): 14.0} → {("Monday", 12): 14.0}: l'optimizer usa i nomi dei giorni."""
    return {(DAY_NAMES_FULL[d - 1], h): v for (d, h), v in customers.items()}


# ============================================================================
# ENTRY POINT
# ============================================================================

def load_schedule_setup(bundle: DataBundle, address: str, window_days: int = 14,
                        use_real_customers: bool = True) -> Optional[SavedScheduleSetup]:
    from analysis.business_fit import _window, open_hours_by_day, resolve_business_profile
    from analysis.staffing_fit import business_skills, observed_customers, station_for
    from core.game_data import business_type_display_by_name, _get_business_type, skill_display
    from core.localization import display_name

    snap = bundle.snapshot
    profile = resolve_business_profile(snap, address)
    if profile is None:
        return None
    notes = []
    skills = business_skills(profile.biz_name)
    bt = _get_business_type(profile.biz_name) or {}

    # --- Step 1: building + mobili ---
    furn = snap.furniture[snap.furniture["address"] == address]
    selected = build_selected_furniture(dict(zip(furn["item_key"], furn["count"])), skills)
    eff_cap = effective_capacity(selected, profile.capacity)
    max_sim = sum(f["quantity"] for f in selected if f["is_workstation"]) or 1
    display_type = business_type_display_by_name(profile.biz_name)
    category = display_name(bt.get("suitableBuildingType", ""), default="")
    building = Building(business_type=category, code=profile.building_size or "?",
                        capacity_limit=eff_cap, business_name=display_type)
    if not any(f["is_workstation"] for f in selected):
        notes.append("No workstations found in this building: the optimizer has no stations to staff.")

    # --- turni attuali: ruolo per turno + costo attuale ---
    shifts = snap.shifts[snap.shifts["address"] == address]
    emp = snap.employees[snap.employees["address"] == address]
    wage = dict(zip(emp["employee_id"], emp["hourly_wage"]))
    roles_by_emp: dict[str, list[str]] = {}
    current_hours, current_cost = 0, 0.0
    for s in shifts.itertuples():
        key = s.station_item_key if isinstance(s.station_item_key, str) else ""
        st_ = station_for(key, skills)
        roles_by_emp.setdefault(s.employee_id, []).append(st_.role if st_ else "")
        h = len(hours_in_slot(s.start_hour, s.end_hour))
        current_hours += h
        current_cost += h * float(wage.get(s.employee_id, 0.0))

    # --- Step 2: dipendenti ---
    priorities = _default_priorities()
    sk = snap.employee_skills
    dm = snap.employee_demands
    names = _unique_names([str(n) for n in emp["name"]])
    employees = []
    for name, row in zip(names, emp.itertuples()):
        emp_skills = dict(zip(sk.loc[sk["employee_id"] == row.employee_id, "skill_key"],
                              sk.loc[sk["employee_id"] == row.employee_id, "value"]))
        role = employee_role(roles_by_emp.get(row.employee_id, []), emp_skills, skills, skill_display)
        demands = [to_demand(k, priorities)
                   for k in dm.loc[dm["employee_id"] == row.employee_id, "demand_key"]]
        employees.append(Employee(name=name, role=role, hourly_wage=round(float(row.hourly_wage), 2),
                                  demands=demands))
    unassigned = [e.name for e in employees if e.role == "Unassigned"]
    if unassigned:
        notes.append(f"{len(unassigned)} employee(s) without a role for this business: "
                     + ", ".join(unassigned[:5]))

    # --- Step 4: orari ---
    week = build_weekly_schedule(open_hours_by_day(snap, address))

    # --- domanda: clienti reali per giorno × ora ---
    customers, source = None, "game curve"
    if use_real_customers:
        days = _window(bundle.hour_reports, window_days)
        obs = observed_customers(bundle.hour_reports, profile.business_name, days)
        if obs:
            customers, source = to_named_days(obs), "observed"
        else:
            notes.append("No hour reports for this business: using the game's demand curve.")

    return SavedScheduleSetup(
        address=address,
        business_name=profile.business_name,
        display_type=display_type,
        category=category,
        building=building,
        selected_furniture=selected,
        max_simultaneous=max_sim,
        effective_capacity=eff_cap,
        total_furniture_cost=sum(f["total_price"] for f in selected),
        employees=employees,
        weekly_schedule=week,
        customers_by_hour=customers,
        customers_source=source,
        current_weekly_cost=current_cost,
        current_weekly_hours=current_hours,
        notes=notes,
        employee_ids=[str(i) for i in emp["employee_id"]],
    )
