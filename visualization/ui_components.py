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

# Il tema (chiaro/scuro) NON si legge da Python per il CSS: st.context.theme può
# essere vecchio di un rerun (cambi tema dal menu → nessun rerun) e il CSS resterebbe
# quello sbagliato. Quindi:
# - i neutri (testo, bordi, sfondi) derivano dal colore del testo della pagina
#   (currentColor), che Streamlit imposta già giusto per il tema attivo;
# - i colori di stato sono la palette di stato della skill dataviz, pensata per
#   funzionare uguale su sfondo chiaro e scuro (e sempre con un'etichetta).
TOKENS = {
    "ink":      "currentColor",
    "muted":    "color-mix(in srgb, currentColor 62%, transparent)",
    "line":     "color-mix(in srgb, currentColor 20%, transparent)",
    "card":     "color-mix(in srgb, currentColor 6%, transparent)",
    "hover":    "color-mix(in srgb, currentColor 9%, transparent)",
    "track":    "color-mix(in srgb, currentColor 15%, transparent)",
    "critical": "#d03b3b",
    "warning":  "#fab219",
    "info":     "#2a78d6",
    "ok":       "#0ca30c",
    "neutral":  "color-mix(in srgb, currentColor 55%, transparent)",
}
TONES = ("critical", "warning", "info", "ok", "neutral")

# Palette categoriale per le serie (una linea per business): 8 tinte in ordine
# fisso, validate per daltonismo nella skill dataviz. Mai ciclare: dalla 9a serie
# in poi si raggruppa in "Other" (colore OTHER_COLOR).
CATEGORICAL = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    "dark":  ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
}
OTHER_COLOR = {"light": "#8a8985", "dark": "#a3a29d"}


def ui_theme() -> str:
    """'dark' o 'light': il tema attivo di Streamlit (st.context.theme dalla 1.46)."""
    try:
        kind = st.context.theme.type
        if kind in ("dark", "light"):
            return kind
    except Exception:
        pass
    try:
        return "dark" if st.get_option("theme.base") == "dark" else "light"
    except Exception:
        return "light"


