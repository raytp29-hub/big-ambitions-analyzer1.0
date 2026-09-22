"""
visualization/staffing_heatmap.py
Heatmap "in turno − necessari" per un ruolo: giorni × ore.

    blu  = persone in più del necessario (costo inutile)
    rosso = persone in meno (clienti non serviti / postazione scoperta)
    grigio = in linea
    vuoto = negozio chiuso e nessuno in turno

Colori: coppia divergente blu↔rosso con punto medio grigio neutro, una
versione per tema chiaro e una per tema scuro (validate con lo script della
skill dataviz). Ogni cella non a zero porta anche il numero (+2 / −1), così
il segno non è affidato solo al colore.

La funzione restituisce un dict (data + layout) nel formato di Plotly: la
pagina lo passa a go.Figure, e lo stesso dict si può renderizzare anche con
plotly.js puro per le anteprime.
"""

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
INK_ON_LIGHT = "#1f1f1e"     # testo su celle chiare
INK_ON_DARK = "#ffffff"      # testo su celle scure (blu/rosso pieni)

THEMES = {
    "light": {"under": "#e34948", "over": "#2a78d6", "mid": "#f0efec",
              "ink": "#1f1f1e", "muted": "#6b6a66", "grid": "#e4e3df"},
    "dark":  {"under": "#e66767", "over": "#3987e5", "mid": "#383835",
              "ink": "#f2f1ed", "muted": "#a3a29d", "grid": "#2c2c2a"},
}


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def cell_color(value: float, peak: float, scale: dict) -> str:
    """Colore della cella: stessa interpolazione lineare della colorscale di Plotly."""
    t = max(-1.0, min(1.0, value / peak)) if peak else 0.0
    end = scale["over"] if t >= 0 else scale["under"]
    a, b = _rgb(scale["mid"]), _rgb(end)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * abs(t)) for x, y in zip(a, b))


def text_color(fill: str) -> str:
    """Ink scuro o chiaro in base alla luminanza della cella (contrasto leggibile)."""
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(fill))
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return INK_ON_LIGHT if luminance > 0.30 else INK_ON_DARK


def _hour_span(diff: list) -> tuple[int, int]:
    """Prima e ultima ora con almeno una cella, per non disegnare 24 colonne vuote."""
    hours = [h for row in diff for h, v in enumerate(row) if v is not None]
    return (min(hours), max(hours)) if hours else (0, 23)


def staffing_heatmap_spec(grid: dict, role: str, theme: str = "light") -> dict:
    """grid = StaffingResult.grid(role): matrici 7×24 diff / staffed / needed / customers."""
    c = THEMES.get(theme, THEMES["light"])
    first, last = _hour_span(grid["diff"])
    cols = list(range(first, last + 1))
    x = [f"{h:02d}:00" for h in cols]

    def cut(m):
        return [[row[h] for h in cols] for row in m]

    z = cut(grid["diff"])
    peak = max([abs(v) for row in z for v in row if v is not None] or [1]) or 1

    # Numeri nelle celle: un trace di testo sopra la heatmap, perché il testo
    # della heatmap ha un solo colore e su blu/rosso pieni non si leggerebbe.
    tx, ty, tt, tc = [], [], [], []
    for j, row in enumerate(z):
        for i, v in enumerate(row):
            if v in (None, 0):
                continue
            tx.append(x[i]); ty.append(DAY_LABELS[j])
            tt.append(f"{v:+d}".replace("-", "−"))
            tc.append(text_color(cell_color(v, peak, c)))
    custom = [[[s, n, cu] for s, n, cu in zip(rs, rn, rc)]
              for rs, rn, rc in zip(cut(grid["staffed"]), cut(grid["needed"]), cut(grid["customers"]))]

    return {
        "data": [{
            "type": "heatmap",
            "z": z, "x": x, "y": DAY_LABELS,
            "zmin": -peak, "zmax": peak, "zmid": 0,
            "colorscale": [[0.0, c["under"]], [0.5, c["mid"]], [1.0, c["over"]]],
            "xgap": 2, "ygap": 2,
            "customdata": custom,
            "hovertemplate": ("<b>%{y} %{x}</b><br>On shift: %{customdata[0]}"
                              "<br>Needed: %{customdata[1]}"
                              "<br>Customers/h: ~%{customdata[2]}<extra></extra>"),
            "hoverongaps": False,
            "colorbar": {
                "title": {"text": "On shift − needed", "font": {"color": c["muted"], "size": 12}},
                "tickvals": [-peak, 0, peak],
                "ticktext": [f"−{peak} missing", "matched", f"+{peak} extra"],
                "tickfont": {"color": c["muted"], "size": 11},
                "thickness": 12, "outlinewidth": 0, "len": 0.9,
            },
        }, {
            "type": "scatter", "mode": "text",
            "x": tx, "y": ty, "text": tt,
            "textfont": {"color": tc, "size": 12},
            "hoverinfo": "skip", "showlegend": False,
        }],
        "layout": {
            "title": {"text": f"{role}: staff on shift vs needed", "font": {"color": c["ink"], "size": 15},
                      "x": 0, "xanchor": "left"},
            "height": 330,
            "margin": {"l": 48, "r": 20, "t": 48, "b": 40},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "xaxis": {"side": "bottom", "tickfont": {"color": c["muted"], "size": 11},
                      "showgrid": False, "zeroline": False, "fixedrange": True},
            "yaxis": {"autorange": "reversed", "tickfont": {"color": c["muted"], "size": 12},
                      "showgrid": False, "zeroline": False, "fixedrange": True},
            "hoverlabel": {"font": {"size": 12}},
        },
    }
