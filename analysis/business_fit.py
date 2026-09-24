"""
analysis/business_fit.py
"My business vs theory": prende un business VERO dal save .hsg e lo confronta
con il modello teorico di health_check.compute_bep.

Prima il planner chiedeva a mano tipo, taglia, zona e affitto. Ora li
ricaviamo dal save:
    snapshot.businesses  → tipo, affitto, capacità clienti
    game data buildings  → quartiere, trafficIndex, taglia (join su address)
e confrontiamo il teorico con i numeri reali:
    item_sales    → ricavo/giorno e prodotti venduti
    hour_reports  → clienti/giorno
    opening_hours → orari reali
    shifts + employees → personale e salari
    furniture     → arredi piazzati

Struttura (stessa filosofia di business_alerts):
    BusinessProfile             → gli input del modello, letti dal save
    resolve_business_profile()  → address → BusinessProfile
    ActualMetrics / actual_metrics() → i numeri reali in una finestra di giorni
    FitRow / compare_to_theory()     → la tabella Theory vs Actual
Le funzioni accettano il game data come parametro opzionale: nei test si
passano liste finte, senza caricare il JSON (dependency injection).
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from analysis.business_alerts import hours_in_slot
from core.data_loader import DataBundle
from core.snapshot import Snapshot


# ============================================================================
# COSTANTI
# ============================================================================

WINDOW_DAYS = 14         # finestra dei dati reali: 2 settimane intere (il save ne tiene ~16)
DEFAULT_WAGE = 22.0      # salario orario se il business non ha dipendenti

# Stesse fasce del rating di generate_report
OK_RATIO = 0.85
WARN_RATIO = 0.60

# Salari in % del ricavo: soglie assolute, non rispetto al modello
# (compute_bep conta solo le workstation, quindi sottostima il personale).
WAGE_SHARE_OK = 0.20
WAGE_SHARE_WARN = 0.35

STATUS_ICON = {"ok": "✅", "warn": "⚠️", "bad": "❌", "info": "ℹ️"}

NEIGHBOURHOOD_LABELS = {
    "ba:neighborhood_murrayhill":     "Murray Hill",
    "ba:neighborhood_industrycity":   "Industry City",
    "ba:neighborhood_midtown":        "Midtown",
    "ba:neighborhood_hellskitchen":   "Hell's Kitchen",
    "ba:neighborhood_lowermanhattan": "Lower Manhattan",
    "ba:neighborhood_garmentdistrict": "Garment District",
    "ba:neighborhood_thehamptons":    "The Hamptons",
}


# ============================================================================
# DATACLASS
# ============================================================================

@dataclass(frozen=True)
class BusinessProfile:
    """Gli input di compute_bep, ricavati dal save invece che dai selectbox."""
    address: str
    business_name: str
    business_type: str       # ba:businesstype_fastfoodrestaurant
    biz_name: str            # FastFoodRestaurant (m_Name, quello che vuole compute_bep)
    neighbourhood: str       # etichetta leggibile
    traffic: int             # trafficIndex del building (non la media della zona)
    building_size: str       # "A2", "" se il building non è nel game data
    capacity: int            # clienti/ora
    rent: float              # $/giorno


@dataclass(frozen=True)
class ActualMetrics:
    days: list                    # giorni di gioco nella finestra
    revenue_per_day: Optional[float]
    customers_per_day: Optional[float]
    items_sold: frozenset         # item_key venduti nella finestra
    open_hours: dict              # day (1-7) → set di ore aperte
    staff_assigned: int           # dipendenti assegnati al business
    peak_staff: int               # massimo di persone in turno nella stessa ora
    wages_per_open_day: float
    avg_hourly_wage: float
    furniture: dict = field(default_factory=dict)   # item_key → count


@dataclass(frozen=True)
class FitRow:
    metric: str
    theory: str
    actual: str
    status: str          # ok | warn | bad | info
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUS_ICON:
            raise ValueError(f"status must be one of {set(STATUS_ICON)}, got {self.status!r}")


# ============================================================================
# PROFILO: address → input del modello
# ============================================================================

def _default_buildings() -> list[dict]:
    from core.game_data import _game_data
    return _game_data["buildings"]


def _default_business_types() -> list[dict]:
    from core.game_data import get_all_business_types
    return get_all_business_types()


def _capacity_from_game_data(building: dict) -> int:
    """Fallback se il save ha customerCapacity = 0."""
    from core.game_data import _building_sizes_by_id, _find_capacity
    size = _building_sizes_by_id.get(building.get("BuildingSize"))
    if not size:
        return 0
    return _find_capacity(size, building.get("BuildingType"), building.get("BuildingVersion", 0))


def building_index(buildings: list[dict]) -> dict[str, dict]:
    """address key ('ba:street_fifthavenue|38') → record building del game data."""
    return {
        f"{b['StreetName']}|{int(b['StreetNumber'])}": b
        for b in buildings
        if b.get("StreetName") is not None
    }


def resolve_business_profile(
    snapshot: Snapshot,
    address: str,
    buildings: Optional[list[dict]] = None,
    business_types: Optional[list[dict]] = None,
) -> Optional[BusinessProfile]:
    """None se l'indirizzo non è fra i business del player o il tipo è sconosciuto."""
    rows = snapshot.businesses[snapshot.businesses["address"] == address]
    if rows.empty:
        return None
    biz = rows.iloc[0]

    business_types = business_types if business_types is not None else _default_business_types()
    bt = next((t for t in business_types if t.get("businessTypeName") == biz["business_type"]), None)
    if bt is None:
        return None

    buildings = buildings if buildings is not None else _default_buildings()
    building = building_index(buildings).get(address, {})

    size_key = building.get("BuildingSize") or ""
    size = ""
    if size_key:
        size = f"{size_key.rsplit('_', 1)[-1].upper()}{building.get('BuildingVersion', '')}"

    capacity = int(biz["customer_capacity"])
    if capacity <= 0 and building:
        capacity = _capacity_from_game_data(building)

    hood = building.get("Neighbourhood") or ""
    return BusinessProfile(
        address=address,
        business_name=str(biz["business_name"]),
        business_type=str(biz["business_type"]),
        biz_name=bt["m_Name"],
        neighbourhood=NEIGHBOURHOOD_LABELS.get(hood, hood.rsplit("_", 1)[-1].title() if hood else "?"),
        traffic=int(building.get("trafficIndex") or 0),
        building_size=size,
        capacity=capacity,
        rent=float(biz["rent_per_day"]),
    )


