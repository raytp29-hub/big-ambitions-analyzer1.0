"""
analysis/staffing_fit.py
Personale teorico ORA PER ORA contro i turni reali del save.

Idea: per ogni ruolo e per ogni ora della settimana
    serve   = postazioni necessarie per i clienti di quell'ora
    in turno = persone che il save mette su quel ruolo a quell'ora
e la differenza dice dove paghi personale inutile (sovra-organico) o dove
manca gente (sotto-organico).

Da dove vengono i dati:
    clienti/ora   → hour_reports (clienti REALI, media per giorno della
                    settimana × ora nella finestra); se mancano, curva del
                    gioco = capacità × moltiplicatore orario × giornaliero
    postazioni    → snapshot.furniture (oggetti piazzati) + game data
                    (assignable, addedCustomersPerHour, suitableSkills)
    turni e ruolo → snapshot.shifts.station_item_key → suitableSkills
    orari         → snapshot.opening_hours

Tipi di ruolo (stessa logica di schedule_constraints, niente nomi hardcoded):
    sales        postazioni con throughput > 1 (cassa 20/h): serve
                 max(1, postazioni necessarie al flusso) in ogni ora aperta
    appointment  throughput 1 (computer di uffici: lawyer, designer...): stessa
                 formula, ma hour_reports conta gli ARRIVI, non il tempo che il
                 cliente passa col professionista → indicativo, mai "errore"
    presence     throughput 0 (cleaning, security, macchine): 1 persona in
                 ogni ora aperta (ipotesi del modello → solo informativo)

Il giorno della settimana di un giorno di gioco è (day - 1) % 7 + 1
(1 = lunedì). Verificato sul save: con questo allineamento zero clienti
cadono fuori dagli orari di apertura.
"""

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd

from analysis.business_alerts import DAY_NAMES, format_hour_ranges, hours_in_slot
from analysis.schedule_constraints import _hourly_multiplier_at, _stations_needed
from core.data_loader import DataBundle


# ============================================================================
# COSTANTI
# ============================================================================

MAX_SHIFT_LEN = 8          # ore max di un turno (come lo Schedule Optimizer)
MAX_WEEKLY_HOURS = 50      # ore max per dipendente a settimana

# Soglie sul rapporto ore in turno / ore necessarie (per ruolo, a settimana)
OVER_WARN = 1.25           # oltre +25% di ore → avviso
OVER_BAD = 1.60            # oltre +60% → errore
UNDER_OK = 0.85            # sotto l'85% → sotto-organico (warn), sotto 60% bad

# Margine sui clienti: dentro l'ora i clienti non arrivano uniformi, quindi il
# fabbisogno si calcola su clienti × 1.25 (una cassa da 20/h regge ~16 clienti).
# Parametro del modello, da calibrare in gioco.
NEED_BUFFER = 1.25

CLEANING_SKILL = "ba:skill_cleaning"


# ============================================================================
# DATACLASS
# ============================================================================

@dataclass(frozen=True)
class Station:
    item_key: str
    role: str              # nome leggibile del ruolo ("Customer Service")
    throughput: int        # clienti/ora serviti da UNA persona su questa postazione


@dataclass(frozen=True)
class HourGap:
    """Un'ora in cui il personale in turno non corrisponde al necessario."""
    role: str
    day: int               # 1-7
    hour: int
    staffed: int
    needed: int
    customers: float

    @property
    def diff(self) -> int:
        return self.staffed - self.needed


