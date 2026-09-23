"""
visualization/ui_components.py
Componenti grafici condivisi (card, tabella "aperta", badge, icone delle
customer demands, card Theory vs Actual) per Home e Health Check.

Ogni componente ha due livelli:
    *_html(...)   → funzione pura che restituisce una stringa HTML (testabile
                     senza Streamlit)
    render_*(...) → la mostra nella pagina con st.html

Lo stile sta tutto in inject_css(): va chiamata una volta per pagina, prima
dei componenti. I colori sono variabili CSS (--ba-*) con una versione per il
tema chiaro e una per lo scuro; il tema si legge da st.context.theme.

Regole di leggibilità (skill dataviz):
- lo stato (critical / warning / info / ok) non è mai affidato al solo colore:
  i badge hanno sempre un'etichetta, le card un titolo;
- il testo usa l'inchiostro del tema, il colore di stato va su pallini, bordi,
  barre e sfondi tenui.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Callable, Optional

import streamlit as st

# ============================================================================
# TEMA
# ============================================================================

# Stato: good / warning / critical dalla palette di stato della skill dataviz;
# info = il blu "over" della staffing heatmap, così le pagine parlano la stessa lingua.
THEMES = {
    "dark": {
        "ink": "#f2f1ed", "muted": "#a3a29d", "line": "rgba(250,250,250,0.12)",
        "card": "rgba(255,255,255,0.03)", "hover": "rgba(255,255,255,0.05)",
        "track": "rgba(250,250,250,0.10)",
        "critical": "#e66767", "warning": "#fab219", "info": "#3987e5",
        "ok": "#0ca30c", "neutral": "#a3a29d",
    },
    "light": {
        "ink": "#1f1f1e", "muted": "#6b6a66", "line": "rgba(49,51,63,0.15)",
        "card": "#ffffff", "hover": "rgba(49,51,63,0.04)",
        "track": "rgba(49,51,63,0.10)",
        "critical": "#d03b3b", "warning": "#fab219", "info": "#2a78d6",
        "ok": "#0ca30c", "neutral": "#8a8985",
    },
}
TONES = ("critical", "warning", "info", "ok", "neutral")


def ui_theme() -> str:
    """'dark' o 'light': il tema attivo di Streamlit (st.context.theme dalla 1.46)."""
    try:
        kind = st.context.theme.type
        if kind in THEMES:
            return kind
    except Exception:
        pass
    try:
        return "dark" if st.get_option("theme.base") == "dark" else "light"
    except Exception:
        return "light"


def css(theme: str = "dark") -> str:
    t = THEMES[theme]
    tokens = "\n".join(f"  --ba-{k}: {v};" for k, v in t.items())
    return f"""
:root {{
{tokens}
  --ba-mono: "Source Code Pro", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
.ba-card {{ background: var(--ba-card); border: 1px solid var(--ba-line); border-radius: 10px;
  padding: 14px 16px; color: var(--ba-ink); height: 100%; box-sizing: border-box; }}
.ba-card.ba-accent {{ border-top: 3px solid var(--ba-tone); }}
.ba-card h4 {{ margin: 0; padding: 0; font-size: 1rem; font-weight: 600; color: var(--ba-ink); }}
.ba-muted {{ color: var(--ba-muted); }}
.ba-small {{ font-size: 0.8rem; }}
.ba-mono {{ font-family: var(--ba-mono); }}
.ba-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--ba-tone); margin-right: 6px; vertical-align: middle; }}
.ba-list {{ list-style: none; margin: 10px 0 0; padding: 0; }}
.ba-list li {{ display: flex; justify-content: space-between; gap: 8px; padding: 6px 0;
  border-top: 1px solid var(--ba-line); margin: 0; font-size: 0.9rem; }}
.ba-list li span:last-child {{ color: var(--ba-muted); font-size: 0.8rem; text-align: right; }}
.ba-badge {{ display: inline-flex; align-items: center; gap: 5px; font: 0.75rem var(--ba-mono);
  padding: 2px 8px; border-radius: 4px; color: var(--ba-ink); white-space: nowrap;
  background: color-mix(in srgb, var(--ba-tone) 16%, transparent); }}
