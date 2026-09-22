"""
hsg_data_map.py — Diagnostica una tantum della struttura del save .hsg.

Scrive in hsg_data_map.txt la forma dei campi che servono per:
  - alert engine   → BuildingRegistration dei business del player
  - employees      → EmployeeInstances
  - arredi/stock   → itemInstances
  - import/logistica → importPartnerships, logisticsManagerPlans, ...

Uso (dalla root del repo):
    python hsg_data_map.py "C:\\...\\Recover Midnight.hsg"
oppure con SAMPLE_HSG_PATH settata:
    python hsg_data_map.py
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

from core.hsg_reader import load_save

MAX_DEPTH = 4     # quanti livelli di annidamento mostrare
MAX_ITEMS = 3     # quanti elementi mostrare per ogni lista
MAX_STR = 120     # tronca stringhe lunghe

# Campi "piatti" del business: una riga per business, per vedere tipi e range
BUSINESS_SCALARS = [
    "BusinessName", "businessTypeName", "RentedByPlayer", "AvailableForRent",
    "RentPerDay", "temporarilyClosed", "satisfaction", "customerCapacity",
    "radioStation", "radioVolume", "warnedLastHourAboutNoEmployee",
    "securityLevelPercentage", "creationDay", "takenOver",
]

# Campi annidati del business: dettaglio solo sul primo, per capirne la forma
BUSINESS_NESTED = [
    "scheduleDays", "promotion", "uniformsBySkill", "interiorDesigns",
    "marketingCampaigns", "dailyIncomes", "aiEmployees",
    "cachedFulfilledCustomerDemands", "retailPrices",
]

# Sezioni top-level del save per import e logistica
ROOT_SECTIONS = [
    "realEstate", "importPartnerships", "itemsOrderedThisWeekByImporter",
    "logisticsManagerPlans", "hrManagerPlans", "pricingManagerPlans",
]


def short_type(t):
    """'Entities.OrderHistoryEntry+HourReport, BigAmbitions' -> 'OrderHistoryEntry+HourReport'"""
    if not t:
        return None
    return t.split(",")[0].split(".")[-1]


def prune(value, save, depth=0, max_depth=MAX_DEPTH, max_items=MAX_ITEMS):
    """
    Converte un nodo del save in una struttura stampabile come JSON:
    segue i $ref, toglie $id, accorcia $type, tronca liste e profondità.
    """
    value = save.deref(value)

    if isinstance(value, dict):
        t = short_type(value.get("$type"))
        if depth >= max_depth:
            return f"<{t or 'dict'}: {len(value)} keys>"
        out = {}
        if t:
            out["$type"] = t
        for k, v in value.items():
            if k in ("$type", "$id"):
                continue
            if k == "$items" and isinstance(v, list):
                out["$items_count"] = len(v)
                out["$items"] = [
                    prune(x, save, depth + 1, max_depth, max_items)
                    for x in v[:max_items]
                ]
                continue
            out[k] = prune(v, save, depth + 1, max_depth, max_items)
        return out

    if isinstance(value, list):
        head = [prune(x, save, depth + 1, max_depth, max_items) for x in value[:max_items]]
        if len(value) > max_items:
            head.append(f"... (+{len(value) - max_items} more)")
        return head

    if isinstance(value, (bytes, bytearray)):
        return f"<bytes len={len(value)}>"

    if isinstance(value, str) and len(value) > MAX_STR:
        return value[:MAX_STR] + "..."

    return value


class Report:
    """Accumula le righe del report, poi le scrive su file in un colpo."""

    def __init__(self):
        self.lines = []

    def header(self, title):
        self.lines += ["", "=" * 78, title, "=" * 78]

    def line(self, *parts):
        self.lines.append(" ".join(str(p) for p in parts))

    def block(self, obj):
        self.lines.append(json.dumps(obj, indent=2, ensure_ascii=False, default=str))

    def row(self, obj):
        self.lines.append(json.dumps(obj, ensure_ascii=False, default=str))


def describe(value, save):
    """Descrizione di una riga: tipo + dimensione o valore."""
    v = save.deref(value)
    if isinstance(v, dict):
        size = len(v["$items"]) if "$items" in v else len(v)
        return f"dict ({short_type(v.get('$type')) or '-'}, {size} items/keys)"
    if isinstance(v, list):
        return f"list len={len(v)}"
    return f"{type(v).__name__} = {repr(v)[:60]}"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SAMPLE_HSG_PATH")
    if not path:
        sys.exit("Passa il path del .hsg come argomento o setta SAMPLE_HSG_PATH")

    save = load_save(path)
    root = save.root
    rep = Report()

    # 0. Meta
    rep.header("0. META")
    rep.block({k: root.get(k) for k in (
        "SaveGameName", "Day", "Hour", "Money", "NetWorth", "buildNumberAtLastSave"
    )})

    # 1. Business del player: campi piatti, una riga ciascuno
    buildings = [b for b in save.items(root.get("BuildingRegistrations")) if b]
    mine = [b for b in buildings if b.get("RentedByPlayer")]
    rep.header(f"1. PLAYER BUSINESSES — {len(mine)} su {len(buildings)} building")
    for b in mine:
        rep.row({k: prune(b.get(k), save, max_depth=2) for k in BUSINESS_SCALARS})

    if not mine:
        rep.line("Nessun business del player trovato.")
    else:
        first = mine[0]

        # 2. Tutte le chiavi del BuildingRegistration, per non perdere campi
        rep.header(f"2. TUTTE LE CHIAVI di BuildingRegistration — {first.get('BusinessName')}")
        for k, v in first.items():
            rep.line(f"  {k}: {describe(v, save)}")

        # 2b. Campi annidati in dettaglio
        rep.header("2b. CAMPI ANNIDATI (primo business)")
        for k in BUSINESS_NESTED:
            rep.line(f"\n--- {k} ---")
            rep.block(prune(first.get(k), save))

        # 3. itemInstances = arredi + stock
        rep.header("3. itemInstances — conteggio per business")
        for b in mine:
            n = len(save.items(b.get("itemInstances")))
            rep.line(f"  {b.get('BusinessName')} ({b.get('businessTypeName')}): {n} itemInstances")

        first_items = [x for x in save.items(first.get("itemInstances")) if x]
        rep.line(f"\nPrimi item di {first.get('BusinessName')} (dettaglio):")
        for it in first_items[:3]:
            rep.block(prune(it, save))

        # Conteggio per nome, se troviamo una chiave che identifica l'item
        name_key = next(
            (k for k in ("itemName", "ItemName", "itemId", "name")
             if first_items and k in first_items[0]),
            None,
        )
        if name_key:
            counts = Counter(str(save.deref(it.get(name_key))) for it in first_items)
            rep.line(f"\nConteggio per '{name_key}' in {first.get('BusinessName')}:")
            for name, cnt in counts.most_common(40):
                rep.line(f"  {cnt:4d}  {name}")

    # 4. Dipendenti
    emps = [e for e in save.items(root.get("EmployeeInstances")) if e]
    rep.header(f"4. EmployeeInstances — {len(emps)} totali")
    if emps:
        rep.line("Chiavi:", list(emps[0].keys()))
        for e in emps[:2]:
            rep.block(prune(e, save, max_depth=5))

    # 5+. Sezioni top-level per import / logistica / manager
    for i, key in enumerate(ROOT_SECTIONS, start=5):
        rep.header(f"{i}. {key}")
        rep.block(prune(root.get(key), save))

    dest = Path(__file__).parent / "hsg_data_map.txt"
    dest.write_text("\n".join(rep.lines), encoding="utf-8")
    print(f"Scritto {dest} ({len(rep.lines)} righe)")


if __name__ == "__main__":
    main()