# ============================================================================
# NUMERI REALI
# ============================================================================

def _window(df: Optional[pd.DataFrame], window_days: int) -> list[int]:
    """Gli ultimi N giorni presenti nei dati (non quelli del singolo business:
    un giorno a zero vendite deve contare come zero, non sparire)."""
    if df is None or df.empty:
        return []
    last = int(df["day"].max())
    return [d for d in range(last - window_days + 1, last + 1) if d >= int(df["day"].min())]


def open_hours_by_day(snapshot: Snapshot, address: str) -> dict[int, set]:
    oh = snapshot.opening_hours
    oh = oh[(oh["address"] == address) & oh["is_open"]]
    result: dict[int, set] = {}
    for s in oh.itertuples():
        result.setdefault(int(s.day), set()).update(hours_in_slot(s.start_hour, s.end_hour))
    return result


def actual_metrics(bundle: DataBundle, address: str, window_days: int = WINDOW_DAYS) -> ActualMetrics:
    snap = bundle.snapshot
    name = snap.businesses.loc[snap.businesses["address"] == address, "business_name"]
    name = str(name.iloc[0]) if not name.empty else ""

    # --- ricavo e prodotti (item_sales) ---
    sales = bundle.item_sales
    days = _window(sales, window_days)
    revenue, items_sold = None, frozenset()
    if days:
        mine = sales[(sales["business_name"] == name) & sales["day"].isin(days)]
        revenue = float(mine["total_price"].sum()) / len(days)
        items_sold = frozenset(mine.loc[mine["amount_sold"] > 0, "item_key"])

    # --- clienti (hour_reports) ---
    hr = bundle.hour_reports
    hr_days = _window(hr, window_days)
    customers = None
    if hr_days:
        mine = hr[(hr["business_name"] == name) & hr["day"].isin(hr_days)]
        customers = float(mine["customers"].sum()) / len(hr_days)

    # --- orari, personale, salari (snapshot: settimana tipo) ---
    open_hours = open_hours_by_day(snap, address)

    emp = snap.employees
    staff = emp[emp["address"] == address]
    wage_by_id = dict(zip(emp["employee_id"], emp["hourly_wage"]))
    avg_wage = float(staff["hourly_wage"].mean()) if not staff.empty else DEFAULT_WAGE

    shifts = snap.shifts[snap.shifts["address"] == address]
    weekly_wages = 0.0
    per_hour: dict[tuple, int] = {}
    for s in shifts.itertuples():
        hours = hours_in_slot(s.start_hour, s.end_hour)
        weekly_wages += len(hours) * wage_by_id.get(s.employee_id, avg_wage)
        for h in hours:
            per_hour[(s.day, h)] = per_hour.get((s.day, h), 0) + 1
    open_days = len(open_hours) or 1

    furn = snap.furniture[snap.furniture["address"] == address]
    return ActualMetrics(
        days=days,
        revenue_per_day=revenue,
        customers_per_day=customers,
        items_sold=items_sold,
        open_hours=open_hours,
        staff_assigned=len(staff),
        peak_staff=max(per_hour.values(), default=0),
        wages_per_open_day=weekly_wages / open_days,
        avg_hourly_wage=avg_wage,
        furniture=dict(zip(furn["item_key"], furn["count"].astype(int))),
    )