@dataclass(frozen=True)
class RoleStaffing:
    role: str
    kind: str                  # "sales" | "appointment" | "presence"
    stations: int
    peak_needed: int           # max persone necessarie nella stessa ora
    peak_staffed: int
    hours_needed: int          # ore-persona/settimana necessarie
    hours_staffed: int         # ore-persona/settimana in turno
    headcount_needed: int      # dipendenti necessari (vedi theoretical_headcount)
    headcount_actual: int      # dipendenti distinti con turni su questo ruolo
    over_hours: int            # ore-persona in più del necessario
    under_hours: int           # ore-persona mancanti
    wasted_per_week: float     # over_hours × salario medio del ruolo
    cost_per_week: float = 0.0 # hours_staffed × salario medio del ruolo

    @property
    def status(self) -> str:
        # Presenza (cleaning, security): la regola "1 persona ogni ora aperta"
        # è un'ipotesi del modello, non un dato del gioco → solo informativa,
        # tranne quando la postazione c'è ma nessuno ci lavora mai.
        if self.kind == "presence":
            return "warn" if self.hours_needed and self.hours_staffed == 0 else "info"
        if self.hours_needed == 0:
            return "info"
        ratio = self.hours_staffed / self.hours_needed
        if ratio < 0.60 or ratio > OVER_BAD:
            status = "bad"
        elif ratio < UNDER_OK or ratio > OVER_WARN:
            status = "warn"
        else:
            status = "ok"
        if self.kind == "appointment" and status == "bad":
            return "warn"
        return status


@dataclass(frozen=True)
class StaffingResult:
    customers_source: str                  # "observed" | "game curve"
    roles: list = field(default_factory=list)     # list[RoleStaffing]
    gaps: list = field(default_factory=list)      # list[HourGap], solo ore con diff != 0
    cells: list = field(default_factory=list)     # list[HourGap], TUTTE le ore valutate (anche diff 0)

    @property
    def wasted_per_week(self) -> float:
        """Solo i ruoli "sales": lì il fabbisogno viene dai clienti ed è affidabile."""
        return sum(r.wasted_per_week for r in self.roles if r.kind == "sales")

    @property
    def wage_bill_per_week(self) -> float:
        return sum(r.cost_per_week for r in self.roles)

    @property
    def wasted_share(self) -> float:
        """Quota del monte salari settimanale pagata per ore in più (ruoli sales)."""
        bill = self.wage_bill_per_week
        return self.wasted_per_week / bill if bill > 0 else 0.0

    def over_ranges(self, role: Optional[str] = None, min_diff: int = 1) -> list[str]:
        return _ranges([g for g in self.gaps if g.diff >= min_diff and (role is None or g.role == role)])

    def under_ranges(self, role: Optional[str] = None) -> list[str]:
        return _ranges([g for g in self.gaps if g.diff < 0 and (role is None or g.role == role)])

    def grid(self, role: str) -> dict:
        """
        Matrici 7×24 (lunedì→domenica × ore 0-23) per la heatmap di un ruolo:
        diff = in turno − necessari, più staffed / needed / customers per il tooltip.
        None dove il negozio è chiuso e nessuno è in turno (cella vuota).
        """
        def empty():
            return [[None] * 24 for _ in range(7)]
        out = {"diff": empty(), "staffed": empty(), "needed": empty(), "customers": empty()}
        for c in self.cells:
            if c.role != role or not 1 <= c.day <= 7:
                continue
            d, h = c.day - 1, c.hour % 24
            out["diff"][d][h] = c.diff
            out["staffed"][d][h] = c.staffed
            out["needed"][d][h] = c.needed
            out["customers"][d][h] = round(c.customers, 1)
        return out

    def top_over_ranges(self, n: int = 3) -> list[str]:
        """Le fasce di sovra-organico dei ruoli di vendita che costano più ore."""
        sales = {r.role for r in self.roles if r.kind == "sales"}
        over = [g for g in self.gaps if g.diff > 0 and g.role in sales]
        return [text for text, _ in sorted(_ranges(over, with_weight=True), key=lambda x: -x[1])[:n]]


# ============================================================================
# POSTAZIONI E RUOLI
# ============================================================================

def _default_item_lookup(key: str) -> Optional[dict]:
    from core.game_data import get_item_by_id
    return get_item_by_id(key)