def css(theme: str | None = None) -> str:
    """CSS dei componenti. `theme` non serve più (vedi TOKENS): resta per compatibilità."""
    tokens = "\n".join(f"  --ba-{k}: {v};" for k, v in TOKENS.items())
    # barre di composizione: primi slot della palette categoriale (versione chiara:
    # blu/arancio/acqua/giallo si leggono anche su fondo scuro)
    tokens += "\n" + "\n".join(f"  --ba-c{i + 1}: {c};" for i, c in enumerate(CATEGORICAL["light"]))
    tokens += "\n  --ba-other: color-mix(in srgb, currentColor 45%, transparent);"
    return f"""
:root {{
{tokens}
  --ba-mono: "Source Code Pro", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
.ba-card {{ background: var(--ba-card); border: 1px solid var(--ba-line); border-radius: 10px;
  padding: 14px 16px; color: var(--ba-ink); height: 100%; box-sizing: border-box;
  box-shadow: 0 1px 3px color-mix(in srgb, currentColor 10%, transparent); }}
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
table.ba-table td small {{ display: block; color: var(--ba-muted); font-family: sans-serif; font-size: 0.75rem; margin-top: 2px; }}
table.ba-table tr:hover td {{ background: var(--ba-hover); }}
table.ba-table .ba-left {{ text-align: left; }}
table.ba-table .ba-right {{ text-align: right; }}
.ba-help {{ border-bottom: 1px dotted var(--ba-muted); cursor: help; }}
.ba-inline {{ display: inline-flex; align-items: center; gap: 10px; }}
.ba-inline .ba-bar {{ width: 70px; }}
.ba-chips {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }}
.ba-chip {{ display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px 3px 7px;
  border-radius: 6px; font-size: 0.8rem; line-height: 1.3; color: var(--ba-ink);
  border: 1px solid var(--ba-line); background: var(--ba-card); }}
.ba-chip img {{ width: 15px; height: 15px; display: block; }}
.ba-chip b {{ color: var(--ba-tone); font-size: 0.72rem; }}
.ba-chip.ba-miss {{ border-color: color-mix(in srgb, var(--ba-critical) 55%, transparent);
  background: color-mix(in srgb, var(--ba-critical) 10%, transparent); }}
.ba-icons {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }}
.ba-icon {{ width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
  position: relative; color: var(--ba-tone);
  background: color-mix(in srgb, var(--ba-tone) 14%, transparent); }}
.ba-icon.ba-miss {{ box-shadow: inset 0 0 0 1.5px var(--ba-tone); }}
.ba-icon.ba-miss::after {{ content: ""; position: absolute; width: 24px; height: 1.5px;
  background: var(--ba-tone); transform: rotate(-45deg); }}
.ba-icon img {{ width: 18px; height: 18px; display: block; }}
.ba-tip {{ position: absolute; bottom: 42px; left: 50%; transform: translateX(-50%);
  background: #111; color: #fff; font-size: 0.75rem; padding: 4px 8px; border-radius: 5px;
  white-space: nowrap; opacity: 0; pointer-events: none; transition: opacity .12s; z-index: 10; }}
.ba-icon:hover .ba-tip {{ opacity: 1; }}
.ba-big {{ font: 600 1.5rem var(--ba-mono); margin: 4px 0 2px; }}
.ba-row {{ display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }}
.ba-gauge {{ position: relative; height: 8px; background: var(--ba-track); border-radius: 4px; margin: 12px 0 6px; }}
.ba-gauge > i {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 4px; background: var(--ba-tone); }}
.ba-kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }}
@media (max-width: 900px) {{ .ba-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.ba-kpi {{ display: flex; flex-direction: column; min-height: 178px; }}
.ba-kpi .ba-label {{ color: var(--ba-muted); font-size: 0.85rem; display: flex; justify-content: space-between; }}
.ba-kpi .ba-q {{ cursor: help; color: var(--ba-muted); display: inline-flex; align-items: center; }}
.ba-i {{ display: inline-grid; place-items: center; width: 14px; height: 14px; border-radius: 50%;
  border: 1.4px solid currentColor; font: 700 9.5px/1 Georgia, serif; box-sizing: border-box; }}
.ba-kpi .ba-q:hover {{ color: var(--ba-ink); }}
.ba-kpi .ba-graphic {{ margin-top: auto; padding-top: 10px; overflow: hidden; }}
.ba-cols {{ display: flex; align-items: flex-end; gap: 3px; height: 44px; }}
.ba-cols > i {{ flex: 1; background: var(--ba-c1); border-radius: 3px 3px 0 0; min-height: 2px; opacity: .85; }}
.ba-cols > i:hover {{ opacity: 1; }}
.ba-cols.ba-dense {{ gap: 1px; }}
.ba-wklabels {{ display: flex; gap: 3px; margin-top: 4px; }}
.ba-wklabels > span {{ flex: 1; text-align: center; font: 0.65rem var(--ba-mono); color: var(--ba-muted); }}
.ba-days {{ display: flex; gap: 3px; }}
.ba-days > span {{ flex: 1; text-align: center; font: 0.65rem var(--ba-mono); color: var(--ba-muted); }}
.ba-days > span > i {{ display: block; height: 22px; border-radius: 4px; margin-bottom: 4px;
  background: color-mix(in srgb, var(--ba-c1) 70%, transparent); }}
.ba-days > span.ba-weekend > i {{ background: color-mix(in srgb, var(--ba-c1) 40%, transparent); }}
.ba-stack {{ display: flex; height: 12px; border-radius: 4px; overflow: hidden; gap: 2px; }}
.ba-stack > i {{ display: block; height: 100%; }}
.ba-legend {{ display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 8px; font-size: 0.72rem; color: var(--ba-muted); }}
.ba-legend > span::before {{ content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 2px;
  margin-right: 4px; background: var(--ba-sw); vertical-align: -1px; }}
.ba-area {{ display: block; width: 100%; height: 44px; }}
.ba-kpis.ba-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.ba-kpis.ba-5 {{ grid-template-columns: repeat(5, minmax(0, 1fr)); }}
@media (max-width: 900px) {{ .ba-kpis.ba-3, .ba-kpis.ba-5 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.ba-kpi.ba-compact {{ min-height: 0; }}
.ba-kpi.ba-compact .ba-big {{ font-family: inherit; font-size: 1.15rem; font-weight: 600; line-height: 1.3; }}
.ba-section {{ font-weight: 600; margin: 14px 0 4px; }}
.ba-grid-title {{ font-size: 1.05rem; font-weight: 700; margin: 14px 0 2px; }}
.ba-grid-desc {{ font-size: 0.82rem; color: var(--ba-muted); margin-bottom: 6px; }}
.ba-cols > i.ba-hl {{ background: var(--ba-warning); opacity: 1; }}
.ba-note {{ border-left: 3px solid var(--ba-info); background: color-mix(in srgb, var(--ba-info) 10%, transparent);
  padding: 10px 14px; border-radius: 4px; font-size: 0.88rem; line-height: 1.45; margin: 12px 0; }}
.ba-biz {{ border-left: 3px solid var(--ba-tone); min-height: 150px; }}
.ba-biz .ba-hd {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }}
.ba-biz .ba-badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
.ba-biz .ba-none {{ font-size: 0.8rem; color: var(--ba-muted); margin-top: 10px; }}
.ba-bizgrid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: start; }}
@media (max-width: 900px) {{ .ba-bizgrid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
@media (max-width: 600px) {{ .ba-bizgrid {{ grid-template-columns: 1fr; }} }}
.ba-issues {{ list-style: none; margin: 10px 0 0; padding: 0; }}
.ba-issues li {{ font-size: 0.82rem; line-height: 1.35; padding: 5px 0; margin: 0;
  border-top: 1px solid var(--ba-line); }}
.ba-issues li b {{ font-weight: 600; }}
.ba-more summary {{ cursor: pointer; font-size: 0.8rem; color: var(--ba-muted); padding: 6px 0 0;
  list-style: none; }}
.ba-more summary::-webkit-details-marker {{ display: none; }}
.ba-more summary::after {{ content: " ▾"; }}
.ba-more[open] summary::after {{ content: " ▴"; }}
.ba-more summary:hover {{ color: var(--ba-ink); }}
.ba-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }}
.ba-delta {{ font: 0.8rem var(--ba-mono); color: var(--ba-muted); }}
.ba-delta b {{ color: var(--ba-tone); font-weight: 600; }}
.ba-spark {{ display: block; width: 100%; height: 38px; margin-top: 8px; }}
.ba-gauge > b {{ position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--ba-ink); }}
"""


