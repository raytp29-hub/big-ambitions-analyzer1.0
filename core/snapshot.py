"""
core/snapshot.py
Lo "stato attuale" dei business del player, estratto dal save .hsg.

DataBundle contiene la STORIA (transactions, item_sales, hour_reports):
cosa è successo giorno per giorno. Snapshot contiene lo STATO: com'è fatto
ogni business adesso (orari, turni, dipendenti, import, domande clienti).

Modello relazionale (schema a stella):
    businesses          → tabella dimensione, chiave primaria `address`
    opening_hours       ┐
    shifts              │ tabelle dei fatti, collegate a businesses
    employees           │ tramite la colonna `address`
    fulfilled_demands   ┘
    imports             → collegata ai magazzini tramite `warehouse_address`

La chiave è l'indirizzo, non il nome: un building affittato ma vuoto non ha
nome, e il giocatore può dare lo stesso nome a due negozi. Formato della
chiave: "ba:street_fifthavenue|38". Vedi claude/hsg-data-map.md.
"""

from dataclasses import dataclass

import pandas as pd

from core.hsg_reader import Save
from core.schema_utils import validate_df


# ============================================================================
# SCHEMI
# ============================================================================

BUSINESSES_SCHEMA: dict[str, str] = {
    "address":              "string",   # PK
    "business_name":        "string",   # "" per building vuoto
    "business_type":        "string",   # ba:businesstype_*
    "rent_per_day":         "float64",
    "temporarily_closed":   "bool",
    "customer_capacity":    "int32",
    "sat_overall":          "float64",  # 0-100 (50 fisso = default, business senza clienti)
    "sat_customer_service": "float64",
    "sat_pricing":          "float64",
    "sat_cleanliness":      "float64",
    "sat_facility":         "float64",
    "promotion_total":      "float64",  # 100 = cap raggiunto
    "promotion_marketing":  "float64",
    "radio_station":        "int32",
    "warned_no_employee":   "bool",
}

OPENING_HOURS_SCHEMA: dict[str, str] = {   # una riga per fascia oraria
    "address":    "string",
    "day":        "int32",    # 1-7
    "is_open":    "bool",
    "start_hour": "int32",
    "end_hour":   "int32",
}

SHIFTS_SCHEMA: dict[str, str] = {          # una riga per turno
    "address":         "string",
    "day":             "int32",
    "employee_id":     "string",
    "start_hour":      "int32",
    "end_hour":        "int32",
    "station_item_id": "string",
    "shift_type":      "int32",    # 0/1 — significato da confermare
}

EMPLOYEES_SCHEMA: dict[str, str] = {
    "employee_id":          "string",   # PK
    "name":                 "string",
    "address":              "string",   # "" se non assegnato
    "hourly_wage":          "float64",
    "satisfaction":         "float64",
    "weekly_hours":         "int32",
    "is_absent":            "bool",
    "is_complaining":       "bool",
    "complaint_demand":     "string",   # "" se nessuna
    "quit_warning":         "bool",
    "hr_plan_id":           "string",
    "has_health_insurance": "bool",     # unico campo derivato (join con hrManagerPlans)
}

IMPORTS_SCHEMA: dict[str, str] = {         # una riga per partnership × prodotto
    "partnership_id":    "string",
    "import_address":    "string",   # il pier
    "is_active":         "bool",
    "is_repeating":      "bool",
    "next_delivery_day": "int32",
    "item_key":          "string",
    "amount":            "int32",
    "ordered_last_week": "int32",
    "warehouse_address": "string",   # "" se nessuno
}

FULFILLED_DEMANDS_SCHEMA: dict[str, str] = {   # una riga per business × domanda soddisfatta
    "address":    "string",
    "demand_key": "string",    # ba:customerdemand_*
}

# Nome del campo nella dataclass → schema. Usato dal __post_init__ per
# validare tutte le tabelle con un solo loop.
SNAPSHOT_SCHEMAS: dict[str, dict[str, str]] = {
    "businesses":        BUSINESSES_SCHEMA,
    "opening_hours":     OPENING_HOURS_SCHEMA,
    "shifts":            SHIFTS_SCHEMA,
    "employees":         EMPLOYEES_SCHEMA,
    "imports":           IMPORTS_SCHEMA,
    "fulfilled_demands": FULFILLED_DEMANDS_SCHEMA,
}