def _default_skill_name(skill: str) -> str:
    from core.game_data import skill_display
    return skill_display(skill)


def business_skills(biz_name: str) -> set[str]:
    """Skill del tipo di business (+ cleaning, sempre presente)."""
    from core.game_data import _get_business_type
    bt = _get_business_type(biz_name) or {}
    return set(bt.get("employeePrimarySkills", [])) | {CLEANING_SKILL}


def station_for(
    item_key: str,
    skills: set[str],
    item_lookup: Callable[[str], Optional[dict]] = _default_item_lookup,
    skill_name: Callable[[str], str] = _default_skill_name,
) -> Optional[Station]:
    """
    None se l'oggetto non è una postazione. Il computer vale per 10 skill
    (lawyer, programmer...): si sceglie quella del tipo di business.
    """
    item = item_lookup(item_key) if item_key else None
    if not item or not item.get("assignable"):
        return None
    item_skills = item.get("suitableSkills") or []
    chosen = next((s for s in item_skills if s in skills), item_skills[0] if item_skills else None)
    if chosen is None:
        return None
    return Station(item_key, skill_name(chosen), int(item.get("addedCustomersPerHour") or 0))


def role_stations(furniture: dict[str, int], skills: set[str], **lookups) -> dict[str, list[int]]:
    """{ruolo: [throughput, ...]} espanso per quantità, dagli oggetti piazzati."""
    result: dict[str, list[int]] = {}
    for key, count in furniture.items():
        st = station_for(key, skills, **lookups)
        if st:
            result.setdefault(st.role, []).extend([st.throughput] * int(count))
    return result


# ============================================================================
# CLIENTI PER ORA
# ============================================================================

def weekday(day: int) -> int:
    """Giorno di gioco → 1..7 (1 = lunedì)."""
    return (int(day) - 1) % 7 + 1


def observed_customers(hour_reports: Optional[pd.DataFrame], business_name: str,
                       days: list[int]) -> dict[tuple[int, int], float]:
    """
    Media clienti per (giorno settimana, ora) sui giorni della finestra.
    hour_reports ha righe solo per le ore con clienti: si divide per quante
    volte quel giorno della settimana compare nella finestra, non per le righe.
    """
    if hour_reports is None or hour_reports.empty or not days:
        return {}
    mine = hour_reports[(hour_reports["business_name"] == business_name)
                        & hour_reports["day"].isin(days)]
    occurrences: dict[int, int] = {}
    for d in days:
        occurrences[weekday(d)] = occurrences.get(weekday(d), 0) + 1
    totals: dict[tuple[int, int], float] = {}
    for r in mine.itertuples():
        k = (weekday(r.day), int(r.hour))
        totals[k] = totals.get(k, 0.0) + float(r.customers)
    return {k: v / occurrences[k[0]] for k, v in totals.items()}


def curve_customers(biz_name: str, capacity: int) -> dict[tuple[int, int], float]:
    """Fallback: capacità × moltiplicatore orario × giornaliero (curva del gioco)."""
    from core.game_data import get_demand_multipliers
    mults = get_demand_multipliers(biz_name)
    if not mults:
        return {}
    daily = {d["day"]: d["multiplier"] for d in mults["daily"]}
    return {
        (d, h): capacity * _hourly_multiplier_at(h, mults["hourly"]) * daily.get(d, 1.0)
        for d in range(1, 8) for h in range(24)
    }


# ============================================================================
# FABBISOGNO E CONFRONTO
# ============================================================================

def role_kind(throughputs: list[int]) -> str:
    top = max(throughputs, default=0)
    if top > 1:
        return "sales"
    return "appointment" if top == 1 else "presence"


def hourly_need(throughputs: list[int], customers: float) -> int:
    """Persone necessarie in un'ora aperta per un ruolo."""
    if not throughputs:
        return 0
    if max(throughputs) <= 0:                    # presenza: cleaning, security, macchine
        return 1
    return min(len(throughputs), max(1, _stations_needed(throughputs, customers * NEED_BUFFER)))


