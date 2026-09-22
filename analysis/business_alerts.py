"""
analysis/business_alerts.py
Motore degli alert: trova i problemi dei business del player nel save .hsg.

Struttura:
    Alert           → un problema trovato (dataclass immutabile)
    AlertContext    → dati di contorno che servono ai check (nomi, requisiti
                      del gioco). Costruito una volta e PASSATO ai check:
                      nei test si crea a mano, senza leggere game_data.json
                      (dependency injection).
    check_xxx()     → una funzione pura per ogni tipo di problema:
                      (bundle, ctx) -> list[Alert]
    CHECKS          → il registry: la lista di tutti i check
    run_all_checks  → li esegue tutti e ordina per gravità

Per aggiungere un check: scrivi la funzione, aggiungila a CHECKS, scrivi il test.
Vedi claude/hsg-data-map.md per l'origine di ogni campo.
"""

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd

from core.data_loader import DataBundle
from core.hsg_reader import Names
from core.localization import display_name
from core.snapshot import Snapshot


# ============================================================================
# COSTANTI
# ============================================================================

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

# Tipi di business senza clienti: la loro satisfaction è fissa a 50 (default
# del gioco) e non ha senso controllarla. Gli uffici (law firm, graphic
# designer) NON sono qui: non hanno walk-in, ma la satisfaction è reale.
NON_CUSTOMER_TYPES = frozenset({
    "ba:businesstype_warehouse",
    "ba:businesstype_headquarters",
    "ba:businesstype_factory",
    "ba:businesstype_empty",
})

# Le chiavi ba:customerdemand_* non sono in en.json: etichette a mano.
DEMAND_LABELS = {
    "ba:customerdemand_music":           "Music",
    "ba:customerdemand_employeeuniforms": "Uniforms",
    "ba:customerdemand_interiordesign":  "Interior design",
    "ba:customerdemand_seating":         "Seating",
    "ba:customerdemand_toilet":          "Toilet",
    "ba:customerdemand_toiletprivacy":   "Toilet privacy",
    "ba:customerdemand_sink":            "Sink",
}

DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}

# Soglie (concordate 2026-09-22)
SAT_CRITICAL = 60
SAT_WARNING = 80
TREND_THRESHOLD_PCT = 15
TREND_MIN_DAYS = 14
CAPACITY_RATIO = 0.9
OVERSTAFF_MIN_WEEKLY = 300      # $/settimana di ore in più (ruoli sales) sotto cui si tace
OVERSTAFF_WARN_SHARE = 0.20     # ≥20% del monte salari pagato per ore inutili → warning


# ============================================================================
# DATACLASS
# ============================================================================

@dataclass(frozen=True)
class Alert:
    address: str        # chiave del business ("" se non legato a un business)
    business: str       # nome da mostrare
    severity: str       # "critical" | "warning" | "info"
    code: str           # identificativo stabile, es. "RENT_ON_EMPTY"
    message: str        # frase per l'utente
    evidence: str       # il dato che giustifica l'alert

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_ORDER:
            raise ValueError(
                f"severity must be one of {set(SEVERITY_ORDER)}, got {self.severity!r}"
            )


@dataclass(frozen=True)
class AlertContext:
    names: dict[str, str]                             # address → nome business
    demand_requirements: dict[str, dict[str, float]]  # business_type → {demand_key: weight}


def build_context(snapshot: Snapshot) -> AlertContext:
    """Contesto reale: nomi dallo snapshot, requisiti da game_data.json."""
    from core.game_data import get_all_business_types   # import qui: carica il JSON

    names = {
        row.address: (row.business_name or "Empty building")
        for row in snapshot.businesses.itertuples()
    }
    requirements = {}
    for bt in get_all_business_types():
        demand_sets = bt.get("customerDemandSets") or []
        if demand_sets:
            requirements[bt["businessTypeName"]] = {
                d["type"]: float(d.get("weight", 1)) for d in demand_sets
            }
    return AlertContext(names=names, demand_requirements=requirements)