# ============================================================================
# CONFRONTO
# ============================================================================

def ratio_status(actual: float, theory: float, higher_is_better: bool = True) -> str:
    """ok ≥ 85% del teorico, warn ≥ 60%, bad sotto. Per i costi il rapporto si inverte."""
    if theory <= 0 or actual is None:
        return "info"
    ratio = actual / theory if higher_is_better else (theory / actual if actual > 0 else 1.0)
    if ratio >= OK_RATIO:
        return "ok"
    if ratio >= WARN_RATIO:
        return "warn"
    return "bad"


def _norm(text: str) -> str:
    """'Cash Register' / 'ba:itemname_cashregister' / 'CashRegister' → 'cashregister'"""
    text = text.rsplit("_", 1)[-1] if text.startswith("ba:") else text
    return "".join(ch for ch in text.lower() if ch.isalnum())


def count_matching(furniture: dict[str, int], theory_name: str,
                   name_to_key: Optional[dict[str, str]] = None) -> int:
    """
    Quanti pezzi reali corrispondono a una riga di arredo teorica.
    BepResult ha solo il nome visualizzato ("Wooden Salad Bar"), il save ha
    la chiave ("ba:itemname_saladbar"): name_to_key traduce l'uno nell'altra.
    Se il nome non è nel game data (es. "Toilet" → toiletstall) si ripiega
    sul prefisso del nome normalizzato.
    """
    key = (name_to_key or {}).get(theory_name)
    if key:
        return int(furniture.get(key, 0))
    target = _norm(theory_name)
    return sum(n for k, n in furniture.items() if _norm(k).startswith(target))


def furniture_name_index() -> dict[str, str]:
    """Nome visualizzato e m_Name → itemName, per tutti gli item del game data."""
    from analysis.health_check import MANDATORY_FURNITURE
    from core.game_data import get_all_items, item_name

    index = {}
    for it in get_all_items():
        index[item_name(it)] = it["itemName"]
        index[it["m_Name"]] = it["itemName"]
    for mf in MANDATORY_FURNITURE:            # "Cash Register" → m_Name CashRegister
        if mf["internal"] in index:
            index[mf["name"]] = index[mf["internal"]]
    return index


def _money(x: Optional[float]) -> str:
    return "n/a" if x is None else f"${x:,.0f}"