def theoretical_headcount(peak: int, hours: int, longest_day: int, open_days: int) -> int:
    """
    Dipendenti necessari = il massimo fra tre vincoli (come
    compute_staffing_recommendation dello Schedule Optimizer):
      - picco: quante persone nella stessa ora
      - copertura: una giornata lunga 14h con turni da max 8h ne richiede 2
      - monte ore: ore totali / ore max per dipendente
    """
    if hours <= 0:
        return 0
    per_emp = min(MAX_WEEKLY_HOURS, open_days * MAX_SHIFT_LEN) or MAX_SHIFT_LEN
    return max(peak, math.ceil(longest_day / MAX_SHIFT_LEN), math.ceil(hours / per_emp))


def _ranges(gaps: list[HourGap], with_weight: bool = False) -> list:
    """Raggruppa ore consecutive con lo stesso quadro: 'Sun 14:00-18:00: 3 on shift, 1 needed (~13 cust/h)'."""
    by_key: dict[tuple, list[HourGap]] = {}
    for g in sorted(gaps, key=lambda g: (g.role, g.day, g.hour)):
        by_key.setdefault((g.role, g.day, g.staffed, g.needed), []).append(g)
    lines = []
    for (role, day, staffed, needed), items in by_key.items():
        avg = sum(g.customers for g in items) / len(items)
        hours = format_hour_ranges(g.hour for g in items)
        text = (f"{DAY_NAMES.get(day, day)} {hours}: {staffed} {role} on shift, "
                f"{needed} needed (~{avg:.0f} customers/h)")
        weight = abs(staffed - needed) * len(items)       # ore-persona in più/in meno
        lines.append((day, items[0].hour, text, weight))
    lines.sort()
    if with_weight:
        return [(text, weight) for _, _, text, weight in lines]
    return [text for _, _, text, _ in lines]


def compare_staffing(
    stations: dict[str, list[int]],
    open_hours: dict[int, set],
    shifts: pd.DataFrame,                  # turni del business, con colonna "role"
    customers: dict[tuple[int, int], float],
    wage_by_employee: dict[str, float],
    default_wage: float,
    customers_source: str = "observed",
) -> StaffingResult:
    # persone in turno per (ruolo, giorno, ora) e dipendenti per ruolo
    staffed: dict[tuple[str, int, int], int] = {}
    people: dict[str, set] = {}
    hours_by_emp_role: dict[tuple[str, str], int] = {}
    for s in shifts.itertuples():
        for h in hours_in_slot(s.start_hour, s.end_hour):
            k = (s.role, int(s.day), h)
            staffed[k] = staffed.get(k, 0) + 1
            hours_by_emp_role[(s.role, s.employee_id)] = hours_by_emp_role.get((s.role, s.employee_id), 0) + 1
        people.setdefault(s.role, set()).add(s.employee_id)

    open_days = sum(1 for hrs in open_hours.values() if hrs)
    longest_day = max((len(h) for h in open_hours.values()), default=0)

    roles, gaps, cells = [], [], []
    for role in sorted(set(stations) | set(people)):
        throughputs = stations.get(role, [])
        needed_by_hour: dict[tuple[int, int], int] = {}
        for day, hours in open_hours.items():
            for h in hours:
                needed_by_hour[(day, h)] = hourly_need(throughputs, customers.get((day, h), 0.0))

        # tutte le ore rilevanti: aperte + quelle con qualcuno in turno (anche a negozio chiuso)
        keys = set(needed_by_hour) | {(d, h) for (r, d, h) in staffed if r == role}
        over = under = 0
        for day, h in keys:
            n_staffed = staffed.get((role, day, h), 0)
            n_needed = needed_by_hour.get((day, h), 0)
            cell = HourGap(role, day, h, n_staffed, n_needed, customers.get((day, h), 0.0))
            cells.append(cell)
            if n_staffed != n_needed:
                gaps.append(cell)
            over += max(0, n_staffed - n_needed)
            under += max(0, n_needed - n_staffed)

        # salario medio del ruolo, pesato sulle ore in turno
        role_hours = {e: n for (r, e), n in hours_by_emp_role.items() if r == role}
        total_h = sum(role_hours.values())
        avg_wage = (sum(wage_by_employee.get(e, default_wage) * n for e, n in role_hours.items()) / total_h
                    if total_h else default_wage)

        hours_needed = sum(needed_by_hour.values())
        peak_needed = max(needed_by_hour.values(), default=0)
        roles.append(RoleStaffing(
            role=role,
            kind=role_kind(throughputs),
            stations=len(throughputs),
            peak_needed=peak_needed,
            peak_staffed=max((n for (r, _, _), n in staffed.items() if r == role), default=0),
            hours_needed=hours_needed,
            hours_staffed=sum(n for (r, _, _), n in staffed.items() if r == role),
            headcount_needed=theoretical_headcount(peak_needed, hours_needed, longest_day, open_days),
            headcount_actual=len(people.get(role, set())),
            over_hours=over,
            under_hours=under,
            wasted_per_week=over * avg_wage,
            cost_per_week=total_h * avg_wage,
        ))
    return StaffingResult(customers_source, roles, gaps, cells)