# ============================================================================
# DATACLASS
# ============================================================================

@dataclass(frozen=True)
class Snapshot:
    businesses: pd.DataFrame
    opening_hours: pd.DataFrame
    shifts: pd.DataFrame
    employees: pd.DataFrame
    imports: pd.DataFrame
    fulfilled_demands: pd.DataFrame

    def __post_init__(self) -> None:
        # getattr(self, "businesses") == self.businesses: così un solo loop
        # valida tutte e sei le tabelle, e aggiungerne una settima significa
        # aggiungere una riga a SNAPSHOT_SCHEMAS, non un altro blocco if.
        for field_name, schema in SNAPSHOT_SCHEMAS.items():
            validate_df(getattr(self, field_name), field_name, schema)


# ============================================================================
# HELPER
# ============================================================================

def _key(street, number) -> str:
    """Chiave indirizzo: 'ba:street_fifthavenue|38'. Stringa vuota se manca la via."""
    if not street:
        return ""
    return f"{street}|{int(number or 0)}"


def _address_key(save: Save, value) -> str:
    """Chiave da un oggetto Address {streetName, streetNumber} del save."""
    addr = save.address(value)   # helper di Peter → (street, number) o None
    return _key(*addr) if addr else ""


def _num(value, default=0):
    """None → default. Il save a volte ha la chiave presente con valore null."""
    return default if value is None else value


def _to_df(rows: list[dict], schema: dict[str, str]) -> pd.DataFrame:
    """Stesso pattern di data_loader: funziona anche con rows=[] (df vuoto ma tipato)."""
    return pd.DataFrame(rows, columns=list(schema)).astype(schema)


def _player_buildings(save: Save) -> list[dict]:
    return [
        b for b in save.items(save.root.get("BuildingRegistrations"))
        if b and b.get("RentedByPlayer")
    ]


# ============================================================================
# ESTRAZIONI — una funzione per tabella
# ============================================================================

def _extract_businesses(buildings: list[dict], save: Save) -> pd.DataFrame:
    rows = []
    for b in buildings:
        sat = save.deref(b.get("satisfaction")) or {}
        promo = save.deref(b.get("promotion")) or {}
        rows.append({
            "address":              _key(b.get("StreetName"), b.get("StreetNumber")),
            "business_name":        b.get("BusinessName") or "",
            "business_type":        b.get("businessTypeName") or "",
            "rent_per_day":         _num(b.get("RentPerDay"), 0.0),
            "temporarily_closed":   bool(b.get("temporarilyClosed")),
            "customer_capacity":    _num(b.get("customerCapacity")),
            "sat_overall":          _num(sat.get("overall"), 0.0),
            "sat_customer_service": _num(sat.get("customerService"), 0.0),
            "sat_pricing":          _num(sat.get("pricing"), 0.0),
            "sat_cleanliness":      _num(sat.get("cleanliness"), 0.0),
            "sat_facility":         _num(sat.get("facility"), 0.0),
            "promotion_total":      _num(promo.get("total"), 0.0),
            "promotion_marketing":  _num(promo.get("marketing"), 0.0),
            "radio_station":        _num(b.get("radioStation")),
            "warned_no_employee":   bool(b.get("warnedLastHourAboutNoEmployee")),
        })
    return _to_df(rows, BUSINESSES_SCHEMA)