# ============================================================================
# HELPER
# ============================================================================

def _active_businesses(snapshot: Snapshot, customer_only: bool = True) -> pd.DataFrame:
    """Business aperti; con customer_only esclude magazzini, HQ, fabbriche, building vuoti."""
    b = snapshot.businesses
    mask = ~b["temporarily_closed"]
    if customer_only:
        mask &= ~b["business_type"].isin(NON_CUSTOMER_TYPES)
    return b[mask]


def _address_by_name(snapshot: Snapshot) -> dict[str, str]:
    """item_sales, hour_reports e P&L usano il nome: serve la mappa nome → indirizzo."""
    return {
        row.business_name: row.address
        for row in snapshot.businesses.itertuples()
        if row.business_name
    }


def hours_in_slot(start: int, end: int) -> list[int]:
    """Ore coperte da una fascia [start, end). Gestisce i turni oltre mezzanotte."""
    if end == start:
        return []
    if end > start:
        return list(range(start, min(end, 24)))
    return list(range(start, 24)) + list(range(0, end))


def format_hour_ranges(hours) -> str:
    """{11, 12, 13, 18, 19} → '11:00-14:00, 18:00-20:00'"""
    hours = sorted(set(hours))
    if not hours:
        return ""
    ranges, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h == prev + 1:
            prev = h
            continue
        ranges.append((start, prev))
        start = prev = h
    ranges.append((start, prev))
    return ", ".join(f"{a:02d}:00-{b + 1:02d}:00" for a, b in ranges)


def demand_label(key: str) -> str:
    return DEMAND_LABELS.get(key) or key.split("_", 1)[-1].title()


def _street_label(address_key: str) -> str:
    """'ba:street_pier|2' → '2 Pier'"""
    if not address_key or "|" not in address_key:
        return address_key
    street, number = address_key.split("|", 1)
    return Names(locale={}).addr((street, int(number)))


# ============================================================================
# TABELLA DI SUPPORTO PER LA UI
# ============================================================================

def demand_status(snapshot: Snapshot, ctx: AlertContext) -> pd.DataFrame:
    """
    Una riga per business × domanda richiesta: soddisfatta sì/no.
    Alimenta sia il check 4 sia la griglia verde/rossa della Health Check.
    """
    fulfilled = set(zip(
        snapshot.fulfilled_demands["address"],
        snapshot.fulfilled_demands["demand_key"],
    ))
    rows = []
    for b in _active_businesses(snapshot).itertuples():
        for key, weight in ctx.demand_requirements.get(b.business_type, {}).items():
            rows.append({
                "address":    b.address,
                "business":   ctx.names.get(b.address, b.business_name),
                "demand_key": key,
                "demand":     demand_label(key),
                "weight":     weight,
                "fulfilled":  (b.address, key) in fulfilled,
            })
    columns = ["address", "business", "demand_key", "demand", "weight", "fulfilled"]
    return pd.DataFrame(rows, columns=columns)


# ============================================================================
# CHECK — uno per tipo di problema
# ============================================================================