def _hours_label(open_hour: int, close_hour: int) -> str:
    return f"{open_hour:02d}:00-{close_hour:02d}:00"


def compare_to_theory(
    profile: BusinessProfile,
    bep,                                   # health_check.BepResult (o None)
    actual: ActualMetrics,
    core_products: Optional[list] = None,  # [(item_key, label)] prodotti chiave del tipo
    name_to_key: Optional[dict[str, str]] = None,
    mandatory: frozenset = frozenset(),    # nomi degli arredi "obbligatori" del modello
    staffing=None,                         # staffing_fit.StaffingResult (personale ora per ora)
) -> list[FitRow]:
    if bep is None:
        return [FitRow(
            "Model", "no demand hours", "-", "info",
            "the game's demand curve never reaches the model threshold for this type: "
            "the theoretical model does not apply.",
        )]

    rows = []

    # 1. Ricavo
    rows.append(FitRow(
        "Daily revenue", _money(bep.revenue), _money(actual.revenue_per_day),
        ratio_status(actual.revenue_per_day, bep.revenue),
        f"avg over last {len(actual.days)} days" if actual.days else "no sales data",
    ))

    # 2. Clienti
    rows.append(FitRow(
        "Customers / day", f"{bep.daily_customers:,.0f}",
        "n/a" if actual.customers_per_day is None else f"{actual.customers_per_day:,.0f}",
        ratio_status(actual.customers_per_day, bep.daily_customers),
        f"capacity {profile.capacity}/h · traffic index {profile.traffic}",
    ))

    # 3. Orari: le ore del modello (heatmap della domanda, giorno per giorno,
    # vedi health_check.model_open_hours) confrontate con le tue, giorno per giorno.
    theory_hours = bep.open_hours
    wanted = sum(len(h) for h in theory_hours.values())
    theory_label = f"{len(theory_hours)} days · {wanted} h/week"
    if actual.open_hours and wanted:
        covered = sum(len(h & actual.open_hours.get(day, set())) for day, h in theory_hours.items())
        extra = sum(len(h - theory_hours.get(day, set())) for day, h in actual.open_hours.items())
        pct = covered / wanted
        status = "ok" if pct >= OK_RATIO else "warn" if pct >= WARN_RATIO else "bad"
        note = f"{pct:.0%} of the model's demand hours covered"
        if extra:
            note += f" · {extra} h/week open outside them"
        actual_label = f"{len(actual.open_hours)} days · {sum(len(h) for h in actual.open_hours.values())} h/week"
    else:
        status, note, actual_label = "bad", "no opening hours set", "closed"
    rows.append(FitRow("Opening hours", theory_label, actual_label, status, note))

    # 4. Personale.
    # Con lo staffing ora per ora (staffing_fit): una riga per ruolo, teorico
    # calcolato sui clienti reali. Senza: il vecchio numero di compute_bep,
    # che conta solo le workstation → solo informativo.
    if staffing is not None and staffing.roles:
        for r in staffing.roles:
            if r.kind == "sales":
                note = f"+{r.over_hours} h extra (~{_money(r.wasted_per_week)}/week) · {r.under_hours} h missing"
            elif r.kind == "appointment":
                note = (f"+{r.over_hours} h / -{r.under_hours} h · indicative: "
                        "reports count arrivals, not time spent with each client")
            else:
                note = "presence role: model assumes 1 person every open hour"
            rows.append(FitRow(
                f"Staff · {r.role}",
                f"{r.hours_needed} h/wk · {r.headcount_needed} ppl",
                f"{r.hours_staffed} h/wk · {r.headcount_actual} ppl",
                r.status, note,
            ))
    else:
        rows.append(FitRow(
            "Staff on shift (peak)", str(bep.employees), str(actual.peak_staff),
            "bad" if actual.peak_staff == 0 else "info",
            f"{actual.staff_assigned} employees assigned · model counts workstations only",
        ))

    # 5. Salari in % del ricavo (soglie assolute, vedi WAGE_SHARE_*): vedi wage_shares.
    theo_share, share = wage_shares(bep, actual, staffing)
    if share is not None:
        share_label = f"{share:.0%}"
        share_status = "ok" if share <= WAGE_SHARE_OK else "warn" if share <= WAGE_SHARE_WARN else "bad"
    else:
        share_label = "no revenue"
        share_status = "bad" if actual.wages_per_open_day > 0 else "info"
    rows.append(FitRow(
        "Wages / revenue", "n/a" if theo_share is None else f"{theo_share:.0%}", share_label,
        share_status,
        f"{_money(actual.wages_per_open_day)} per open day · avg ${actual.avg_hourly_wage:,.2f}/h",
    ))

    # 6. Arredi: una riga per pezzo teorico. Gli "obbligatori" del modello
    # (MANDATORY_FURNITURE) non valgono per ogni tipo (un ufficio non ha la
    # cassa): se mancano è solo un'informazione, non un errore.
    # Le POSTAZIONI si contano per ruolo, non per oggetto esatto: il modello sceglie
    # "Computer" (il più economico), ma 49 Desktop Computer + 1 Laptop sono comunque
    # 50 postazioni da avvocato. Gli altri arredi restano per nome.
    role_of = _station_role_lookup(profile.biz_name) if name_to_key else (lambda key: None)
    for f in bep.furniture:
        key = (name_to_key or {}).get(f.name)
        role = role_of(key) if key else None
        if role:
            have = sum(int(n) for k, n in actual.furniture.items() if role_of(k) == role)
        else:
            have = count_matching(actual.furniture, f.name, name_to_key)
        if have >= f.quantity:
            status = "ok"
        elif f.name in mandatory:
            status = "info"
        else:
            status = "bad" if have == 0 else "warn"
        if f.name in mandatory:
            note = "model default" + ("" if have else " · may not apply to this type")
        elif role:
            note = f"any {role} workstation counts · {f.capacity}/h each"
        else:
            note = f"{f.capacity}/h each"
        rows.append(FitRow(f"Furniture · {f.name}", str(f.quantity), str(have), status, note))

    # 7. Prodotti chiave venduti
    if core_products:
        missing = [label for key, label in core_products if key not in actual.items_sold]
        sold = len(core_products) - len(missing)
        rows.append(FitRow(
            "Core products sold", str(len(core_products)), str(sold),
            ratio_status(sold, len(core_products)),
            ("missing: " + ", ".join(missing)) if missing else "all sold",
        ))

    return rows