def _extract_schedule(buildings: list[dict], save: Save) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Un solo passaggio su scheduleDays produce due tabelle:
    le fasce di apertura e i turni. Stessa sorgente, due granularità diverse.
    """
    hour_rows, shift_rows = [], []
    for b in buildings:
        address = _key(b.get("StreetName"), b.get("StreetNumber"))
        for sd in save.items(b.get("scheduleDays")):
            if not sd:
                continue
            day = _num(sd.get("day"))
            is_open = bool(sd.get("isOpen"))

            for slot in save.items(sd.get("openingHourSlots")):
                if not slot:
                    continue
                hour_rows.append({
                    "address":    address,
                    "day":        day,
                    "is_open":    is_open,
                    "start_hour": _num(slot.get("startingHour")),
                    "end_hour":   _num(slot.get("endingHour")),
                })

            for sh in save.items(sd.get("workShifts")):
                if not sh:
                    continue
                shift_rows.append({
                    "address":         address,
                    "day":             day,
                    "employee_id":     sh.get("employeeId") or "",
                    "start_hour":      _num(sh.get("startingHour")),
                    "end_hour":        _num(sh.get("endingHour")),
                    "station_item_id": sh.get("itemInstanceId") or "",
                    "shift_type":      _num(sh.get("type")),
                })

    return _to_df(hour_rows, OPENING_HOURS_SCHEMA), _to_df(shift_rows, SHIFTS_SCHEMA)


def _extract_employees(save: Save) -> pd.DataFrame:
    # Mappa piano HR → ha assicurazione sanitaria? Serve per il join qui sotto.
    plan_insured = {
        p.get("id"): p.get("healthInsurancePlan") is not None
        for p in save.items(save.root.get("hrManagerPlans"))
        if p
    }

    rows = []
    for e in save.items(save.root.get("EmployeeInstances")):
        if not e:
            continue
        character = save.deref(e.get("characterData")) or {}
        complaint = save.deref(e.get("complaintData")) or {}
        current = save.deref(complaint.get("currentComplaint")) or {}
        plan_id = e.get("assignedHrManagerPlanId") or ""

        rows.append({
            "employee_id":          e.get("id") or "",
            "name":                 character.get("name") or "",
            "address":              _address_key(save, e.get("assignedAddress")),
            "hourly_wage":          _num(e.get("hourlyWage"), 0.0),
            "satisfaction":         _num(e.get("satisfaction"), 0.0),
            "weekly_hours":         _num(e.get("assignedWeeklyHours")),
            "is_absent":            bool(e.get("isAbsent")),
            "is_complaining":       bool(complaint.get("isComplaining")),
            "complaint_demand":     current.get("demandName") or "",
            "quit_warning":         bool(e.get("hasSendQuitWarning")),
            "hr_plan_id":           plan_id,
            "has_health_insurance": plan_insured.get(plan_id, False),
        })
    return _to_df(rows, EMPLOYEES_SCHEMA)


def _extract_imports(save: Save) -> pd.DataFrame:
    rows = []
    for p in save.items(save.root.get("importPartnerships")):
        if not p:
            continue
        common = {
            "partnership_id":    p.get("id") or "",
            "import_address":    _address_key(save, p.get("importAddress")),
            "is_active":         bool(p.get("isActive")),
            "is_repeating":      bool(p.get("isRepeatingOrder")),
            "next_delivery_day": _num(p.get("nextDeliveryDay")),
        }
        for prod in save.items(p.get("products")):
            if not prod:
                continue
            rows.append({
                **common,   # i campi della partnership, ripetuti su ogni prodotto
                "item_key":          prod.get("itemName") or "",
                "amount":            _num(prod.get("amount")),
                "ordered_last_week": _num(prod.get("amountOrderedLastWeek")),
                "warehouse_address": _address_key(save, prod.get("assignedWarehouse")),
            })
    return _to_df(rows, IMPORTS_SCHEMA)


def _extract_fulfilled_demands(buildings: list[dict], save: Save) -> pd.DataFrame:
    rows = []
    for b in buildings:
        address = _key(b.get("StreetName"), b.get("StreetNumber"))
        for demand in save.items(b.get("cachedFulfilledCustomerDemands")):
            if demand:
                rows.append({"address": address, "demand_key": demand})
    return _to_df(rows, FULFILLED_DEMANDS_SCHEMA)


# ============================================================================
# ENTRY POINT
# ============================================================================

def build_snapshot(save: Save) -> Snapshot:
    """Costruisce lo Snapshot completo. Il __post_init__ valida tutte le tabelle."""
    buildings = _player_buildings(save)
    opening_hours, shifts = _extract_schedule(buildings, save)
    return Snapshot(
        businesses=_extract_businesses(buildings, save),
        opening_hours=opening_hours,
        shifts=shifts,
        employees=_extract_employees(save),
        imports=_extract_imports(save),
        fulfilled_demands=_extract_fulfilled_demands(buildings, save),
    )