def check_rent_waste(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """6. Affitto pagato per un building vuoto o per un business chiuso."""
    alerts = []
    for b in bundle.snapshot.businesses.itertuples():
        name = ctx.names.get(b.address, b.business_name or "Empty building")
        if b.business_type == "ba:businesstype_empty":
            alerts.append(Alert(
                b.address, name, "critical", "RENT_ON_EMPTY",
                "Paying rent for an empty building",
                f"${b.rent_per_day:,.0f}/day",
            ))
        elif b.temporarily_closed:
            alerts.append(Alert(
                b.address, name, "warning", "RENT_WHILE_CLOSED",
                "Business closed but still paying rent",
                f"${b.rent_per_day:,.0f}/day",
            ))
    return alerts


def check_unstaffed(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """7. Negozio senza personale: flag del gioco + ore aperte non coperte da turni."""
    snap = bundle.snapshot
    alerts = []
    active = _active_businesses(snap)

    for b in active[active["warned_no_employee"]].itertuples():
        alerts.append(Alert(
            b.address, ctx.names.get(b.address, b.business_name), "critical",
            "NO_EMPLOYEE_NOW", "The game reports nobody working here",
            "warnedLastHourAboutNoEmployee",
        ))

    oh = snap.opening_hours[snap.opening_hours["is_open"]]
    for address in active["address"]:
        uncovered_by_day = []
        for day in sorted(oh.loc[oh["address"] == address, "day"].unique()):
            day_slots = oh[(oh["address"] == address) & (oh["day"] == day)]
            open_hours = {
                h for s in day_slots.itertuples()
                for h in hours_in_slot(s.start_hour, s.end_hour)
            }
            day_shifts = snap.shifts[(snap.shifts["address"] == address) & (snap.shifts["day"] == day)]
            covered = {
                h for s in day_shifts.itertuples()
                for h in hours_in_slot(s.start_hour, s.end_hour)
            }
            gap = open_hours - covered
            if gap:
                uncovered_by_day.append(f"{DAY_NAMES.get(int(day), day)} {format_hour_ranges(gap)}")

        if uncovered_by_day:
            alerts.append(Alert(
                address, ctx.names.get(address, address), "warning", "UNCOVERED_HOURS",
                "Open hours with no staff scheduled",
                "; ".join(uncovered_by_day),
            ))
    return alerts


def check_losing_money(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """
    1. Profitto negativo nel periodo coperto dalle transazioni.
    Esclusi magazzini, HQ e fabbriche: non vendono direttamente, quindi nel
    P&L hanno solo costi e sarebbero sempre "in perdita" (falso positivo).
    """
    from analysis.profit_loss import calculate_profit_loss

    pl = calculate_profit_loss(bundle.transactions)
    if pl.empty:
        return []
    biz = bundle.snapshot.businesses
    customer_facing = set(biz.loc[~biz["business_type"].isin(NON_CUSTOMER_TYPES), "business_name"])
    by_name = {
        name: address for name, address in _address_by_name(bundle.snapshot).items()
        if name in customer_facing
    }
    days = bundle.transactions["day"]
    period = f"days {int(days.min())}-{int(days.max())}" if not days.empty else "the save"

    alerts = []
    for row in pl.itertuples():
        address = by_name.get(row.business)
        if address is None:          # es. "Unassigned": non è un business del player
            continue
        if row.profit < 0:
            alerts.append(Alert(
                address, row.business, "critical", "LOSING_MONEY",
                "Losing money",
                f"profit -${abs(row.profit):,.0f} over {period}",
            ))
    return alerts


def check_revenue_trend(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """2. Ricavi degli ultimi 7 giorni contro i 7 precedenti (±15%)."""
    sales = bundle.item_sales
    if sales is None or sales.empty:
        return []
    max_day, min_day = int(sales["day"].max()), int(sales["day"].min())
    if max_day - min_day + 1 < TREND_MIN_DAYS:
        return []

    last = sales[sales["day"] > max_day - 7]
    prev = sales[(sales["day"] > max_day - 14) & (sales["day"] <= max_day - 7)]
    last_rev = last.groupby("business_name")["total_price"].sum()
    prev_rev = prev.groupby("business_name")["total_price"].sum()
    by_name = _address_by_name(bundle.snapshot)

    alerts = []
    for name, prev_value in prev_rev.items():
        if prev_value <= 0:
            continue
        last_value = float(last_rev.get(name, 0.0))
        pct = (last_value - prev_value) / prev_value * 100
        evidence = f"{pct:+.0f}% (${prev_value:,.0f} → ${last_value:,.0f}, last 7 days vs previous 7)"
        if pct <= -TREND_THRESHOLD_PCT:
            alerts.append(Alert(by_name.get(name, ""), name, "warning", "REVENUE_DOWN",
                                "Revenue dropping", evidence))
        elif pct >= TREND_THRESHOLD_PCT:
            alerts.append(Alert(by_name.get(name, ""), name, "info", "REVENUE_UP",
                                "Revenue growing", evidence))
    return alerts


def check_low_satisfaction(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """3. Satisfaction bassa, indicando il sotto-punteggio peggiore."""
    alerts = []
    for b in _active_businesses(bundle.snapshot).itertuples():
        if b.sat_overall >= SAT_WARNING:
            continue
        subs = {
            "customer service": b.sat_customer_service,
            "pricing":          b.sat_pricing,
            "cleanliness":      b.sat_cleanliness,
            "facility":         b.sat_facility,
        }
        worst = min(subs, key=subs.get)
        severity = "critical" if b.sat_overall < SAT_CRITICAL else "warning"
        alerts.append(Alert(
            b.address, ctx.names.get(b.address, b.business_name), severity,
            "LOW_SATISFACTION", "Low customer satisfaction",
            f"overall {b.sat_overall:.0f}/100, lowest: {worst} {subs[worst]:.0f}",
        ))
    return alerts


def check_missing_demands(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """4. Domande dei clienti richieste dal tipo di business ma non soddisfatte."""
    status = demand_status(bundle.snapshot, ctx)
    missing = status[~status["fulfilled"]]
    alerts = []
    for address, group in missing.groupby("address", sort=False):
        severity = "warning" if group["weight"].max() >= 1 else "info"
        alerts.append(Alert(
            address, group["business"].iloc[0], severity, "MISSING_DEMANDS",
            "Customer demands not met",
            ", ".join(group["demand"]),
        ))
    return alerts


def check_promotion_below_cap(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """5. Promozione sotto il massimo."""
    alerts = []
    for b in _active_businesses(bundle.snapshot).itertuples():
        if b.promotion_total < 100:
            alerts.append(Alert(
                b.address, ctx.names.get(b.address, b.business_name), "info",
                "PROMOTION_BELOW_CAP", "Promotion below the cap",
                f"promotion {b.promotion_total:.0f}/100",
            ))
    return alerts


def check_at_capacity(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """8. Ore in cui i clienti arrivano al 90% della capacità oraria."""
    hr = bundle.hour_reports
    if hr is None or hr.empty:
        return []
    caps = {
        row.business_name: (row.address, row.customer_capacity)
        for row in _active_businesses(bundle.snapshot).itertuples()
        if row.business_name and 0 < row.customer_capacity < 999
    }
    alerts = []
    for name, (address, cap) in caps.items():
        rows = hr[hr["business_name"] == name]
        if rows.empty:
            continue
        hot = rows[rows["customers"] >= CAPACITY_RATIO * cap]
        if hot.empty:
            continue
        peak = rows.loc[rows["customers"].idxmax()]
        alerts.append(Alert(
            address, name, "warning", "AT_CAPACITY",
            "Hitting customer capacity — likely turning customers away",
            f"{len(hot)} hours at ≥{CAPACITY_RATIO:.0%} of capacity; "
            f"peak {int(peak['customers'])}/{cap} at {int(peak['hour']):02d}:00 (day {int(peak['day'])})",
        ))
    return alerts


def check_import_paused(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """9. Partnership di import inattive ma con quantità configurate."""
    imp = bundle.snapshot.imports
    paused = imp[(~imp["is_active"]) & (imp["amount"] > 0)]
    alerts = []
    for pid, group in paused.groupby("partnership_id", sort=False):
        items = ", ".join(
            f"{display_name(r.item_key)} {r.amount:,}" for r in group.itertuples()
        )
        address = group["import_address"].iloc[0]
        alerts.append(Alert(
            address, f"Import {_street_label(address)}", "warning", "IMPORT_PAUSED",
            "Import partnership paused with orders configured",
            items,
        ))
    return alerts


def check_staff_issues(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """10. Dimissioni in arrivo, lamentele, dipendenti senza assicurazione."""
    snap = bundle.snapshot
    known = set(snap.businesses["address"])
    emp = snap.employees[snap.employees["address"].isin(known)]
    alerts = []

    for e in emp[emp["quit_warning"]].itertuples():
        alerts.append(Alert(
            e.address, ctx.names.get(e.address, e.address), "critical", "QUIT_WARNING",
            f"{e.name} is about to quit",
            display_name(e.complaint_demand) if e.complaint_demand else "quit warning sent",
        ))

    for e in emp[emp["is_complaining"]].itertuples():
        alerts.append(Alert(
            e.address, ctx.names.get(e.address, e.address), "warning", "EMPLOYEE_COMPLAINT",
            f"{e.name} is complaining",
            display_name(e.complaint_demand) if e.complaint_demand else "unfulfilled demand",
        ))

    uninsured = emp[~emp["has_health_insurance"]].groupby("address").size()
    for address, count in uninsured.items():
        alerts.append(Alert(
            address, ctx.names.get(address, address), "info", "NO_HEALTH_INSURANCE",
            "Employees without health insurance",
            f"{count} employee{'s' if count > 1 else ''}",
        ))
    return alerts


# ============================================================================
# REGISTRY E RUNNER
# ============================================================================

def check_overstaffed_hours(bundle: DataBundle, ctx: AlertContext) -> list[Alert]:
    """
    11. Più persone in cassa (o al computer) di quante ne servano per i clienti
    reali di quell'ora. Il fabbisogno viene da analysis/staffing_fit.py.
    """
    from analysis.staffing_fit import evaluate_staffing   # import qui: evita il ciclo

    alerts = []
    for b in _active_businesses(bundle.snapshot).itertuples():
        result = evaluate_staffing(bundle, b.address)
        if result is None or result.wasted_per_week < OVERSTAFF_MIN_WEEKLY:
            continue
        worst = result.top_over_ranges(1)
        severity = "warning" if result.wasted_share >= OVERSTAFF_WARN_SHARE else "info"
        alerts.append(Alert(
            b.address, ctx.names.get(b.address, b.business_name), severity,
            "OVERSTAFFED_HOURS",
            "Paying for more staff than customers need",
            f"~${result.wasted_per_week:,.0f}/week ({result.wasted_share:.0%} of wages)"
            + (f" · worst: {worst[0]}" if worst else ""),
        ))
    return alerts


CHECKS = [
    check_rent_waste,
    check_unstaffed,
    check_losing_money,
    check_revenue_trend,
    check_low_satisfaction,
    check_missing_demands,
    check_promotion_below_cap,
    check_at_capacity,
    check_import_paused,
    check_staff_issues,
    check_overstaffed_hours,
]


def run_all_checks(bundle: DataBundle, ctx: Optional[AlertContext] = None) -> list[Alert]:
    """Esegue tutti i check. Senza snapshot (upload CSV) restituisce lista vuota."""
    if bundle is None or bundle.snapshot is None:
        return []
    ctx = ctx or build_context(bundle.snapshot)
    alerts = [alert for check in CHECKS for alert in check(bundle, ctx)]
    return sorted(alerts, key=lambda a: (SEVERITY_ORDER[a.severity], a.business, a.code))


def summarize(alerts: list[Alert]) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITY_ORDER}
    for a in alerts:
        counts[a.severity] += 1
    return counts


def alerts_to_df(alerts: list[Alert]) -> pd.DataFrame:
    columns = ["address", "business", "severity", "code", "message", "evidence"]
    return pd.DataFrame([asdict(a) for a in alerts], columns=columns)
