"""
visualization/alerts_view.py
UI degli alert: riepilogo compatto per il Dashboard e sezione completa
per la pagina Business Health Check. La logica sta in analysis/business_alerts.py:
qui c'è solo la presentazione.
"""

from typing import Callable, Optional

import pandas as pd
import streamlit as st

from analysis.business_alerts import (
    SEVERITY_ORDER, build_context, demand_status, run_all_checks, summarize,
)

from core.localization import display_name
from analysis.business_alerts import NON_CUSTOMER_TYPES, _street_label
from visualization.ui_components import (
    business_card_html, business_grid_html, demand_icons_html, render_severity_card,
)

SEVERITY_ICON = {"critical": "🔴", "warning": "🟠", "info": "🔵"}

# Etichette brevi per le card della Home (il messaggio lungo resta nel dettaglio).
# Chiave = Alert.code, stabile; un codice nuovo senza etichetta usa il messaggio.
ALERT_LABEL = {
    "RENT_ON_EMPTY":       "Empty building",
    "RENT_WHILE_CLOSED":   "Closed, still paying rent",
    "NO_EMPLOYEE_NOW":     "Nobody working now",
    "UNCOVERED_HOURS":     "Hours without staff",
    "LOSING_MONEY":        "Losing money",
    "REVENUE_DOWN":        "Revenue down",
    "REVENUE_UP":          "Revenue up",
    "LOW_SATISFACTION":    "Low satisfaction",
    "MISSING_DEMANDS":     "Missing customer demands",
    "PROMOTION_BELOW_CAP": "Promotion below cap",
    "AT_CAPACITY":         "At customer capacity",
    "IMPORT_PAUSED":       "Import paused",
    "QUIT_WARNING":        "Employee about to quit",
    "EMPLOYEE_COMPLAINT":  "Employee complaining",
    "NO_HEALTH_INSURANCE": "No health insurance",
    "OVERSTAFFED_HOURS":   "Overstaffed hours",
}
CARD_ITEMS = 3   # voci mostrate per card; le altre finiscono in "+N more"


def short_label(alert) -> str:
    return ALERT_LABEL.get(alert.code, alert.message)


def _get_alerts(bundle):
    """Una sola esecuzione dei check per rerun, condivisa fra le sezioni della pagina."""
    return run_all_checks(bundle)


def render_alert_summary(bundle, on_open: Optional[Callable[[], None]] = None) -> None:
    """Home: una card per gravità (Critical / Warning / Info) con le prime voci.
    `on_open` = callback del bottone che porta alla Health Check (la navigazione
    sta in app.py: qui non serve sapere come è fatta)."""
    if bundle is None or bundle.snapshot is None:
        return

    alerts = _get_alerts(bundle)
    counts = summarize(alerts)

    st.subheader("Business Alerts")
    columns = st.columns(len(SEVERITY_ORDER))
    for col, severity in zip(columns, SEVERITY_ORDER):
        items = [(short_label(a), a.business) for a in alerts if a.severity == severity]
        with col:
            render_severity_card(severity, counts[severity], items[:CARD_ITEMS])

    if on_open is not None:
        st.button("Open Business Health Check →", on_click=on_open, key="home_open_health")


# Alert della supply chain: non stanno nella griglia dei business
# (avranno una pagina dedicata alla supply chain).
SUPPLY_CODES = frozenset({"IMPORT_PAUSED"})
STATUS_LABEL = {"critical": "critical", "warning": "warning", "info": "info", "ok": "healthy"}


def business_groups(bundle, alerts) -> list[dict]:
    """Un gruppo per business del save (anche quelli senza problemi) + i gruppi di alert
    non legati a un business del save (es. import). Ordine: gravità peggiore, poi numero
    di problemi, poi nome."""
    snap = bundle.snapshot
    ctx = build_context(snap)
    status = demand_status(snap, ctx)
    groups: dict[str, dict] = {}
    for b in snap.businesses.itertuples():
        kind = display_name(b.business_type) if b.business_type else ""
        if b.business_type == "ba:businesstype_empty":
            kind = "Empty building"
        demands = status[status["address"] == b.address]
        name = ctx.names.get(b.address) or b.business_name or _street_label(b.address)
        street = _street_label(b.address)
        groups[b.address] = {
            "key": b.address,
            "name": name,
            "subtitle": " · ".join(x for x in (kind, street if street != name else "") if x),
            "alerts": [],
            "demands": [(r.demand_key, r.demand, bool(r.fulfilled)) for r in demands.itertuples()],
            "customer": b.business_type not in NON_CUSTOMER_TYPES,
        }
    for al in alerts:
        if al.code in SUPPLY_CODES:
            continue
        key = al.address if al.address in groups else f"name:{al.business}"
        if key not in groups:
            groups[key] = {"key": key, "name": al.business, "subtitle": "", "alerts": [],
                           "demands": [], "customer": False}
        groups[key]["alerts"].append(al)

    def worst(g):
        return min((SEVERITY_ORDER[x.severity] for x in g["alerts"]), default=len(SEVERITY_ORDER))

    return sorted(groups.values(), key=lambda g: (worst(g), -len(g["alerts"]), g["name"].lower()))


def _tone_of(group) -> str:
    if not group["alerts"]:
        return "ok"
    return min(group["alerts"], key=lambda x: SEVERITY_ORDER[x.severity]).severity


def business_card(group) -> str:
    tone = _tone_of(group)
    counts = summarize(group["alerts"])
    badges = [(f"{n} {sev}", sev) for sev, n in counts.items() if n]
    issues = [(x.severity, short_label(x), x.evidence)
              for x in sorted(group["alerts"], key=lambda x: SEVERITY_ORDER[x.severity])]
    icons = demand_icons_html(group["demands"]) if group["demands"] else ""
    return business_card_html(group["name"], group["subtitle"], tone, STATUS_LABEL[tone],
                              badges, issues, icons)


def has_urgent(group) -> bool:
    """Per il filtro: solo critical e warning contano come 'problema'."""
    return any(x.severity in ("critical", "warning") for x in group["alerts"])


def render_alerts_section(bundle) -> None:
    """Your Businesses: una card per business in griglia; 'Details' apre il dettaglio."""
    st.header("Your Businesses")

    if bundle is None or bundle.snapshot is None:
        st.info(
            "Load an HSG save file from the sidebar to see live alerts for your businesses "
            "(staffing, rent, customer demands, imports, employees)."
        )
        return

    alerts = [x for x in _get_alerts(bundle) if x.code not in SUPPLY_CODES]
    counts = summarize(alerts)
    st.caption(
        f"{counts['critical']} critical · {counts['warning']} warning · {counts['info']} info. "
        "The coloured edge shows each business's most urgent problem. Icons = customer demands "
        "(green met, red crossed missing): hover an icon for its name. "
        "Click \"+N more\" inside a card to see the rest of its issues."
    )
    only_issues = st.toggle("Only critical and warning", key="hc_only_issues",
                            help="Hide businesses that only have info notes or no issues.")

    groups = business_groups(bundle, alerts)
    if only_issues:
        groups = [g for g in groups if has_urgent(g)]
    if not groups:
        st.success("No critical or warning issues. Everything looks healthy.")
        return
    st.html(business_grid_html([business_card(g) for g in groups]))
