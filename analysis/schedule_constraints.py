"""
Schedule Constraints and Configuration
Loads game data from JSON via core.game_data module.
All business types, buildings, furniture, and roles are derived from the game data.
"""
from collections import defaultdict
import sys
from pathlib import Path
import pandas as pd
from typing import Dict, List, Tuple


# Ensure project root is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.game_data import (
    get_business_categories,
    get_businesses_for_category,
    get_building_sizes_for_category,
    get_building_capacity as _get_building_capacity,
    get_furniture_for_business as _get_furniture_for_business,
    get_employee_roles_for_business,
    format_item_name,
    get_demand_multipliers,
    display_to_internal,
)




DAY_NAME_TO_NUM = {
    'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 'Thursday': 4,
    'Friday': 5, 'Saturday': 6, 'Sunday': 7,
}

# ============================================================================
# HELPER
# ============================================================================

def _hourly_multiplier_at(hour:int, hourly_bands: List[dict]) -> float:
    """Multiplier della fascia che contiene `hour` (0-23). 0.0 se nessuna."""
    h = hour % 24
    for band in hourly_bands:
        if band['start'] <= h < band['end']:
            return band['multiplier']
    return 0.0



def compute_peak_customers(business_name: str, effective_capacity: int, daily_shifts: Dict[str, Dict[str, dict]],) -> Dict[Tuple[str, str], float]:
    """Clienti dell'ora di picco per ogni (giorno, turno).
    peak = effective_capacity * max(hourly_mult sulle ore del turno) * daily_mult[giorno]."""
    mults = get_demand_multipliers(display_to_internal(business_name))
    if mults is None:
        return {}

    hourly = mults['hourly']
    daily = {d['day']: d['multiplier'] for d in mults['daily']}

    peak: Dict[Tuple[str, str], float] = {}
    for day_name, shifts in daily_shifts.items():
        if not shifts:
            continue
        day_mult = daily.get(DAY_NAME_TO_NUM[day_name], 1.0)
        for shift_name, info in shifts.items():
            shift_hours = [(info['start'] + i) % 24 for i in range(info['hours'])]
            peak_mult = max(_hourly_multiplier_at(h, hourly) for h in shift_hours)
            peak[(day_name, shift_name)] = effective_capacity * peak_mult * day_mult
    return peak


def _stations_needed(throughputs: List[int], peak: float) -> int:
    """Minimo n° di postazioni (dalle più capienti) per coprire `peak` clienti.
    Se nemmeno tutte bastano, restituisce quante ne hai (sei capacity-limited)."""
    if peak <= 0:
        return 0
    cum = 0
    for k, cap in enumerate(sorted(throughputs, reverse=True), start=1):
        cum += cap
        if cum >= peak:
            return k
    return len(throughputs)


def compute_role_demand(roles: List[str], peak_customers: Dict[Tuple[str, str], float], role_workstations: Dict[str, List[int]], cleaning_per_shift: int = 1, headcount_per_shift: int = 1, role_headcount: Dict[str, int] = None, ) -> Dict[Tuple[str, str, str], int]:
    """Fabbisogno minimo di addetti per (ruolo, giorno, turno).

    Se `role_headcount` e' fornito, il fabbisogno viene LIMITATO ALL'ORGANICO:
    per ogni (ruolo, giorno) il totale richiesto sui turni non puo' superare il
    numero di dipendenti di quel ruolo (ognuno fa al massimo un turno/giorno).
    L'organico viene distribuito con un "water-filling": prima 1 addetto a OGNI
    turno con clienti (in ordine di picco), poi i restanti vanno ad approfondire
    i turni di punta. Cosi' nessun turno con domanda resta scoperto (clienti alla
    cassa senza nessuno = vendite perse), finche' l'organico lo consente; con un
    solo addetto (es. Security) copre solo il turno di picco.
    """
    role_headcount = role_headcount or {}
    demand: Dict[Tuple[str, str, str], int] = {}

    # Raggruppa i turni per giorno (servono per la distribuzione dell'organico).
    shifts_by_day: Dict[str, List[str]] = defaultdict(list)
    for (day, shift) in peak_customers:
        shifts_by_day[day].append(shift)

    for role in roles:
        stations = role_workstations.get(role, [])

        # 1) Fabbisogno "grezzo" per turno (dal flusso clienti o presenza fissa).
        raw: Dict[Tuple[str, str], int] = {}
        for (day, shift), peak in peak_customers.items():
            if stations and max(stations) > 0:
                need = _stations_needed(stations, peak)
            elif stations:
                need = min(cleaning_per_shift, len(stations))
            else:
                need = headcount_per_shift
            raw[(day, shift)] = need

        cap = role_headcount.get(role)  # n. dipendenti del ruolo (None => nessun cap)

        # 2) Per ogni giorno: senza cap usa il grezzo; con cap distribuisci
        #    l'organico con water-filling (prima ampiezza, poi profondita').
        for day, shifts in shifts_by_day.items():
            if cap is None:
                for shift in shifts:
                    demand[(role, day, shift)] = raw[(day, shift)]
                continue

            ordered = sorted(shifts, key=lambda s: peak_customers[(day, s)], reverse=True)
            alloc = {shift: 0 for shift in shifts}
            remaining = cap
            progress = True
            # Ogni passata aggiunge al massimo 1 addetto per turno: la prima
            # passata copre tutti i turni (in ordine di picco), le successive
            # rinforzano i turni di punta finche' resta organico.
            while remaining > 0 and progress:
                progress = False
                for shift in ordered:
                    if remaining <= 0:
                        break
                    if alloc[shift] < raw[(day, shift)]:
                        alloc[shift] += 1
                        remaining -= 1
                        progress = True
            for shift in shifts:
                demand[(role, day, shift)] = alloc[shift]

    return demand