def inject_css() -> None:
    """Da chiamare una volta per pagina, prima dei componenti."""
    st.html(f"<style>{css()}</style>")


# st.html passa l'HTML da DOMPurify con il profilo "html": gli <svg> inline vengono
# tolti (niente icone, niente sparkline). Un <img src="data:image/svg+xml;base64,...">
# invece passa. Dentro un'immagine però le variabili CSS non esistono: i colori
# vanno scritti nell'SVG (TONE_HEX, stessi valori di TOKENS).
TONE_HEX = {"critical": "#d03b3b", "warning": "#fab219", "info": "#2a78d6",
            "ok": "#0ca30c", "neutral": "#8a8985"}


def svg_img(svg: str, cls: str = "", alt: str = "") -> str:
    import base64
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img class="{cls}" alt="{escape(alt)}" src="data:image/svg+xml;base64,{data}">'


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

class Raw(str):
    """HTML già pronto da mettere in una cella (es. un badge): non viene escapato.
    Usarlo solo con HTML costruito da queste funzioni, mai con testo del save."""


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
    if isinstance(value, Raw):
        text = str(value)
    else:
        text = escape(col.fmt(value)) if value is not None else "—"
    if col.tone is not None and value is not None:
        tone = col.tone(value)
        if tone:
            text = badge_html(col.fmt(value), tone)
    if col.bar and isinstance(value, (int, float)) and max_value > 0:
        pct = max(0.0, min(1.0, float(value) / max_value)) * 100
        text = f'<span class="ba-inline"><span class="ba-bar"><i style="width:{pct:.1f}%"></i></span>{text}</span>'
    if col.sub and row.get(col.sub):
        sub = row[col.sub]
        text += f"<small>{sub if isinstance(sub, Raw) else escape(str(sub))}</small>"
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
    """items = [(demand_key, etichetta, soddisfatta)] → "chip" con icona, NOME sempre visibile
    e ✓ / ✕. Le demand mancanti hanno bordo e sfondo rossi. Stato mai affidato al solo colore:
    c'è il segno e la parola nel tooltip."""
    chips = []
    for key, label, met in items:
        path = _ICON_PATHS.get(key, _FALLBACK_ICON)
        tone = "ok" if met else "critical"
        state = "met" if met else "missing"
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
               f'stroke="{TONE_HEX[tone]}" stroke-width="1.9" stroke-linecap="round" '
               f'stroke-linejoin="round"><path d="{path}"/></svg>')
        chips.append(
            f'<span class="ba-chip{"" if met else " ba-miss"}" {_tone(tone)} title="{escape(label)}: {state}">'
            f'{svg_img(svg, alt="")}<span>{escape(label)}</span>'
            f'<b>{"✓" if met else "✕"}</b></span>'
        )
    return f'<div class="ba-chips">{"".join(chips)}</div>'


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


