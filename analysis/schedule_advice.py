"""
Schedule advice — consigli generali derivati dai FATTI del solver.

Nessun hardcoding per scenario e nessuna dipendenza dal file caricato o dai nomi
dei business: legge solo cio' che `optimize_schedule_variable` ha gia' calcolato
(richieste non soddisfatte, copertura, capping organico, scartati) e produce una
lista di consigli strutturati. Le stesse regole, su fatti diversi, danno consigli
diversi -> si adattano da soli a qualunque configurazione.

Quantificazione in ORE/TESTE (niente dollari): la parte economica col fatturato
reale e' parcheggiata per piu' avanti.

NB: il testo dei consigli e' in INGLESE (compare nel pannello UI); la console
dell'app puo' stamparli con `format_console`.
"""
from dataclasses import dataclass, field
from math import ceil
from typing import List, Dict, Optional


PART_TIME_CAP = 30  # ore settimanali massime per un part-time (banda 10-30)

# fasce orarie "vietate" per ciascuna richiesta avoid (per ora di inizio)
AVOID_TYPES = {
    'no_morning': {'morning'},
    'no_afternoon': {'afternoon'},
    'no_evening': {'afternoon', 'night'},
    'no_night': {'night'},
    'no_cleaning': {'night'},
}

# etichette leggibili in inglese
CONSTRAINT_LABEL = {
    'free_weekend': 'free weekend',
    'no_morning': 'no morning shifts',
    'no_afternoon': 'no afternoon shifts',
    'no_evening': 'no evening shifts',
    'no_night': 'no night shifts',
    'no_cleaning': 'no cleaning shifts',
    'four_days': 'max 4 days/week',
    'five_days': 'max 5 days/week',
    'full_time': 'full-time',
    'part_time': 'part-time',
}


@dataclass
class Recommendation:
    kind: str                 # 'unmet' | 'coverage' | 'capacity' | 'dropped' | 'margin'
    severity: str             # 'high' | 'medium' | 'low' | 'info'
    title: str                # short English headline
    detail: str = ""          # explanation (English)
    suggestion: str = ""      # actionable advice (English)


# --------------------------------------------------------------------------- #
# helper
# --------------------------------------------------------------------------- #

def _hour_bucket(h: int) -> str:
    hh = h % 24
    if hh < 12:
        return 'morning'
    if hh < 18:
        return 'afternoon'
    return 'night'


def _band_hi(emp) -> int:
    cons = {d.constraint for d in emp.demands if d.category == 'schedule'}
    if 'full_time' in cons:
        return 50
    if 'part_time' in cons:
        return 30
    return 50


def _forbidden_region(constraint: str, open_days: List[str],
                      open_hours: Dict[str, List[int]]):
    """Lista di (giorno, ora) vietati da una richiesta avoid/free_weekend."""
    if constraint == 'free_weekend':
        return [(d, h) for d in ('Saturday', 'Sunday') if d in open_days
                for h in open_hours.get(d, [])]
    if constraint in AVOID_TYPES:
        types = AVOID_TYPES[constraint]
        return [(d, h) for d in open_days for h in open_hours.get(d, [])
                if _hour_bucket(h) in types]
    return []


def _region_demand_hours(demand: Dict, role: str, region) -> float:
    return float(sum(demand.get((role, d, h), 0) for (d, h) in region))


def _free_capacity(role: str, region, constraint: str,
                   emps_by_role: Dict[str, list], max_shift_len: int) -> float:
    """Ore che i colleghi dello STESSO ruolo SENZA quel vincolo possono coprire
    nella regione vietata. Stima: ogni collega copre al massimo un turno/giorno
    della regione, limitato dalla sua banda contrattuale."""
    region_days = {d for (d, _) in region}
    per_emp_cap = len(region_days) * max_shift_len
    total = 0.0
    for e in emps_by_role.get(role, []):
        cons = {d.constraint for d in e.demands if d.category == 'schedule'}
        if constraint in cons:
            continue  # ha lo stesso vincolo: non e' "libero"
        total += min(_band_hi(e), per_emp_cap)
    return total


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #

def build_recommendations(
    employees: list,
    schedule: Dict[str, Dict[str, list]],
    demand: Dict,
    demand_info: Dict[str, dict],
    coverage_report: Optional[Dict[str, dict]],
    unmet_soft: list,                 # (uid, name, constraint, priority, points)
    open_days: List[str],
    open_hours: Dict[str, List[int]],
    max_shift_len: int = 8,
    business_name: str = "",
    econ: Optional[Dict] = None,       # (role,day,h) -> ppc*min(throughput,flusso)
    ppc: float = 0.0,                  # profitto/cliente stimato (da prezzi prodotto)
) -> List[Recommendation]:
    """Costruisce i consigli dai soli fatti del solver. Vedi modulo docstring."""
    recs: List[Recommendation] = []

    emp_by_uid = {e.uid: e for e in employees}
    emps_by_role: Dict[str, list] = {}
    for e in employees:
        emps_by_role.setdefault(e.role, []).append(e)

    # 1) RICHIESTE NON SODDISFATTE ----------------------------------------- #
    days_unmet: Dict[str, dict] = {}   # role -> {names, cons, sev} (aggregati dopo)
    for uid, name, c, prio, pts in unmet_soft:
        emp = emp_by_uid.get(uid)
        role = emp.role if emp else None
        label = CONSTRAINT_LABEL.get(c, c)
        sev = 'high' if prio == 'important' else 'low'

        if c in AVOID_TYPES or c == 'free_weekend':
            region = _forbidden_region(c, open_days, open_hours)
            required = _region_demand_hours(demand, role, region) if role else 0
            supply = _free_capacity(role, region, c, emps_by_role, max_shift_len) if role else 0
            deficit = max(0.0, required - supply)
            where = 'the weekend' if c == 'free_weekend' else f'their off-limits shifts'
            if deficit > 0:
                heads = max(1, ceil(deficit / PART_TIME_CAP))
                per = int(round(deficit / heads))
                recs.append(Recommendation(
                    kind='unmet', severity=sev,
                    title=f"{name}: '{label}' not honored",
                    detail=(f"{role} coverage on {where} needs ~{required:.0f} staff-hours, "
                            f"but colleagues without this request can supply only ~{supply:.0f}h. "
                            f"Someone with the request has to work it."),
                    suggestion=(f"Hire ~{heads} weekend-capable part-timer(s) (~{per}h each) "
                                f"for this role — or close/shorten a day, or rotate who covers "
                                f"{where} week to week."),
                ))
            else:
                recs.append(Recommendation(
                    kind='unmet', severity='low',
                    title=f"{name}: '{label}' not honored",
                    detail=("There is spare staff without this request, so this is a cost "
                            "choice, not a coverage gap: honoring it was cheaper to skip."),
                    suggestion=("Raise the satisfaction weight (beta) if you want to force it, "
                                "accepting a slightly higher wage bill."),
                ))
        elif c in ('four_days', 'five_days'):
            # aggregati per ruolo (evita 5 righe quasi identiche)
            key = role or '—'
            d = days_unmet.setdefault(key, {'names': [], 'cons': set(), 'sev': 'low'})
            d['names'].append(name)
            d['cons'].add(c)
            if sev == 'high':
                d['sev'] = 'high'
        else:
            recs.append(Recommendation(
                kind='unmet', severity=sev,
                title=f"{name}: '{label}' not honored",
                suggestion="Review this request against current coverage needs.",
            ))

    # 1b) richieste "giorni/settimana" aggregate per ruolo ----------------- #
    for role, d in days_unmet.items():
        n = len(d['names'])
        cons_lbl = ' / '.join(CONSTRAINT_LABEL.get(c, c) for c in sorted(d['cons']))
        recs.append(Recommendation(
            kind='unmet', severity=d['sev'],
            title=f"{n} {role} work more days than requested",
            detail=(f"{', '.join(d['names'])} exceed their requested days ({cons_lbl}): "
                    f"{role} is stretched across the week, so they pick up an extra day."),
            suggestion=(f"Add distinct {role} staff (even part-time) so the open days can be "
                        f"spread across more people."),
        ))

    # 2) GAP DI COPERTURA REALI -------------------------------------------- #
    for role, info in (coverage_report or {}).items():
        real = info.get('real', 0) or 0
        if real > 1e-6:
            recs.append(Recommendation(
                kind='coverage', severity='high',
                title=f"{role}: understaffed",
                detail=f"~{real:.0f} staff-hours go uncovered for {role}.",
                suggestion=f"Hire ~+{info.get('suggest', 1)} {role} staff to close the gap.",
            ))

    # 3) CAPPING ORGANICO (sotto al picco) --------------------------------- #
    for role, di in (demand_info or {}).items():
        ideal = di.get('ideal', 0)
        cap = di.get('cap', 0)
        if ideal > cap and cap > 0:
            recs.append(Recommendation(
                kind='capacity', severity='medium',
                title=f"{role}: capacity below peak demand",
                detail=(f"Ideal coverage is ~{ideal:.0f}h but your {role} team can only deliver "
                        f"~{cap:.0f}h, so peak hours are thinned out."),
                suggestion=f"Add {role} headcount or longer shifts to fully cover peaks.",
            ))

    # 4) SCARTATI ----------------------------------------------------------- #
    dropped = [e.name for e in employees
               if not any(schedule.get(e.uid, {}).get(d) for d in open_days)]
    if dropped:
        recs.append(Recommendation(
            kind='dropped', severity='info',
            title=f"{len(dropped)} employee(s) not scheduled",
            detail=("They were not needed to meet minimum coverage at lowest wage cost: "
                    + ", ".join(dropped) + "."),
            suggestion=("Normal when you pay only scheduled hours. If you pay them regardless, "
                        "switch the objective to use the whole hired team."),
        ))

    # 5) MARGINE DI SERVIZIO (opzionale) ----------------------------------- #
    for role, info in (coverage_report or {}).items():
        opt = info.get('optional', 0) or 0
        if opt > 1e-6:
            recs.append(Recommendation(
                kind='margin', severity='low',
                title=f"{role}: service margin available",
                detail=f"~{opt:.0f} extra staff-hours could serve more customers at peak.",
                suggestion=f"Optional: more {role} staff would lift throughput (revenue upside).",
            ))

    # 6) ORE DI BORDO CHE NON COPRONO IL LAVORO (margin-aware) ------------- #
    # Segnala SOLO le ore ai bordi dell'apertura dove il margine STIMATO di un
    # addetto (ppc x clienti attesi) non copre nemmeno il suo salario. Niente
    # ledger: ppc viene dai prezzi prodotto (dati di gioco) e i clienti dalla
    # curva di domanda -> stima forward, da rivedere in gioco. Se ppc<=0 (non
    # disponibile) la regola NON si attiva (non inventa). Salta gli overnight.
    if business_name and ppc and ppc > 0 and econ:
        all_hours = [h for d in open_days for h in open_hours.get(d, [])]
        overnight = any(h >= 24 for h in all_hours)
        selling_roles = {r for (r, _, _) in econ.keys()}
        sell_wages = [e.hourly_wage for e in employees if e.role in selling_roles]
        if all_hours and not overnight and sell_wages:
            min_wage = min(sell_wages)  # costo di 1 addetto vendita per un'ora
            hours_set = sorted(set(all_hours))
            lo, hi = hours_set[0], hours_set[-1]

            def _avg_margin(hour: int) -> float:
                vals = []
                for d in open_days:
                    if hour in open_hours.get(d, []):
                        vals.append(max((econ.get((r, d, hour), 0.0)
                                         for r in selling_roles), default=0.0))
                return sum(vals) / len(vals) if vals else 0.0

            # conta le ore in perdita CONTIGUE dai due bordi (margine < salario)
            early = 0
            h = lo
            while h <= hi and _avg_margin(h) < min_wage:
                early += 1
                h += 1
            late = 0
            h = hi
            while h >= lo and _avg_margin(h) < min_wage:
                late += 1
                h -= 1
            # non suggerire di chiudere tutto: solo se restano ore "buone" in mezzo
            if early + late > 0 and (early + late) < len(hours_set):
                n_days = len(open_days)
                trimmed = early + late
                new_start, new_end = lo + early, hi - late + 1
                wasted = trimmed * n_days
                recs.append(Recommendation(
                    kind='hours', severity='medium',
                    title="Some opening hours don't cover their labor",
                    detail=(f"You open {lo:02d}:00–{hi + 1:02d}:00. At the fringes the estimated "
                            f"margin (~${ppc:.0f}/customer × expected customers) is below the cost "
                            f"of one server, so those hours lose money on staffing."),
                    suggestion=(f"Consider trimming toward {new_start:02d}:00–{new_end:02d}:00 "
                                f"(~{wasted:.0f} staff-hours/week, estimated) to cut wage cost. "
                                f"This is a forward estimate — check the real numbers in-game."),
                ))

    return recs


# --------------------------------------------------------------------------- #
# rendering console (IT-friendly, ma testo dei consigli in EN)
# --------------------------------------------------------------------------- #

SEV_TAG = {'high': '⚠', 'medium': '•', 'low': '·', 'info': 'ℹ'}


def format_console(recs: List[Recommendation]) -> List[str]:
    if not recs:
        return ["  [Advice] No issues: schedule is clean."]
    lines = ["  [Advice] Recommendations:"]
    for r in recs:
        lines.append(f"    {SEV_TAG.get(r.severity, '-')} {r.title}")
        if r.suggestion:
            lines.append(f"        → {r.suggestion}")
    return lines