# ============================================================================
# MODELLO A TURNI VARIABILI (domanda oraria + template di turno)
# ============================================================================

def hours_range(start_hour: int, end_hour: int) -> List[int]:
    """Ore di apertura come lista di interi.

    Normale: [start, end). Overnight (chiusura <= apertura, a cavallo della
    mezzanotte): le ore dopo mezzanotte diventano 24..27 (= 0..3 del giorno dopo),
    cosi' la sequenza resta continua e crescente. I moltiplicatori orari usano
    comunque h % 24, quindi 24->0, 25->1, ecc.
    """
    if end_hour == start_hour:
        return []
    if end_hour < start_hour:
        return list(range(start_hour, end_hour + 24))
    return list(range(start_hour, end_hour))


def peak_hours_for_day(business_name: str, open_hours: List[int], threshold: float = 0.999) -> set:
    """Ore (entro l'apertura) col moltiplicatore orario massimo (>= threshold*max)."""
    mults = get_demand_multipliers(display_to_internal(business_name))
    if mults is None or not open_hours:
        return set()
    hourly = mults['hourly']
    vals = {h: _hourly_multiplier_at(h, hourly) for h in open_hours}
    mx = max(vals.values()) if vals else 0.0
    if mx <= 0:
        return set()
    return {h for h, v in vals.items() if v >= threshold * mx}


def peak_duration(business_name: str, open_hours: List[int]) -> int:
    """Durata (h) del piu' lungo blocco contiguo di ore di picco entro l'apertura."""
    ph = peak_hours_for_day(business_name, open_hours)
    if not ph:
        return 1
    best = cur = 0
    prev = None
    for h in sorted(ph):
        cur = cur + 1 if (prev is not None and h == prev + 1) else 1
        best = max(best, cur)
        prev = h
    return max(best, 1)


def suggested_opening_hours(business_name: str, threshold: float = 0.5) -> Tuple[int, int]:
    """Finestra oraria consigliata (start, end) dove la domanda media settimanale
    e' >= threshold del picco. STESSA logica del Game Data Explorer
    (_render_demand_curves): media su 7 giorni di daily_mult x hourly_mult, e si
    prende dal primo all'ultimo ora sopra soglia. Ritorna None se non disponibile.

    Serve ai consigli per segnalare ore di apertura a domanda ~0 (paghi personale
    per pochi clienti -> incide sul pareggio).
    """
    mults = get_demand_multipliers(display_to_internal(business_name))
    if not mults:
        return None
    hourly24 = [0.0] * 24
    for band in mults['hourly']:
        for hour in range(band['start'], band['end']):
            if 0 <= hour < 24:
                hourly24[hour] = band['multiplier']
    daily = [d['multiplier'] for d in mults['daily']] or [1.0]
    n = len(daily)
    avg_hourly = [sum(daily[d] * hourly24[h] for d in range(n)) / n for h in range(24)]
    good = [h for h, v in enumerate(avg_hourly) if v >= threshold]
    if not good:
        return None
    return (good[0], good[-1] + 1)


