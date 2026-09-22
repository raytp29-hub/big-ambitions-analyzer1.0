"""
visualization/alerts_view.py
UI degli alert: riepilogo compatto per il Dashboard e sezione completa
per la pagina Business Health Check. La logica sta in analysis/business_alerts.py:
qui c'è solo la presentazione.
"""

import pandas as pd
import streamlit as st

from analysis.business_alerts import (
    SEVERITY_ORDER, build_context, demand_status, run_all_checks, summarize,
)

SEVERITY_ICON = {"critical": "🔴", "warning": "🟠", "info": "🔵"}


def _get_alerts(bundle):
    """Una sola esecuzione dei check per rerun, condivisa fra le sezioni della pagina."""
    return run_all_checks(bundle)


def render_alert_summary(bundle) -> None:
    """Riepilogo in cima al Dashboard: conteggi per gravità + i critici principali."""
    if bundle is None or bundle.snapshot is None:
        return

    alerts = _get_alerts(bundle)
    counts = summarize(alerts)

    st.subheader("Business Alerts")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{SEVERITY_ICON['critical']} Critical", counts["critical"])
    c2.metric(f"{SEVERITY_ICON['warning']} Warnings", counts["warning"])
    c3.metric(f"{SEVERITY_ICON['info']} Info", counts["info"])

    critical = [a for a in alerts if a.severity == "critical"]
    for a in critical[:3]:
        st.error(f"**{a.business}** — {a.message} ({a.evidence})")
    if len(critical) > 3:
        st.caption(f"+{len(critical) - 3} more critical issues.")
    st.caption("Full details in the 🏥 Business Health Check page.")


def render_alerts_section(bundle) -> None:
    """Sezione completa: alert raggruppati per business + griglia delle customer demands."""
    st.header("Your Businesses — Live Status")

    if bundle is None or bundle.snapshot is None:
        st.info(
            "Load an HSG save file from the sidebar to see live alerts for your businesses "
            "(staffing, rent, customer demands, imports, employees)."
        )
        return

    alerts = _get_alerts(bundle)
    if not alerts:
        st.success("No issues found. Everything looks healthy.")
    else:
        counts = summarize(alerts)
        c1, c2, c3 = st.columns(3)
        c1.metric(f"{SEVERITY_ICON['critical']} Critical", counts["critical"])
        c2.metric(f"{SEVERITY_ICON['warning']} Warnings", counts["warning"])
        c3.metric(f"{SEVERITY_ICON['info']} Info", counts["info"])

        shown = st.multiselect(
            "Show",
            options=list(SEVERITY_ORDER),
            default=list(SEVERITY_ORDER),
            format_func=lambda s: f"{SEVERITY_ICON[s]} {s.title()}",
            key="hc_alert_severity_filter",
        )
        visible = [a for a in alerts if a.severity in shown]

        # Raggruppa per business mantenendo l'ordine (i business col problema
        # più grave vengono prima, perché gli alert arrivano già ordinati).
        groups: dict[str, list] = {}
        for a in visible:
            groups.setdefault(a.business, []).append(a)

        for business, items in groups.items():
            worst = min(items, key=lambda a: SEVERITY_ORDER[a.severity]).severity
            label = f"{SEVERITY_ICON[worst]} {business} — {len(items)} issue{'s' if len(items) > 1 else ''}"
            with st.expander(label, expanded=(worst == "critical")):
                for a in items:
                    st.markdown(f"{SEVERITY_ICON[a.severity]} **{a.message}** — {a.evidence}")

    # Griglia customer demands: ✅ soddisfatta, ❌ mancante, vuoto = non richiesta
    status = demand_status(bundle.snapshot, build_context(bundle.snapshot))
    if not status.empty:
        st.subheader("Customer Demands")
        status = status.assign(mark=status["fulfilled"].map({True: "✅", False: "❌"}))
        grid = status.pivot_table(
            index="business", columns="demand", values="mark", aggfunc="first"
        ).fillna("")
        st.dataframe(grid, use_container_width=True)
        st.caption(
            "✅ met · ❌ missing · empty = not required for this business type. "
            "Requirements come from the game data; what's met comes from your save."
        )
