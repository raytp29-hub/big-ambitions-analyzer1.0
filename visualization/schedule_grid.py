"""
Schedule Grid - prep + rendering per la visualizzazione stile gioco.
1) Trasforma l'output dell'optimizer in un'assegnazione esplicita addetto->postazione.
2) Genera la griglia come HTML autosufficiente (righe = postazioni, colonne = ore),
   da iniettare in Streamlit con st.components.v1.html().
"""
from typing import List, Dict, Tuple
import html as _html
from analysis.schedule_constraints import DAYS_OF_WEEK


# Colori per ruolo (tono simile ai blocchi del gioco)
ROLE_COLORS = {
    'Customer Service': '#f59e0b',   # arancione (cash register)
    'Cleaning': '#14b8a6',           # teal (cleaning station)
    'Security Guard': '#6366f1',     # indaco
    'Programmer': '#3b82f6',         # blu
    'Designer': '#ec4899',           # rosa
    'Office Worker': '#8b5cf6',      # viola
    'Factory Worker': '#f97316',     # arancio industriale (assembly machine)
}
_FALLBACK_COLORS = ['#ef4444', '#8b5cf6', '#10b981', '#3b82f6', '#ec4899']


def _role_color(role, _cache={}):
    """Colore stabile per un ruolo; assegna un fallback ai ruoli non mappati."""
    if role in ROLE_COLORS:
        return ROLE_COLORS[role]
    if role not in _cache:
        _cache[role] = _FALLBACK_COLORS[len(_cache) % len(_FALLBACK_COLORS)]
    return _cache[role]


def build_station_rows(selected_furniture: List[Dict]) -> List[Dict]:
    """
    Espande le furniture selezionate in singole POSTAZIONI (righe della griglia).
    Una furniture con quantity=3 diventa 3 postazioni distinte.
    Ritorna lista di dict: {id, name, role, capacity}. Solo workstation.
    """
    stations = []
    for furn in selected_furniture:
        if not furn.get('is_workstation', False):
            continue
        skills = list(furn.get('suitable_skills', []))
        role = skills[0] if skills else None
        qty = int(furn.get('quantity', 1))
        name = furn.get('name', 'Workstation')
        cap = int(furn.get('unit_capacity', 0))
        for k in range(1, qty + 1):
            station_id = f"{name} #{k}" if qty > 1 else name
            # `role` = primo skill (per colore/etichetta); `skills` = TUTTI i ruoli
            # che la postazione puo' ospitare (il match avviene su questi).
            stations.append({'id': station_id, 'name': name, 'role': role,
                             'skills': skills, 'capacity': cap})
    return stations


def assign_shift_employees(result, employees, stations) -> Dict[Tuple[str, str], list]:
    """
    Assegna ogni FINESTRA (turno) di un addetto a una postazione del suo ruolo,
    SENZA sovrapposizioni temporali sulla stessa postazione (interval scheduling).
    Vale per tutti i ruoli/postazioni.

    Ritorna {(day, station_id): [(start, end, emp_name, role), ...]}.
    """
    name_of = {e.uid: e.name for e in employees}

    # Una postazione e' disponibile per OGNI ruolo tra i suoi skill (non solo il
    # primo): cosi' i Programmer/Designer/ecc. trovano i loro banchi anche se la
    # postazione elenca un altro skill per primo.
    stations_by_role: Dict[str, List[Dict]] = {}
    for st in stations:
        roles = st.get('skills') or ([st['role']] if st.get('role') else [])
        for role in roles:
            stations_by_role.setdefault(role, []).append(st)
    for r in stations_by_role:
        stations_by_role[r].sort(key=lambda s: -s['capacity'])  # piu' capienti per prime

    assignment: Dict[Tuple[str, str], list] = {}
    for day in DAYS_OF_WEEK:
        day_shifts = result.daily_shifts.get(day, {})

        # 1) raccogli le finestre (start, end, emp) per ruolo
        intervals_by_role: Dict[str, list] = {}
        for emp in employees:
            for sid in result.schedule.get(emp.uid, {}).get(day, []):
                info = day_shifts.get(sid)
                if not info:
                    continue
                intervals_by_role.setdefault(emp.role, []).append(
                    (info['start'], info['end'], name_of.get(emp.uid, emp.uid), emp.role)
                )

        # 2) greedy per ruolo: ordina per inizio, metti ogni finestra sulla prima
        #    postazione libera (ultimo turno finito <= inizio di questa).
        for role, intervals in intervals_by_role.items():
            sts = stations_by_role.get(role, [])
            if not sts:
                continue
            last_end = {st['id']: -1 for st in sts}
            for (s, en, emp, rl) in sorted(intervals, key=lambda iv: iv[0]):
                placed = False
                for st in sts:
                    if last_end[st['id']] <= s:
                        assignment.setdefault((day, st['id']), []).append((s, en, emp, rl))
                        last_end[st['id']] = en
                        placed = True
                        break
                if not placed:
                    # piu' concorrenti delle postazioni (raro: Vincolo A lo limita):
                    # usa quella che si libera prima.
                    st = min(sts, key=lambda st: last_end[st['id']])
                    assignment.setdefault((day, st['id']), []).append((s, en, emp, rl))
                    last_end[st['id']] = en
    return assignment