def generate_shift_templates(start_hour: int, end_hour: int, min_len: int, max_len: int = 8) -> List[Tuple[int, int]]:
    """Tutte le finestre contigue [s, e) dentro [start, end) con durata in [min_len, max_len]."""
    span = end_hour - start_hour
    if span <= 0:
        return []
    lo = max(1, min(min_len, span))
    hi = min(max_len, span)
    templates: List[Tuple[int, int]] = []
    for L in range(lo, hi + 1):
        for s in range(start_hour, end_hour - L + 1):
            templates.append((s, s + L))
    if not templates:
        templates.append((start_hour, end_hour))
    return templates


def estimate_profit_per_customer(business_name: str) -> float:
    """Profitto medio per cliente del business = Σ (prezzo-costo)×probabilita' sui
    prodotti 'core' (impact>=0.90). Riusa rank_products di health_check. 0 se non
    disponibile (in quel caso lo slack resta a penalita' piatta)."""
    try:
        from analysis.health_check import rank_products
        prods = rank_products(display_to_internal(business_name))
        core = [p for p in prods if p.impact >= 0.90] or prods[:3]
        if not core:
            return 0.0
        return float(sum((p.market_price - p.wholesale_price) * p.probability for p in core))
    except Exception:
        return 0.0


def compute_hourly_role_demand(
    business_name: str,
    effective_capacity: int,
    open_hours_by_day: Dict[str, List[int]],
    role_workstations: Dict[str, List[int]],
    role_headcount: Dict[str, int],
    cleaning_per_shift: int = 1,
    security_per_shift: int = 1,
    max_shift_len: int = 8,
    role_capacity: Dict[str, int] = None,
    customers_per_guard: int = 0,
) -> Tuple[Dict[Tuple[str, str, int], int], Dict[str, dict]]:
    """Fabbisogno di addetti per (ruolo, giorno, ora), LIMITATO ALL'ORGANICO.

    Tipi di ruolo (dedotti dai dati, niente nomi hardcoded):
    - VENDITA (postazioni con throughput>0, es. Customer Service / Designer):
      fabbisogno = max(1, stazioni necessarie al flusso) -> floor di 1 ogni ora
      aperta (niente buchi di vendita).
    - PRESENZA con postazione a throughput 0 (cleaning): presenza ogni ora aperta
      (utilita': se pulisce solo al picco il negozio si sporca).
    - SECURITY: presenza CONTINUA su tutte le ore aperte (un furto puo' avvenire
      in qualunque momento di apertura, non solo al picco). Il numero di guardie
      contemporanee = `security_per_shift` come floor, e se `customers_per_guard>0`
      scala con la capacita' clienti dell'edificio (proxy della dimensione, dato
      che il dump JSON non espone una formula guardie/m2): guardie = max(
      security_per_shift, ceil(effective_capacity / customers_per_guard)).

    Capping: per ogni ruolo, se il fabbisogno totale supera le ore-persona
    erogabili (organico × min(50, giorni×max_shift_len)), si distribuisce la
    capacita' dando priorita' alle ore piu' trafficate. Per il ruolo di vendita
    si protegge prima il floor di 1 ovunque (no buchi), poi si aggiunge l'extra
    sul picco. Cosi' il modello e' SEMPRE risolvibile (best-effort sull'organico).

    Ritorna (demand, info) dove info[ruolo] = {ideal, assigned, cap, uncovered}.
    """
    mults = get_demand_multipliers(display_to_internal(business_name))
    daily = {d['day']: d['multiplier'] for d in mults['daily']} if mults else {}
    hourly = mults['hourly'] if mults else []
    n_days = len(open_hours_by_day)
    role_capacity = role_capacity or {}
    ppc = estimate_profit_per_customer(business_name)  # profitto medio per cliente

    demand: Dict[Tuple[str, str, int], int] = {}
    info: Dict[str, dict] = {}
    econ: Dict[Tuple[str, str, int], float] = {}  # valore di un CS extra per (ruolo,giorno,ora)

    for role, hc in role_headcount.items():
        stations = role_workstations.get(role, [])
        selling = bool(stations) and max(stations) > 0
        throughput = max(stations) if stations else 0

        # 1) fabbisogno "ideale" per ora + flusso clienti per priorita'
        raw: Dict[Tuple[str, int], int] = {}
        flow: Dict[Tuple[str, int], float] = {}
        for day, hours in open_hours_by_day.items():
            daymult = daily.get(DAY_NAME_TO_NUM[day], 1.0)
            ph = peak_hours_for_day(business_name, hours)
            for h in hours:
                cust = effective_capacity * _hourly_multiplier_at(h, hourly) * daymult
                flow[(day, h)] = cust
                if selling:
                    raw[(day, h)] = min(hc, max(1, _stations_needed(stations, cust)))
                    # valore economico di UN addetto extra in quest'ora:
                    # clienti che servirebbe (min throughput, flusso) × profitto/cliente
                    econ[(role, day, h)] = ppc * min(throughput, cust) if ppc > 0 else 0.0
                elif stations:                       # presenza con postazione (cleaning, security): ogni ora
                    raw[(day, h)] = min(hc, cleaning_per_shift)
                else:                                # ruoli senza postazione: al picco
                    raw[(day, h)] = min(hc, security_per_shift) if h in ph else 0

        # Capacita' erogabile dal ruolo: somma delle ore max per dipendente
        # (rispetta la banda contrattuale, es. part-time <=30h). Fallback: hc×giorni×ore.
        cap_hours = role_capacity.get(role, hc * min(50, n_days * max_shift_len))
        ideal = sum(raw.values())
        keys = list(raw.keys())

        if ideal <= cap_hours:
            alloc = dict(raw)
        else:
            # capping a capacita', priorita' alle ore col flusso piu' alto
            alloc = {k: 0 for k in keys}
            remaining = cap_hours
            order = sorted(keys, key=lambda k: flow[k], reverse=True)
            if selling:
                # 1a) proteggi il floor di 1 dove serve (no buchi di vendita)
                for k in order:
                    if remaining <= 0:
                        break
                    if raw[k] >= 1:
                        alloc[k] = 1
                        remaining -= 1
            # 1b) riempi l'extra (e, per presenza, tutto) a passate, per flusso
            improved = True
            while remaining > 0 and improved:
                improved = False
                for k in order:
                    if remaining <= 0:
                        break
                    if alloc[k] < raw[k]:
                        alloc[k] += 1
                        remaining -= 1
                        improved = True

        for (day, h), need in alloc.items():
            demand[(role, day, h)] = need

        uncovered = sum(1 for k in keys if raw[k] >= 1 and alloc[k] == 0)
        info[role] = {
            'ideal': ideal,
            'assigned': sum(alloc.values()),
            'cap': cap_hours,
            'uncovered': uncovered,
            'selling': selling,
            'ppc': ppc,
        }

    return demand, info, econ


