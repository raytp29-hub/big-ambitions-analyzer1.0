"""
analysis/hours_advice.py
Consigli scritti sugli orari (Health Check → "Demand vs your opening hours").

Confronta, giorno per giorno:
  - le ORE DEL MODELLO (health_check.model_open_hours: dove la domanda del gioco conta)
  - i TUOI orari (business_fit.open_hours_by_day)
e produce due tipi di consiglio:
  open_more  → ore del modello in cui sei chiuso: clienti persi (stima del modello)
  close      → ore in cui sei aperto fuori dal modello e arrivano pochi clienti veri
               (hour reports del save): paghi personale per quasi nessuno
I giorni con la stessa fascia vengono raggruppati ("Mon–Fri 05:00-11:00").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from analysis.business_alerts import DAY_NAMES, format_hour_ranges

LOW_CUSTOMERS = 3.0      # clienti/ora (reali) sotto cui un'ora aperta fuori modello "non rende"


@dataclass(frozen=True)
class HoursAdvice:
    kind: str                 # "open_more" | "close" | "closed_day"
    days: tuple               # giorni 1-7 con la stessa fascia
    hours: tuple              # ore della fascia
    customers_per_week: float # open_more: clienti stimati persi · close: clienti reali in quelle ore

    @property
    def days_label(self) -> str:
        return days_label(self.days)

    @property
    def hours_label(self) -> str:
        return format_hour_ranges(self.hours)


def days_label(days) -> str:
    """(1, 2, 3, 5) → 'Mon–Wed, Fri'"""
    days = sorted(days)
    parts, start, prev = [], days[0], days[0]
    for d in days[1:] + [None]:
        if d is not None and d == prev + 1:
            prev = d
            continue
        parts.append(DAY_NAMES[start] if start == prev else f"{DAY_NAMES[start]}–{DAY_NAMES[prev]}")
        if d is not None:
            start = prev = d
    return ", ".join(parts)


def _group(items: list[tuple[str, int, tuple, float]]) -> list[HoursAdvice]:
    """(kind, day, hours, customers) → raggruppa per (kind, hours)."""
    groups: dict[tuple, list] = {}
    for kind, day, hours, cust in items:
        groups.setdefault((kind, hours), []).append((day, cust))
    out = [HoursAdvice(kind, tuple(d for d, _ in v), hours, sum(c for _, c in v))
           for (kind, hours), v in groups.items()]
    return sorted(out, key=lambda a: -a.customers_per_week if a.kind != "close" else a.customers_per_week)


def hours_advice(matrix: np.ndarray, model_hours: dict, open_hours: dict, traffic: float,
                 capacity: float, observed: dict | None = None) -> list[HoursAdvice]:
    """
    matrix      domanda 7×24 (health_check.demand_matrix)
    model_hours {giorno: set(ore)} del modello
    open_hours  {giorno: set(ore)} tuoi
    observed    {(giorno, ora): clienti medi reali} (staffing_fit.observed_customers); None = niente consigli "close"
    """
    open_more, close = [], []
    for day in range(1, 8):
        theory = model_hours.get(day, set())
        mine = open_hours.get(day, set())
        missing = tuple(sorted(theory - mine))
        if missing:
            lost = sum(min(traffic * matrix[day - 1][h], capacity) for h in missing)
            kind = "closed_day" if not mine else "open_more"
            open_more.append((kind, day, missing, lost))
        if observed is not None:
            extra = tuple(sorted(h for h in mine - theory
                                 if observed.get((day, h), 0.0) < LOW_CUSTOMERS))
            if extra:
                close.append(("close", day, extra, sum(observed.get((day, h), 0.0) for h in extra)))
    return _group(open_more) + _group(close)