.ba-badge::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--ba-tone); }}
.ba-bar {{ height: 6px; background: var(--ba-track); border-radius: 3px; overflow: hidden; }}
.ba-bar > i {{ display: block; height: 100%; background: var(--ba-tone, var(--ba-ok)); border-radius: 3px; }}
.ba-table-wrap {{ overflow-x: auto; }}
table.ba-table {{ width: 100%; border-collapse: collapse; border: none; color: var(--ba-ink); }}
table.ba-table th {{ font: 0.7rem var(--ba-mono); letter-spacing: .09em; text-transform: uppercase;
  color: var(--ba-muted); font-weight: 400; padding: 10px 12px; border: none;
  border-bottom: 1px solid var(--ba-line); white-space: nowrap; background: transparent; }}
table.ba-table td {{ padding: 10px 12px; border: none; border-bottom: 1px solid var(--ba-line);
  white-space: nowrap; font-family: var(--ba-mono); font-size: 0.85rem; }}
table.ba-table td.ba-text {{ font-family: inherit; font-size: 0.9rem; white-space: normal; }}
table.ba-table td small {{ display: block; color: var(--ba-muted); font-family: sans-serif; font-size: 0.75rem; }}
table.ba-table tr:hover td {{ background: var(--ba-hover); }}
table.ba-table .ba-left {{ text-align: left; }}
table.ba-table .ba-right {{ text-align: right; }}
.ba-help {{ border-bottom: 1px dotted var(--ba-muted); cursor: help; }}
.ba-inline {{ display: inline-flex; align-items: center; gap: 10px; }}
.ba-inline .ba-bar {{ width: 70px; }}
.ba-icons {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }}
.ba-icon {{ width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
  position: relative; color: var(--ba-tone);
  background: color-mix(in srgb, var(--ba-tone) 14%, transparent); }}
.ba-icon.ba-miss {{ box-shadow: inset 0 0 0 1.5px var(--ba-tone); }}
.ba-icon.ba-miss::after {{ content: ""; position: absolute; width: 24px; height: 1.5px;
  background: var(--ba-tone); transform: rotate(-45deg); }}
.ba-icon svg {{ width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.8;
  stroke-linecap: round; stroke-linejoin: round; }}
.ba-tip {{ position: absolute; bottom: 42px; left: 50%; transform: translateX(-50%);
  background: #111; color: #fff; font-size: 0.75rem; padding: 4px 8px; border-radius: 5px;
  white-space: nowrap; opacity: 0; pointer-events: none; transition: opacity .12s; z-index: 10; }}