def compute_staffing_recommendation(
    business_name: str,
    effective_capacity: int,
    open_hours_by_day: Dict[str, List[int]],
    role_workstations: Dict[str, List[int]],
    max_shift_len: int = 8,
    cleaning_per_shift: int = 1,
    security_per_shift: int = 1,
    customers_per_guard: int = 0,
) -> Dict[str, dict]:
    """Consiglia l'organico per ruolo SENZA dipendenti, da furniture + orari + dati gioco.

    Per ogni ruolo calcola tre driver e prende il massimo:
    - picco simultaneo (addetti contemporanei al picco, <= postazioni),
    - continuita' span (ceil(ore aperte/giorno / max_shift) per coprire l'intera fascia),
    - ore totali (ceil(ore-persona/settimana / ore max per dipendente)).
    Poi propone un mix full/part: base continua = full-time, picchi extra = part-time.

    Ritorna {role: {headcount, full_time, part_time, peak, span, hours, stations, role_type}}.
    """
    import math
    mults = get_demand_multipliers(display_to_internal(business_name))
    daily = {d['day']: d['multiplier'] for d in mults['daily']} if mults else {}
    hourly = mults['hourly'] if mults else []
    n_open_days = sum(1 for h in open_hours_by_day.values() if h)
    per_emp_full = min(50, n_open_days * max_shift_len) or max_shift_len

    recs: Dict[str, dict] = {}
    for role, stations in role_workstations.items():
        selling = bool(stations) and max(stations) > 0
        is_security = 'security' in role.lower()  # solo per l'etichetta role_type
        n_stations = len(stations)
        # presenza con postazione (cleaning/security) -> copertura continua
        continuous = selling or bool(stations)

        total_hours = 0
        peak_per_hour = 0
        max_span = 0
        for day, hours in open_hours_by_day.items():
            if not hours:
                continue
            max_span = max(max_span, len(hours))
            daymult = daily.get(DAY_NAME_TO_NUM[day], 1.0)
            ph = peak_hours_for_day(business_name, hours)
            for h in hours:
                cust = effective_capacity * _hourly_multiplier_at(h, hourly) * daymult
                if selling:
                    need = max(1, _stations_needed(stations, cust))
                elif stations:
                    need = cleaning_per_shift  # presenza con postazione (cleaning/security)
                else:
                    need = security_per_shift if h in ph else 0
                total_hours += need
                peak_per_hour = max(peak_per_hour, need)

        if n_stations > 0:
            peak_per_hour = min(peak_per_hour, n_stations)  # simultanei <= postazioni

        span_people = math.ceil(max_span / max_shift_len) if (continuous and max_span > 0) else 1
        hours_people = math.ceil(total_hours / per_emp_full) if (total_hours > 0 and per_emp_full) else 0
        headcount = max(peak_per_hour, span_people, hours_people, 1 if total_hours > 0 else 0)

        if headcount == 0:
            full_time = part_time = 0
        elif continuous:
            full_time = min(headcount, max(span_people, 1))
            part_time = headcount - full_time
        else:  # presenza-picco (security): full-time solo se molte ore, altrimenti part-time
            avg = total_hours / headcount if headcount else 0
            full_time, part_time = (headcount, 0) if avg >= 30 else (0, headcount)

        recs[role] = {
            'headcount': headcount,
            'full_time': full_time,
            'part_time': part_time,
            'peak': peak_per_hour,
            'span': max_span,
            'hours': int(round(total_hours)),
            'stations': n_stations,
            'role_type': 'sales' if selling else ('security' if is_security else 'presence'),
        }
    return recs