# ============================================================================
# CARD REVENUE PER BUSINESS (Home)
# ============================================================================

DELTA_FLAT = 0.02   # entro ±2% la variazione conta come "stabile"


def delta_tone(delta: Optional[float]) -> str:
    if delta is None or abs(delta) < DELTA_FLAT:
        return "neutral"
    return "ok" if delta > 0 else "critical"


def sparkline_svg(values: list, tone: str = "neutral", width: int = 100, height: int = 30) -> str:
    """Linea (viewBox 100×30, stirata sulla larghezza della card), come immagine SVG."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pad = 2
    points = " ".join(
        f"{i * width / (len(values) - 1):.1f},{height - pad - (v - lo) / span * (height - 2 * pad):.1f}"
        for i, v in enumerate(values)
    )
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
           f'<polyline points="{points}" fill="none" stroke="{TONE_HEX[tone]}" stroke-width="1.6" '
           f'vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>')
    return svg_img(svg, "ba-spark")


def revenue_card_html(business: str, total: float, share: float,
                      delta: Optional[float], daily: list, window: int = 7) -> str:
    tone = delta_tone(delta)
    if delta is None:
        delta_html = f'<div class="ba-delta">not enough days for a {window}-day comparison</div>'
    else:
        arrow = "▲" if tone == "ok" else "▼" if tone == "critical" else "＝"
        delta_html = (f'<div class="ba-delta"><b>{arrow} {abs(delta):.0%}</b> '
                      f'vs previous {window} days</div>')
    return (
        f'<div class="ba-card" {_tone(tone)}>'
        f'<div class="ba-muted">{escape(business)}</div>'
        f'<div class="ba-big">${total:,.0f}</div>{delta_html}'
        f'<div class="ba-bar" style="margin-top:10px;--ba-tone:var(--ba-ok)">'
        f'<i style="width:{max(share, 0.0) * 100:.1f}%"></i></div>'
        f'<div class="ba-muted ba-small" style="margin-top:4px">{share:.0%} of total revenue</div>'
        f'{sparkline_svg(daily, tone)}</div>'
    )


def revenue_cards_html(rows: list, window: int = 7) -> str:
    """rows = lista di analysis.revenue_analyzer.BusinessRevenue."""
    cards = "".join(
        revenue_card_html(r.business, r.total, r.share, r.delta_pct, r.daily, window) for r in rows
    )
    return f'<div class="ba-grid">{cards}</div>'


def render_revenue_cards(rows: list, window: int = 7) -> None:
    st.html(revenue_cards_html(rows, window))


# ============================================================================
# CARD KPI (Overview della Home) — stessa altezza, grafico in basso
# ============================================================================

_WEEKDAY = "MTWTFSS"   # giorno di gioco → (day - 1) % 7, 0 = lunedì (vedi staffing_fit)


# Icona "info": cerchio + "i" disegnati in CSS (il carattere ⓘ usciva sgranato,
# e gli <svg> inline vengono tolti da st.html).
_INFO_ICON = '<span class="ba-i">i</span>'


def kpi_card_html(label: str, value: str, graphic: str = "", sub: str = "",
                  help: str = "", tone: str = "neutral", compact: bool = False) -> str:
    """Card KPI: etichetta (+ ⓘ con spiegazione al passaggio del mouse), valore,
    riga opzionale sotto (`sub`, HTML già pronto), grafico ancorato in basso."""
    q = f'<span class="ba-q" title="{escape(help)}">{_INFO_ICON}</span>' if help else ""
    return (
        f'<div class="ba-card ba-kpi{" ba-compact" if compact else ""}" {_tone(tone)}>'
        f'<div class="ba-label"><span>{escape(label)}</span>{q}</div>'
        f'<div class="ba-big">{escape(value)}</div>{sub}'
        f'<div class="ba-graphic">{graphic}</div></div>'
    )


def kpi_row_html(cards: list[str]) -> str:
    """Riga di card della stessa altezza, una colonna per card (max 5)."""
    extra = {3: " ba-3", 5: " ba-5"}.get(len(cards), "")
    return f'<div class="ba-kpis{extra}">{"".join(cards)}</div>'


def columns_html(values: list, labels: list) -> str:
    """Colonne verticali (una per giorno), altezza ∝ valore; hover = etichetta.
    Oltre 30 colonne lo spazio fra le barre si riduce (sennò non ci stanno)."""
    top = max(values, default=0) or 1
    bars = "".join(
        f'<i style="height:{max(v / top, 0) * 100:.0f}%" title="{escape(str(lab))}: {v:,}"></i>'
        for v, lab in zip(values, labels)
    )
    dense = " ba-dense" if len(values) > 30 else ""
    return f'<div class="ba-cols{dense}">{bars}</div>'


WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def weekday_columns_html(avg_by_weekday: list, days_by_weekday: list, unit: str = "transactions") -> str:
    """Grafico statico a 7 colonne (lunedì → domenica): media per giorno della settimana.
    Stessa dimensione con 10 o 200 giorni di dati; hover = giorno, quanti giorni, media."""
    top = max(avg_by_weekday, default=0) or 1
    bars, labels = [], []
    for i, (avg, n) in enumerate(zip(avg_by_weekday, days_by_weekday)):
        tip = f"{WEEKDAY_NAMES[i]} · {n} day{'s' if n != 1 else ''} · avg {avg:,.0f} {unit}/day"
        bars.append(f'<i style="height:{max(avg / top, 0) * 100:.0f}%" title="{escape(tip)}"></i>')
        labels.append(f"<span>{_WEEKDAY[i]}</span>")
    return (f'<div class="ba-cols">{"".join(bars)}</div>'
            f'<div class="ba-wklabels">{"".join(labels)}</div>')


def day_strip_html(days: list[int]) -> str:
    """Un blocco per giorno di gioco, con l'iniziale del giorno della settimana
    (sabato e domenica più tenui): si vede subito quali giorni copre il file."""
    cells = []
    for d in days:
        wd = (int(d) - 1) % 7
        cls = ' class="ba-weekend"' if wd >= 5 else ""
        cells.append(f'<span{cls} title="Day {d}"><i></i>{_WEEKDAY[wd]}</span>')
    return f'<div class="ba-days">{"".join(cells)}</div>'


def composition_html(parts: list[tuple[str, float]], top: int = 4,
                     colors: Optional[dict] = None) -> str:
    """Barra 100% impilata: le prime `top` voci con i colori categoriali, il resto 'Other'.
    `colors` (nome → colore) per usare lo stesso colore dell'entità negli altri grafici.
    Legenda sempre presente (l'identità non è affidata al solo colore)."""
    total = sum(v for _, v in parts) or 1
    shown = parts[:top]
    rest = sum(v for _, v in parts[top:])
    if rest > 0:
        shown = shown + [("Other", rest)]
    segs, legend = [], []
    for i, (name, v) in enumerate(shown):
        if name == "Other":
            color = "var(--ba-other)"
        elif colors and name in colors:
            color = colors[name]
        else:
            color = f"var(--ba-c{i + 1})"
        pct = v / total
        segs.append(f'<i style="width:{pct * 100:.1f}%;background:{color}" title="{escape(name)}: {pct:.0%}"></i>')
        legend.append(f'<span style="--ba-sw:{color}">{escape(name)} {pct:.0%}</span>')
    return f'<div class="ba-stack">{"".join(segs)}</div><div class="ba-legend">{"".join(legend)}</div>'


def area_svg(values: list, tone: str = "info", width: int = 100, height: int = 40) -> str:
    """Area + linea (saldo, clienti per giorno), come immagine SVG."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = [(i * width / (len(values) - 1), height - 3 - (v - lo) / span * (height - 6))
           for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{height} {line} {width},{height}"
    color = TONE_HEX[tone]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
           f'<polygon points="{area}" fill="{color}" fill-opacity="0.18"/>'
           f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.6" '
           f'vector-effect="non-scaling-stroke"/></svg>')
    return svg_img(svg, "ba-area")


def hour_columns_html(values: list, highlight: Optional[int] = None) -> str:
    """24 colonne (una per ora), l'ora `highlight` in evidenza; hover = ora + valore."""
    top = max(values, default=0) or 1
    hl = ' class="ba-hl"'
    bars = "".join(
        f'<i{hl if h == highlight else ""} '
        f'style="height:{max(v / top, 0) * 100:.0f}%" title="{h:02d}:00 · {v:,.1f}"></i>'
        for h, v in enumerate(values)
    )
    return f'<div class="ba-cols">{bars}</div>'


def note_html(html_text: str) -> str:
    """Riquadro informativo (bordo blu a sinistra). `html_text` è HTML scritto nel codice,
    non testo del save: non viene escapato (così può avere <b>)."""
    return f'<div class="ba-note">{html_text}</div>'


def render_note(html_text: str) -> None:
    st.html(note_html(html_text))


# ============================================================================
# CARD BUSINESS (Health Check → Your Businesses)
# ============================================================================

CARD_ISSUES = 3   # problemi visibili nella card; gli altri dentro "+N more" (espandibile)


def _issue_line(severity: str, label: str, evidence: str) -> str:
    ev = f' <span class="ba-muted">— {escape(evidence)}</span>' if evidence else ""
    return f'<li {_tone(severity)}><span class="ba-dot"></span><b>{escape(label)}</b>{ev}</li>'


def business_card_html(name: str, subtitle: str, tone: str, status: str,
                       badges: list[tuple[str, str]], issues: list[tuple[str, str, str]],
                       icons: str = "") -> str:
    """Card di un business: bordo sinistro = gravità peggiore, badge di stato, conteggi,
    i problemi (gravità, etichetta, dato) — i primi CARD_ISSUES in vista, gli altri in un
    <details> dentro la card — e le icone delle customer demands."""
    badge_row = "".join(badge_html(text, t) for text, t in badges)
    first = "".join(_issue_line(*i) for i in issues[:CARD_ISSUES])
    rest = issues[CARD_ISSUES:]
    more = ""
    if rest:
        more = (f'<details class="ba-more"><summary>+{len(rest)} more</summary>'
                f'<ul class="ba-issues">{"".join(_issue_line(*i) for i in rest)}</ul></details>')
    body = (f'<ul class="ba-issues">{first}</ul>{more}' if issues
            else '<div class="ba-none">No issues found.</div>')
    return (
        f'<div class="ba-card ba-biz" {_tone(tone)}>'
        f'<div class="ba-hd"><h4>{escape(name)}</h4>{badge_html(status, tone)}</div>'
        f'<div class="ba-muted ba-small">{escape(subtitle)}</div>'
        f'<div class="ba-badges">{badge_row}</div>{body}{icons}</div>'
    )


def business_grid_html(cards: list[str]) -> str:
    return f'<div class="ba-bizgrid">{"".join(cards)}</div>'