def wage_shares(bep, actual: ActualMetrics, staffing=None) -> tuple[Optional[float], Optional[float]]:
    """(teorica, tua) quota dei salari sul ricavo, tutto per giorno di CALENDARIO:
    revenue_per_day conta anche i giorni chiusi, quindi i salari della settimana / 7.
    Teorica con lo staffing = salari delle ore NECESSARIE sul TUO ricavo (quanto
    peserebbero con l'organico giusto); senza = dipendenti del modello × ore del modello.
    None dove manca il ricavo."""
    open_days = len(actual.open_hours) or 1
    wages_per_day = actual.wages_per_open_day * open_days / 7
    if staffing is not None and staffing.roles and actual.revenue_per_day:
        needed_hours = sum(r.hours_needed for r in staffing.roles)
        theo = needed_hours * actual.avg_hourly_wage / 7 / actual.revenue_per_day
    elif bep is not None and bep.revenue > 0:
        staff_hours = getattr(bep, "staff_hours", 0) or bep.employees * bep.weekly_hours
        theo = staff_hours * actual.avg_hourly_wage / 7 / bep.revenue
    else:
        theo = None
    mine = wages_per_day / actual.revenue_per_day if actual.revenue_per_day else None
    return theo, mine


def _station_role_lookup(biz_name: str):
    """item_key → ruolo della postazione (es. "Lawyer") o None se non è una postazione."""
    from analysis.staffing_fit import business_skills, station_for
    skills = business_skills(biz_name)
    cache: dict[str, Optional[str]] = {}

    def role_of(key: str) -> Optional[str]:
        if key not in cache:
            st_ = station_for(key, skills)
            cache[key] = st_.role if st_ else None
        return cache[key]
    return role_of