# ============================================================================
# BUSINESS CATEGORIES & TYPES (from game data)
# ============================================================================

def get_available_categories() -> List[str]:
    """Get list of business categories: Cinema, Office, Retail, Theater, Warehouse"""
    return get_business_categories()


def get_business_tupes_for_category(category: str) -> List[str]:
    """
    Get business types for a category. Returns display names.
    e.g., 'Retail' -> ['Bookstore', 'Clothing Store', 'Coffee Shop', ...]
    """
    raw_names = get_businesses_for_category(category)
    # Exclude Headquarters from the UI list
    excluded = ['Headquarter']
    return [format_item_name(name) for name in raw_names if name not in excluded]


# ============================================================================
# BUILDING DATA (from game data)
# ============================================================================

def get_available_buildings(business_category: str) -> List[str]:
    """
    Get list of available building codes for a category.
    Returns codes like 'A1', 'A2', 'C1', 'S1', 'R3', etc.
    """
    sizes = get_building_sizes_for_category(business_category)
    codes = []
    for size in sizes:
        for version in size['versions']:
            codes.append(f"{size['letter']}{version['number']}")
    return sorted(codes)


def get_building_capacity(business_category: str, building_code: str) -> int:
    """
    Get capacity limit for a specific building code.
    e.g., get_building_capacity('Retail', 'A1') -> 15
          get_building_capacity('Cinema', 'S2') -> 125
    """
    # Parse code: letter(s) + version number (last char)
    letter = building_code[:-1]
    version = int(building_code[-1])
    return _get_building_capacity(business_category, letter, version)


# ============================================================================
# FURNITURE (from game data)
# ============================================================================

def get_furniture_for_business(business_type: str) -> pd.DataFrame:
    """
    Get available furniture for a business type.
    Accepts display name ('Coffee Shop') or internal name ('CoffeeShop').
    Returns DataFrame compatible with existing UI code.
    """
    # Convert display name to internal name (remove spaces)
    internal_name = business_type.replace(' ', '')
    furniture_list = _get_furniture_for_business(internal_name)

    if not furniture_list:
        return pd.DataFrame(columns=[
            'furniture_name', 'customer_capacity', 'price', 'is_workstation'
        ])

    rows = []
    for f in furniture_list:
        rows.append({
            'furniture_name': f['display_name'],
            'customer_capacity': f['added_customers_per_hour'],
            'price': f'${f["price"]:,.0f}',
            'is_workstation': f['is_workstation'],
            'item_name_internal': f['item_name'],
            'suitable_skills': f['suitable_skills']
        })

    return pd.DataFrame(rows)


def parse_price(price_str: str) -> float:
    """Parse price string like '$1,400' to float"""
    if pd.isna(price_str):
        return 0.0
    return float(str(price_str).replace('$', '').replace(',', ''))


# ============================================================================
# EMPLOYEE ROLES (from game data)
# ============================================================================

def get_roles_for_business_type(business_type: str) -> List[str]:
    """
    Get available employee roles for a business type.
    Accepts display name ('Coffee Shop') or internal name ('CoffeeShop').
    """
    internal_name = business_type.replace(' ', '')
    return get_employee_roles_for_business(internal_name)