def build_day_html(day, result, stations, assignment, employees, row_h=46) -> str:
    """
    Griglia HTML autosufficiente di un singolo giorno (stile gioco):
      righe = postazioni, colonne = ore, blocchi colorati = turni con nome.
    Stili inline + colori espliciti: nessuna dipendenza dal tema esterno.
    """
    role_of = {e.name: e.role for e in employees}
    day_shifts = result.daily_shifts.get(day, {})
    if not day_shifts or not stations:
        return ("<div style=\"font-family:sans-serif;color:#888;padding:12px;\">"
                "Nessun turno da mostrare per questo giorno.</div>")

    xmin = min(s['start'] for s in day_shifts.values())
    xmax = max(s['end'] for s in day_shifts.values())
    n_hours = max(xmax - xmin, 1)

    blocks_by_station: Dict[str, list] = {}
    for (d, station_id), blocks in assignment.items():
        if d != day:
            continue
        blocks_by_station.setdefault(station_id, []).extend(blocks)

    cols = f"120px repeat({n_hours}, minmax(0,1fr))"
    p = [f"<div style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
         f"background:#2f3640;border-radius:10px;padding:12px;\">"
         f"<div style=\"display:grid;grid-template-columns:{cols};"
         f"grid-auto-rows:{row_h}px;gap:3px;font-size:11px;\">"]

    # header ore
    p.append("<div style=\"grid-row:1;grid-column:1;\"></div>")
    for i in range(n_hours):
        h = xmin + i
        p.append(f"<div style=\"grid-row:1;grid-column:{i+2};text-align:center;"
                 f"color:#9aa3ad;align-self:center;\">{h % 24:02d}</div>")

    # righe postazioni
    for r, st in enumerate(stations):
        row = r + 2
        p.append(f"<div style=\"grid-row:{row};grid-column:1;display:flex;align-items:center;"
                 f"color:#cfd6de;font-weight:500;overflow:hidden;\">{_html.escape(str(st['id']))}</div>")
        p.append(f"<div style=\"grid-row:{row};grid-column:2 / {n_hours+2};"
                 f"background:#3a4250;border-radius:6px;\"></div>")
        for (start, end, emp, role) in blocks_by_station.get(st['id'], []):
            c0 = start - xmin + 2
            c1 = end - xmin + 2
            color = _role_color(role)
            p.append(
                f"<div style=\"grid-row:{row};grid-column:{c0} / {c1};background:{color};"
                f"color:#1a1a1a;border-radius:6px;padding:3px 7px;display:flex;"
                f"flex-direction:column;justify-content:center;overflow:hidden;\">"
                f"<span style=\"font-weight:600;white-space:nowrap;overflow:hidden;"
                f"text-overflow:ellipsis;\">{_html.escape(str(emp))}</span>"
                f"<span style=\"font-size:10px;opacity:0.85;\">{start % 24:02d}–{end % 24:02d}</span>"
                f"</div>"
            )

    p.append("</div></div>")
    return "".join(p)