.ba-icon:hover .ba-tip {{ opacity: 1; }}
.ba-big {{ font: 600 1.5rem var(--ba-mono); margin: 4px 0 2px; }}
.ba-row {{ display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }}
.ba-gauge {{ position: relative; height: 8px; background: var(--ba-track); border-radius: 4px; margin: 12px 0 6px; }}
.ba-gauge > i {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 4px; background: var(--ba-tone); }}
.ba-gauge > b {{ position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--ba-ink); }}
"""


def inject_css() -> None:
    """Da chiamare una volta per pagina, prima dei componenti."""
    st.html(f"<style>{css(ui_theme())}</style>")


def _tone(tone: str) -> str:
    """Attributo style che imposta il colore di stato per un elemento e i suoi figli."""
    if tone not in TONES:
        raise ValueError(f"tone must be one of {TONES}, got {tone!r}")
    return f'style="--ba-tone: var(--ba-{tone})"'


# ============================================================================
# BADGE
# ============================================================================

def badge_html(text: str, tone: str = "neutral") -> str:
    return f'<span class="ba-badge" {_tone(tone)}>{escape(str(text))}</span>'


# ============================================================================
# CARD DEGLI ALERT (Home)
# ============================================================================

SEVERITY_TITLE = {"critical": "Critical", "warning": "Warning", "info": "Info"}


def severity_card_html(severity: str, total: int, items: list[tuple[str, str]]) -> str:
    """Card con titolo = gravità e le prime voci (etichetta breve, business).
    `total` è il numero complessivo: se le voci mostrate sono meno, compare '+N more'."""
    rows = "".join(
        f"<li><span>{escape(label)}</span><span>{escape(business)}</span></li>"
        for label, business in items
    )
    if not items:
        rows = '<li><span class="ba-muted">Nothing here</span><span></span></li>'
    more = total - len(items)
    more_html = f'<div class="ba-muted ba-small" style="margin-top:8px">+{more} more</div>' if more > 0 else ""
    return (
        f'<div class="ba-card ba-accent" {_tone(severity)}>'
        f'<h4><span class="ba-dot"></span>{SEVERITY_TITLE.get(severity, severity.title())}'
        f' <span class="ba-muted ba-mono">· {total}</span></h4>'
        f'<ul class="ba-list">{rows}</ul>{more_html}</div>'
    )


def render_severity_card(severity: str, total: int, items: list[tuple[str, str]]) -> None:
    st.html(severity_card_html(severity, total, items))


# ============================================================================
# TABELLA "APERTA" (stile Peter: niente griglia, header mono, barre inline)
# ============================================================================

@dataclass(frozen=True)
class Column:
    key: str                                            # colonna del dict/riga
    label: str                                          # intestazione
    fmt: Callable[[Any], str] = str                     # valore → testo
    align: str = "right"                                # "left" | "right"
    help: Optional[str] = None                          # tooltip sull'intestazione
    sub: Optional[str] = None                           # chiave del sottotitolo grigio
    bar: bool = False                                   # barra inline ∝ valore / massimo
    tone: Optional[Callable[[Any], Optional[str]]] = None   # valore → tono → badge


def _cell(col: Column, row: dict, max_value: float) -> str:
    value = row.get(col.key)
    text = escape(col.fmt(value)) if value is not None else "—"
    if col.tone is not None and value is not None:
        tone = col.tone(value)
        if tone:
            text = badge_html(col.fmt(value), tone)
    if col.bar and value is not None and max_value > 0:
        pct = max(0.0, min(1.0, float(value) / max_value)) * 100
        text = f'<span class="ba-inline"><span class="ba-bar"><i style="width:{pct:.1f}%"></i></span>{text}</span>'
    if col.sub and row.get(col.sub):
        text += f"<small>{escape(str(row[col.sub]))}</small>"
    classes = f"ba-{col.align}" + (" ba-text" if col.align == "left" else "")
    return f'<td class="{classes}">{text}</td>'


def open_table_html(columns: list[Column], rows: list[dict]) -> str:
    head = ""
    for c in columns:
        label = escape(c.label)
        if c.help:
            label = f'<span class="ba-help" title="{escape(c.help)}">{label}</span>'
        head += f'<th class="ba-{c.align}">{label}</th>'
    max_values = {
        c.key: max((float(r[c.key]) for r in rows if r.get(c.key) is not None), default=0.0)
        for c in columns if c.bar
    }
    body = "".join(
        "<tr>" + "".join(_cell(c, r, max_values.get(c.key, 0.0)) for c in columns) + "</tr>"
        for r in rows
    )
    return (f'<div class="ba-table-wrap"><table class="ba-table"><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def render_open_table(columns: list[Column], rows: list[dict]) -> None:
    st.html(open_table_html(columns, rows))


# ============================================================================
# ICONE DELLE CUSTOMER DEMANDS
# ============================================================================

# Icone a linea disegnate per questo progetto (viewBox 24×24, solo stroke).
_ICON_PATHS = {
    "ba:customerdemand_music":
        "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    "ba:customerdemand_employeeuniforms":
        "M8 3 4 6l2 4 2-1v12h8V9l2 1 2-4-4-3a4 4 0 0 1-8 0z",
    "ba:customerdemand_interiordesign":
        "M3 21h18M5 21V10l7-6 7 6v11M9 21v-6h6v6",
    "ba:customerdemand_seating":
        "M5 11V8a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v3M3 13a2 2 0 0 1 4 0v2h10v-2a2 2 0 0 1 4 0v5H3zM5 18v2M19 18v2",
    "ba:customerdemand_toilet":
        "M7 4h4v7H7zM5 11h14a6 6 0 0 1-6 6h-2a6 6 0 0 1-6-6zM9 17l-1 4h8l-1-4",
    "ba:customerdemand_toiletprivacy":
        "M6 21V3h12v18M3 21h18M14 12h.01",
    "ba:customerdemand_sink":
        "M4 12h16a6 6 0 0 1-6 6h-4a6 6 0 0 1-6-6zM12 12V6a2 2 0 0 1 4 0M10 18v3h4v-3",
}
_FALLBACK_ICON = "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8v4M12 16h.01"


def demand_icons_html(items: list[tuple[str, str, bool]]) -> str:
    """items = [(demand_key, etichetta, soddisfatta)]. Verde = ok, rossa barrata = manca.
    Hover = etichetta + stato (lo stato non è affidato al solo colore)."""
    icons = []
    for key, label, met in items:
        path = _ICON_PATHS.get(key, _FALLBACK_ICON)
        tone = "ok" if met else "critical"
        state = "met" if met else "missing"
        miss = "" if met else " ba-miss"
        icons.append(
            f'<span class="ba-icon{miss}" {_tone(tone)} aria-label="{escape(label)}: {state}">'
            f'<svg viewBox="0 0 24 24"><path d="{path}"/></svg>'
            f'<span class="ba-tip">{escape(label)} · {state}</span></span>'
        )
    return f'<div class="ba-icons">{"".join(icons)}</div>'


def render_demand_icons(items: list[tuple[str, str, bool]]) -> None:
    st.html(demand_icons_html(items))


# ============================================================================
# CARD THEORY VS ACTUAL
# ============================================================================

GAUGE_MAX = 1.2   # scala "più alto è meglio": la barra arriva al 120% della teoria


def ratio_gauge(ratio: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """Per le metriche dove più alto è meglio (revenue, clienti): ratio = actual / theory.
    Restituisce (riempimento, tacca) in 0-1: la tacca è la teoria (100% → 1/1.2)."""
    if ratio is None:
        return None, None
    return min(max(ratio, 0.0) / GAUGE_MAX, 1.0), 1 / GAUGE_MAX


def share_gauge(share: Optional[float], theory_share: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """Per le quote dove più basso è meglio (salari / ricavo): scala assoluta 0-100%,
    la barra è la tua quota, la tacca quella teorica."""
    if share is None:
        return None, None
    mark = None if theory_share is None else min(max(theory_share, 0.0), 1.0)
    return min(max(share, 0.0), 1.0), mark


def theory_card_html(label: str, actual: str, theory: str, status: str, note: str = "",
                     fill: Optional[float] = None, mark: Optional[float] = None,
                     hint: str = "") -> str:
    """Card Theory vs Actual: valore reale grande, teorico piccolo, barra con tacca.
    status = esito già deciso dall'analisi (FitRow.status: ok / warn / bad / info).
    fill / mark in 0-1, da ratio_gauge o share_gauge."""
    tone = {"bad": "critical", "warn": "warning"}.get(status, status)
    gauge = ""
    if fill is not None:
        mark_html = f'<b style="left:{mark * 100:.1f}%"></b>' if mark is not None else ""
        gauge = f'<div class="ba-gauge"><i style="width:{fill * 100:.1f}%"></i>{mark_html}</div>'
    hint_html = f' <span class="ba-small">({escape(hint)})</span>' if hint else ""
    return (
        f'<div class="ba-card" {_tone(tone)}>'
        f'<div class="ba-muted">{escape(label)}{hint_html}</div>'
        f'<div class="ba-row"><span class="ba-big">{escape(actual)}</span>'
        f'<span class="ba-mono ba-muted">Theory {escape(theory)}</span></div>'
        f'{gauge}<div class="ba-muted ba-small">{escape(note)}</div></div>'
    )


def render_theory_card(*args, **kwargs) -> None:
    st.html(theory_card_html(*args, **kwargs))