# ============================================================================
# WORKSTATION CAPACITY
# ============================================================================

def calculate_workstation_capacity(selected_furniture: List[Dict], business_category: str) -> int:
    """
    Calculate max simultaneous employees based on workstations.
    Uses is_workstation flag from game data instead of hardcoded name checks.
    """
    workstation_count = 0
    for furn in selected_furniture:
        if furn.get('is_workstation', False):
            workstation_count += furn.get('quantity', 1)
    return workstation_count if workstation_count > 0 else 1



def get_role_workstations(selected_furniture: List[Dict]) -> Dict[str, List[int]]:
    """
    Per ruolo, la lista (espansa per quantità) dei throughput delle postazioni possedute.
    Solo furniture con is_workstation=True.

    Es. con 3 Checkout (30) + 2 Cash Register (20) + 1 Cleaning Station (0):
      {'Customer Service': [30, 30, 30, 20, 20], 'Cleaning': [0]}

    Da qui si ricava tutto:
      - n° postazioni del ruolo  = len(lista)          -> Vincolo A
      - capacità per il greedy   = lista ordinata desc -> Vincolo B
    """
    role_caps = defaultdict(list)

    for furn in selected_furniture:
        if not furn.get('is_workstation', False):
            continue
        capacity = furn.get('unit_capacity', 0)
        quantity = furn.get('quantity', 1)

        for role in furn.get('suitable_skills', []):
            role_caps[role].extend([capacity] * quantity)

    return dict(role_caps)


# ============================================================================
# INSURANCE LEVELS
# ============================================================================

INSURANCE_LEVELS = ['bronze', 'silver', 'gold']


# ============================================================================
# DEMAND PRIORITIES
# ============================================================================

DEMAND_PRIORITIES = ['critical', 'important', 'nice_to_have']


# ============================================================================
# SCHEDULE DEMANDS
# ============================================================================

SCHEDULE_DEMANDS = {
    'part_time': 'Part-time (10-30 hours/week)',
    'full_time': 'Full-time (30-50 hours/week)',
    'four_days': 'Four days week',
    'five_days': 'Five days week',
    'no_morning': 'No morning shifts (6:00-10:00)',
    'no_afternoon': 'No afternoon shifts (14:00-16:00)',
    'no_evening': 'No evening shifts (18:00-22:00)',
    'no_night': 'No night shifts (22:00-4:00)',
    'free_weekend': 'Free weekend (no Sat/Sun)',
    'no_cleaning': 'No cleaning shifts'
}


# ============================================================================
# BENEFITS DEMANDS
# ============================================================================

BENEFITS_DEMANDS = {
    'bronze_insurance': 'Bronze Health Insurance or higher',
    'silver_insurance': 'Silver Health Insurance or higher',
    'gold_insurance': 'Gold Health Insurance'
}


# ============================================================================
# ENVIRONMENT DEMANDS
# ============================================================================

ENVIRONMENT_DEMANDS = {
    'peaceful_environment': 'Peaceful work environment (owner happiness ≥ 50%)',
    'clean_environment': 'Clean work environment (cleanliness ≥ 80%)'
}


# ============================================================================
# EQUIPMENT DEMANDS
# ============================================================================

EQUIPMENT_DEMANDS = [
    'Cheap Coffee Machine',
    'Classic Phone',
    'Computer Monitor',
    'Executive Office Desk',
    'Graphic Tablet',
    'Graphic Tablet (with Screen)',
    'Meeting Table (Large)',
    'Modular Sofa 1',
    'Mouse Pad',
    'Multipurpose Chair',
    'Office Chair',
    'Office Phone',
    'Preben Sofa',
    'Standard Fridge',
    'Standard Office Desk',
    'Stump Mesh Office Chair',
    'Water Cooler'
]


# ============================================================================
# ALL DEMANDS (Combined)
# ============================================================================

def get_all_demands_by_category() -> Dict[str, Dict[str, str]]:
    """Get all available demands organized by category"""
    return {
        'schedule': SCHEDULE_DEMANDS,
        'benefits': BENEFITS_DEMANDS,
        'environment': ENVIRONMENT_DEMANDS,
        'equipment': {item: item for item in EQUIPMENT_DEMANDS}
    }


# ============================================================================
# DAYS OF WEEK
# ============================================================================

DAYS_OF_WEEK = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday'
]


# ============================================================================
# DEFAULT HOURS
# ============================================================================

DEFAULT_START_HOUR = 8
DEFAULT_END_HOUR = 22