# ============================================================================
# ENTRY POINT
# ============================================================================

def evaluate_staffing(bundle: DataBundle, address: str, window_days: int = 7) -> Optional[StaffingResult]:
    """Tutto dal bundle: None se il business non è nel save o il tipo è sconosciuto."""
    from analysis.business_fit import _window, open_hours_by_day, resolve_business_profile

    snap = bundle.snapshot
    profile = resolve_business_profile(snap, address)
    if profile is None:
        return None
    skills = business_skills(profile.biz_name)

    furn = snap.furniture[snap.furniture["address"] == address]
    stations = role_stations(dict(zip(furn["item_key"], furn["count"])), skills)

    shifts = snap.shifts[snap.shifts["address"] == address].copy()
    shifts["role"] = [
        (st.role if (st := station_for(str(k) if pd.notna(k) else "", skills)) else "Unassigned station")
        for k in shifts["station_item_key"]
    ]

    days = _window(bundle.hour_reports, window_days)
    customers = observed_customers(bundle.hour_reports, profile.business_name, days)
    source = "observed"
    if not customers:
        customers, source = curve_customers(profile.biz_name, profile.capacity), "game curve"

    emp = snap.employees
    staff = emp[emp["address"] == address]
    default_wage = float(staff["hourly_wage"].mean()) if not staff.empty else 22.0

    return compare_staffing(
        stations, open_hours_by_day(snap, address), shifts, customers,
        dict(zip(emp["employee_id"], emp["hourly_wage"])), default_wage, source,
    )


def staffing_to_df(result: StaffingResult) -> pd.DataFrame:
    from analysis.business_fit import STATUS_ICON
    rows = [{
        "": STATUS_ICON[r.status],
        "Role": r.role,
        "Type": {"sales": "sales", "appointment": "appointment (indicative)",
                 "presence": "presence (1/h)"}[r.kind],
        "Stations": r.stations,
        "Peak (need / have)": f"{r.peak_needed} / {r.peak_staffed}",
        "Hours/week (need / have)": f"{r.hours_needed} / {r.hours_staffed}",
        "Employees (need / have)": f"{r.headcount_needed} / {r.headcount_actual}",
        "Extra hours": r.over_hours,
        "Missing hours": r.under_hours,
        "Wasted/week": f"${r.wasted_per_week:,.0f}",
    } for r in result.roles]
    return pd.DataFrame(rows)