@dataclass
class MenuAction:
    """Un prodotto chiave (o più) da aggiungere al menu, con l'arredo che serve."""
    products: list            # prodotti chiave mancanti
    furniture: Optional[str]  # arredo da comprare; None = niente da comprare
    buy: int = 0              # quanti pezzi mancano
    capacity: float = 0       # clienti/ora per pezzo
    equipment: Optional[str] = None   # arredo del modello che hai già (solo da rifornire)


def menu_actions(bep, rows: list[FitRow], core_products: list, items_sold) -> list[MenuAction]:
    """Prodotti chiave non venduti → una azione per arredo, invece di righe separate.

    Il modello sceglie un arredo PER un prodotto (Pizza → Pizza Oven): se il prodotto
    manca, comprare l'arredo e metterlo in vendita sono la stessa decisione.
    """
    missing = [label for key, label in core_products if key not in items_sold]
    if not missing or bep is None:
        return []
    have_need = {}                                    # nome arredo → (theory, actual) dalla tabella
    for r in rows:
        if r.metric.startswith("Furniture · "):
            try:
                have_need[r.metric.split(" · ", 1)[1]] = (int(r.theory), int(r.actual))
            except ValueError:
                pass
    actions, linked = [], set()
    for f in bep.furniture:
        prods = [p for p in getattr(f, "products", []) if p in missing]
        if not prods:
            continue
        linked.update(prods)
        need, have = have_need.get(f.name, (f.quantity, 0))
        buy = max(need - have, 0)
        if buy:
            actions.append(MenuAction(prods, f.name, buy, f.capacity))
        else:
            actions.append(MenuAction(prods, None, equipment=f.name))
    rest = [p for p in missing if p not in linked]    # nessun arredo dedicato nel modello
    if rest:
        actions.append(MenuAction(rest, None))
    return actions


def fit_to_df(rows: list[FitRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"": STATUS_ICON[r.status], "Metric": r.metric, "Theory": r.theory,
          "Actual": r.actual, "Note": r.note} for r in rows],
        columns=["", "Metric", "Theory", "Actual", "Note"],
    )


# ============================================================================
# ENTRY POINT per la UI
# ============================================================================

def core_products_for(biz_name: str) -> list[tuple[str, str]]:
    """Prodotti con impact ≥ 0.9 (gli stessi che compute_bep usa per il teorico)."""
    from analysis.health_check import rank_products
    from core.game_data import get_item_by_name

    ranked = rank_products(biz_name)
    core = [p for p in ranked if p.impact >= 0.90] or ranked[:3]
    result = []
    for p in core:
        item = get_item_by_name(p.internal_name)
        if item:
            result.append((item["itemName"], p.name))
    return result


def evaluate_business(bundle: DataBundle, address: str, window_days: int = WINDOW_DAYS,
                      staffing=None):
    """profile, bep, actual, rows — tutto quello che serve alla pagina.
    `staffing` si può passare già calcolato (la pagina lo mostra anche a parte)."""
    from analysis.staffing_fit import evaluate_staffing
    from analysis.health_check import (
        MANDATORY_FURNITURE, compute_bep,
    )

    profile = resolve_business_profile(bundle.snapshot, address)
    if profile is None:
        return None, None, None, []
    actual = actual_metrics(bundle, address, window_days)
    bep = compute_bep(profile.biz_name, profile.capacity, profile.traffic,
                      profile.rent, round(actual.avg_hourly_wage, 2))
    if staffing is None:
        staffing = evaluate_staffing(bundle, address, window_days)
    rows = compare_to_theory(
        profile, bep, actual,
        staffing=staffing,
        core_products=core_products_for(profile.biz_name),
        name_to_key=furniture_name_index(),
        mandatory=frozenset(mf["name"] for mf in MANDATORY_FURNITURE),
    )
    return profile, bep, actual, rows
