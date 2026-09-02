"""
Factory Planning section for the Schedule Optimizer.

Factories don't serve customers: production runs on workstations
(assembly machine + production machines) executing recipes. This module
renders workstation/machine requirements, recipe economics (produce vs
buy wholesale) and a production calculator.

Production SPEED is not present in the extracted game data (it lives in
compiled code), so throughput is an optional user-measured input.
"""
import math

import pandas as pd
import streamlit as st

from core.game_data import (
    get_factory_workstations,
    get_recipe_economics,
    get_factory_production_plan,
    get_data_source_info,
)


def _fmt_money(v):
    return f"${v:,.2f}" if v is not None else "—"


def render_factory_planning():
    st.subheader("🏭 Factory Planning")
    st.caption(
        "Factories produce goods with workstations instead of serving customers. "
        "Pick a workstation to see required machines and recipe economics."
    )

    workstations = get_factory_workstations()
    if not workstations:
        info = get_data_source_info()
        st.warning(
            "No factory workstation data found in game data.\n\n"
            f"Loaded JSON: `{info['path']}`\n\n"
            "This file predates the 1.0 extraction (no 'factory_workstations' "
            "section). Make sure the repo's own big_ambitions_game_data.json is "
            "the one being loaded and restart the app."
        )
        return

    ws = st.selectbox(
        "Workstation",
        options=workstations,
        format_func=lambda w: f"{w['display_name']} — {len(w['recipes'])} recipes",
        key="factory_workstation",
    )

    # ----------------------------------------------------------------
    # Required machines
    # ----------------------------------------------------------------
    st.markdown("**Required machines**")
    mdf = pd.DataFrame([
        {
            "Machine": m["name"],
            "Role": "Assembly" if m["role"] == "assembly" else "Production",
            "Price": m["price"],
        }
        for m in ws["machines"]
    ])
    st.dataframe(
        mdf,
        hide_index=True,
        use_container_width=True,
        column_config={"Price": st.column_config.NumberColumn(format="$%d")},
    )
    st.caption(f"Total machine investment: {_fmt_money(ws['total_machine_cost'])}")

    # ----------------------------------------------------------------
    # Recipe economics: produce vs buy wholesale
    # ----------------------------------------------------------------
    st.markdown("**Recipe economics** (ingredient costs at wholesale prices)")
    rows = []
    for rname in ws["recipes"]:
        eco = get_recipe_economics(rname)
        if eco is None:
            continue
        rows.append({
            "Recipe": eco["display_name"],
            "Output": eco["output_name"],
            "Batch size": eco["output_amount"],
            "Batch cost": round(eco["batch_cost"], 2),
            "Cost/unit": round(eco["cost_per_unit"], 3),
            "Wholesale/unit": eco["output_wholesale"],
            "Savings vs wholesale %": round(eco["savings_vs_wholesale_pct"], 1)
                                      if eco["savings_vs_wholesale_pct"] is not None else None,
            "Market/unit": eco["output_market"],
            "Margin/unit @market": round(eco["margin_if_sold_at_market"], 2),
        })
    rdf = pd.DataFrame(rows).sort_values(
        "Savings vs wholesale %", ascending=False, na_position="last"
    )
    st.dataframe(
        rdf,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Batch cost": st.column_config.NumberColumn(format="$%.2f"),
            "Cost/unit": st.column_config.NumberColumn(format="$%.3f"),
            "Wholesale/unit": st.column_config.NumberColumn(format="$%.2f"),
            "Market/unit": st.column_config.NumberColumn(format="$%.2f"),
            "Margin/unit @market": st.column_config.NumberColumn(format="$%.2f"),
            "Savings vs wholesale %": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
    st.caption(
        "Savings vs wholesale = how much cheaper one unit is when produced "
        "instead of bought from wholesalers. Margin @market = profit per unit "
        "if sold at the default market price in your own stores."
    )

    # ----------------------------------------------------------------
    # Production calculator
    # ----------------------------------------------------------------
    st.markdown("**Production calculator**")
    col1, col2, col3 = st.columns(3)
    with col1:
        recipe_name = st.selectbox(
            "Recipe", options=ws["recipes"], key="factory_recipe"
        )
    with col2:
        target_units = st.number_input(
            "Target units", min_value=1, value=1000, step=100, key="factory_target"
        )
    with col3:
        batches_per_day = st.number_input(
            "Batches/day (optional, measured in game)",
            min_value=0.0, value=0.0, step=0.5, key="factory_speed",
            help="Production speed is not in the extracted game data. "
                 "Measure it in game and enter it here to get a time estimate.",
        )

    plan = get_factory_production_plan(recipe_name, int(target_units))
    if plan is None:
        st.warning("Recipe data not available.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Batches", plan["batches"])
    m2.metric("Units produced", plan["units_produced"])
    m3.metric("Ingredient cost", _fmt_money(plan["total_ingredient_cost"]))
    m4.metric("Savings vs wholesale", _fmt_money(plan["savings_vs_wholesale"]))

    if batches_per_day > 0:
        days = math.ceil(plan["batches"] / batches_per_day)
        st.info(f"⏱️ At {batches_per_day:g} batches/day: ~{days} in-game days.")

    st.markdown("**Shopping list (ingredients to order)**")
    sdf = pd.DataFrame([
        {
            "Ingredient": s["name"],
            "Total amount": s["total_amount"],
            "Wholesale/unit": s["unit_wholesale"],
            "Total cost": round(s["total_cost"], 2),
        }
        for s in plan["shopping_list"]
    ])
    st.dataframe(
        sdf,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Wholesale/unit": st.column_config.NumberColumn(format="$%.2f"),
            "Total cost": st.column_config.NumberColumn(format="$%.2f"),
        },
    )
    st.caption(
        f"Selling all {plan['units_produced']} units at market price: "
        f"{_fmt_money(plan['value_at_market'])} "
        f"(margin {_fmt_money(plan['margin_if_sold_at_market'])})."
    )



def render_factory_schedule():
    """Dedicated factory schedule: pure coverage + production plan.

    One worker per assembly workstation at a time; when a shift ends,
    another worker takes over. Wages never exclude a worker. The optional
    production plan assigns machines to recipes and prioritizes the most
    valuable ones when workers are scarce.
    """
    st.subheader("\U0001F5D3\uFE0F Factory Schedule (dedicated)")
    st.caption(
        "One worker per assembly workstation at a time; when a shift ends, "
        "another worker takes over. Goal: keep every workstation staffed "
        "for as many hours as possible. Wages never exclude a worker."
    )
    from analysis.factory_scheduler import optimize_factory_schedule, DAYS_OF_WEEK

    # --- workstations: derivate dalla furniture, override manuale ---
    selected_furniture = st.session_state.get("selected_furniture") or []
    factory_furniture = [
        f for f in selected_furniture
        if f.get("is_workstation") and "Factory Worker" in (f.get("suitable_skills") or [])
    ]
    placed = {}  # assembly display name -> quantity piazzata
    for f in factory_furniture:
        placed[f["name"]] = placed.get(f["name"], 0) + int(f.get("quantity", 1))
    derived_ws = sum(placed.values())

    c1, c2, c3 = st.columns(3)
    with c1:
        if derived_ws > 0:
            # il numero di workstation viene dalla Furniture Selection
            n_ws = int(derived_ws)
            st.metric("Assembly workstations", n_ws,
                      help="Derivate dalla Furniture Selection qui sopra")
        else:
            n_ws = st.number_input(
                "Assembly workstations", min_value=1, value=4, step=1,
                key="fs_n_ws",
                help="Nessuna assembly machine nella Furniture Selection: "
                     "valore manuale di fallback",
            )
    with c2:
        always_open = st.checkbox("Open 24/7", value=True, key="fs_247")
    with c3:
        max_days = st.number_input(
            "Max working days/week per employee", min_value=1, max_value=7,
            value=6, key="fs_max_days",
        )
    if derived_ws > 0:
        st.caption("\U0001FA91 From furniture selection: "
                   + ", ".join(f"**{q}\u00D7 {n}**" for n, q in placed.items()))

    if always_open:
        start_h, end_h = 0, 24
        open_days = list(DAYS_OF_WEEK)
    else:
        start_h, end_h = st.slider(
            "Operating hours", 0, 24, (0, 24), key="fs_hours")
        open_days = st.multiselect(
            "Open days", DAYS_OF_WEEK, default=list(DAYS_OF_WEEK), key="fs_days")

    # --- production plan (opzionale) ---
    plan = _render_production_plan(placed)
    if plan:
        plan_ws = sum(g["n_machines"] for g in plan)
        st.caption(f"\U0001F4CB Production plan active: **{plan_ws}** machines across "
                   f"**{len(plan)}** recipes (priority = value/hour).")

    # --- dipendenti dallo Step 2 ---
    all_emps = st.session_state.get("employees", [])
    workers = [e for e in all_emps if e.role == "Factory Worker"]
    st.caption(f"\U0001F465 Factory Workers from Step 2: **{len(workers)}** "
               f"(other roles are ignored here)")
    if not workers:
        st.info("Add employees with role 'Factory Worker' in Step 2 first.")
        return

    if st.button("\U0001F680 Optimize factory schedule", key="fs_run"):
        st.session_state["fs_result"] = optimize_factory_schedule(
            workers, int(n_ws), start_h, end_h, open_days,
            max_days_per_week=int(max_days),
            groups=plan or None,
        )
        st.session_state["fs_plan_used"] = plan

    res = st.session_state.get("fs_result")
    if res is None:
        return
    plan_used = st.session_state.get("fs_plan_used") or []

    m1, m2, m3 = st.columns(3)
    m1.metric("Coverage", f"{res.coverage_pct:.0f}%")
    m2.metric("Machine-hours", f"{res.covered_machine_hours:.0f}/{res.total_machine_hours:.0f}")
    m3.metric("Wages/week", _fmt_money(res.wages_cost))

    _render_factory_grid(res, workers, factory_furniture)

    missing = res.workers_for_full_coverage - len(workers)
    if missing > 0:
        st.warning(
            f"Full coverage needs **{res.workers_for_full_coverage}** Factory Workers "
            f"({missing} more than the current {len(workers)}) with "
            f"{int(max_days)} working days/week each."
        )
    else:
        st.success("Roster is large enough for full coverage. \U0001F389")

    _render_production_report(res, plan_used)


def _factory_recipe_catalog(placed):
    """Ricette producibili con le assembly machine piazzate.

    Un'assembly machine copre PIU' workstation type (es. la Consumer Goods
    Assembly Machine serve Clothing/Consumer Goods/Electronics/Jewelry):
    l'elenco raggruppa per tipo. Ritorna {recipe: {'ws': display, 'assembly': name}}.
    """
    catalog = {}
    for ws in get_factory_workstations():
        machines = ws.get("machines") or []
        asm = machines[0]["name"] if machines else None
        if asm not in placed:
            continue
        for r in ws.get("recipes", []):
            catalog.setdefault(r, {"ws": ws["display_name"], "assembly": asm})
    return catalog


def _render_production_plan(placed):
    """Editor del piano di produzione. Ritorna i gruppi ordinati per priorita'
    (value/hour decrescente): [{'label', 'n_machines', 'rate', 'value_unit'}]."""
    st.markdown("**\U0001F4CB Production Plan** *(optional — prioritizes recipes by value)*")
    if not placed:
        st.caption("Select assembly machines in the furniture step to enable the plan.")
        return []
    catalog = _factory_recipe_catalog(placed)
    if not catalog:
        st.caption("No recipe available for the selected assembly machines.")
        return []

    # filtro per tipo di workstation (stessi dati della Recipe Economics sopra)
    ws_types = sorted({v["ws"] for v in catalog.values()})
    type_filter = st.multiselect(
        "Workstation type filter",
        options=ws_types,
        key="fs_pp_ws_filter",
        help="Filtra le ricette per tipo di workstation; vuoto = tutte",
    )
    if type_filter:
        options = sorted(r for r, v in catalog.items() if v["ws"] in type_filter)
    else:
        options = sorted(catalog.keys())
    # non perdere ricette gia' scelte se il filtro cambia
    already = st.session_state.get("fs_pp_recipes", [])
    options = sorted(set(options) | {r for r in already if r in catalog})

    max_recipes = sum(placed.values())
    sel = st.multiselect(
        "Recipes to produce",
        options=options,
        format_func=lambda r: f"{r} \u2014 {catalog[r]['ws']}",
        key="fs_pp_recipes",
        max_selections=max_recipes,
        help=f"Max {max_recipes}: ogni ricetta occupa almeno una delle "
             f"{max_recipes} assembly machine piazzate",
    )
    if not sel:
        return []

    metric = st.selectbox(
        "Value metric", ["Savings vs wholesale", "Margin @market"],
        key="fs_pp_metric",
        help="Risparmio se produci per i tuoi negozi; margine se vendi a prezzo market",
    )

    rows = []
    for r in sel:
        c1, c2 = st.columns(2)
        with c1:
            m = st.number_input(f"Machines \u2014 {r}", min_value=0, value=1,
                                step=1, key=f"fs_pp_m_{r}")
        with c2:
            rate = st.number_input(
                f"Products/hour \u2014 {r} (measured in game)",
                min_value=0.0, value=0.0, step=1.0, key=f"fs_pp_r_{r}",
            )
        eco = get_recipe_economics(r)
        if eco:
            vu = (eco["savings_vs_wholesale"] if metric == "Savings vs wholesale"
                  else eco["margin_if_sold_at_market"])
            cu = eco["cost_per_unit"]
        else:
            vu, cu = 0.0, 0.0
        rows.append({
            "label": r, "n_machines": int(m), "rate": float(rate),
            "value_unit": float(vu), "value_hour": float(rate) * float(vu),
            "cost_unit": float(cu),
            "assembly": catalog[r]["assembly"], "ws": catalog[r]["ws"],
        })

    rows = [r for r in rows if r["n_machines"] > 0]
    if not rows:
        return []

    # vincolo: le macchine assegnate per assembly non superano quelle piazzate
    used_by_asm = {}
    for r in rows:
        used_by_asm[r["assembly"]] = used_by_asm.get(r["assembly"], 0) + r["n_machines"]
    for asm, used in used_by_asm.items():
        if used > placed.get(asm, 0):
            st.warning(f"\u26A0\uFE0F {asm}: assigned **{used}** machines but only "
                       f"**{placed.get(asm, 0)}** placed in the furniture step.")

    # priorita': value/hour decrescente; senza rate misurato si ripiega sul
    # valore unitario (segnalato) e si finisce comunque dopo chi ha il rate
    ordered = sorted(rows, key=lambda x: ((0, -x["value_hour"]) if x["rate"] > 0
                                          else (1, -x["value_unit"])))
    if any(r["rate"] <= 0 for r in rows):
        st.caption("\u2139\uFE0F Recipes without a measured products/hour are ranked last "
                   "(by value/unit): measure the rate in game for a correct priority.")

    prio_df = pd.DataFrame([
        {
            "Priority": i + 1,
            "Recipe": r["label"],
            "Workstation": r["ws"],
            "Machines": r["n_machines"],
            "Products/h": r["rate"] if r["rate"] > 0 else None,
            "Value/unit": round(r["value_unit"], 2),
            "Value/h per machine": round(r["value_hour"], 2) if r["rate"] > 0 else None,
        }
        for i, r in enumerate(ordered)
    ])
    st.dataframe(prio_df, hide_index=True, use_container_width=True)
    return ordered


class _FactoryGridResult:
    """Adapter: FactoryScheduleResult -> interfaccia attesa da build_day_html
    (serve solo result.daily_shifts)."""

    def __init__(self, res):
        self.daily_shifts = {
            day: {sh["name"]: {"start": sh["start"], "end": sh["end"]}
                  for sh in shifts}
            for day, shifts in res.shifts_by_day.items()
        }
        self.schedule = {}
        for day, by_shift in res.assignments.items():
            for shift_name, uids in by_shift.items():
                for uid in uids:
                    self.schedule.setdefault(uid, {}).setdefault(day, []).append(shift_name)


def _factory_stations(res, factory_furniture):
    """Righe della griglia. Con production plan: una riga per macchina,
    etichettata con la ricetta del gruppo (l'ordine rispecchia la priorita',
    cosi' la riga i-esima riceve l'i-esimo worker del turno). Senza piano:
    postazioni dalla furniture o sintetiche."""
    layout = res.group_layout or []
    if layout:
        stations = []
        for label, n_mach in layout:
            for i in range(1, n_mach + 1):
                sid = f"{label} #{i}" if n_mach > 1 else label
                stations.append({"id": sid, "name": label, "role": "Factory Worker",
                                 "skills": ["Factory Worker"], "capacity": 0})
        return stations

    from visualization.schedule_grid import build_station_rows
    n_ws = 0
    for day, day_unc in res.uncovered.items():
        for sh_name, free in day_unc.items():
            staffed = len(res.assignments.get(day, {}).get(sh_name, []))
            n_ws = max(n_ws, free + staffed)
    stations = build_station_rows(factory_furniture)
    if len(stations) != n_ws or not stations:
        stations = [
            {"id": f"Workstation #{i}", "name": "Workstation",
             "role": "Factory Worker", "skills": ["Factory Worker"], "capacity": 0}
            for i in range(1, n_ws + 1)
        ]
    return stations


def _render_factory_grid(res, workers, factory_furniture):
    """Griglia stile gioco (riusa build_day_html dello schedule business).
    L'assegnazione worker->postazione segue l'ordine del crew: il primo
    worker del turno va sulla prima macchina (gruppo a priorita' piu' alta)."""
    from visualization.schedule_grid import build_day_html
    import streamlit.components.v1 as components

    stations = _factory_stations(res, factory_furniture)
    if not stations:
        st.info("No workstation to display.")
        return
    uid2name = {e.uid: e.name for e in workers}

    assignment = {}
    for day, by_shift in res.assignments.items():
        shift_info = {sh["name"]: sh for sh in res.shifts_by_day[day]}
        for sname, uids in by_shift.items():
            sh = shift_info[sname]
            for i, uid in enumerate(uids):
                if i >= len(stations):
                    break
                sid = stations[i]["id"]
                assignment.setdefault((day, sid), []).append(
                    (sh["start"], sh["end"], uid2name.get(uid, uid), "Factory Worker"))

    open_days = list(res.assignments.keys())
    if not open_days:
        st.info("No open days to display.")
        return
    sel_day = st.radio("Day", open_days, horizontal=True, key="fs_grid_day")
    shim = _FactoryGridResult(res)
    grid_html = build_day_html(sel_day, shim, stations, assignment, workers)
    components.html(grid_html, height=46 * (len(stations) + 1) + 80, scrolling=True)


def _render_production_report(res, plan_used):
    """Produzione e valore settimanali stimati dal piano + copertura."""
    if not plan_used or not res.covered_hours_by_group:
        return
    st.markdown("**\U0001F4C8 Estimated weekly production**")
    rows, tot_value, tot_ing = [], 0.0, 0.0
    for g in plan_used:
        hours = res.covered_hours_by_group.get(g["label"], 0.0)
        units = hours * g["rate"] if g["rate"] > 0 else None
        value = units * g["value_unit"] if units is not None else None
        ing_cost = units * g.get("cost_unit", 0.0) if units is not None else None
        if value:
            tot_value += value
        if ing_cost:
            tot_ing += ing_cost
        rows.append({
            "Recipe": g["label"],
            "Covered machine-hours": round(hours, 1),
            "Units/week": round(units) if units is not None else None,
            "Ingredient cost/week": round(ing_cost, 2) if ing_cost is not None else None,
            "Value/week": round(value, 2) if value is not None else None,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={
                     "Ingredient cost/week": st.column_config.NumberColumn(format="$%.2f"),
                     "Value/week": st.column_config.NumberColumn(format="$%.2f"),
                 })
    if tot_value > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Production value/week", _fmt_money(tot_value))
        c2.metric("Ingredient orders/week", _fmt_money(tot_ing))
        c3.metric("Wages/week", _fmt_money(res.wages_cost))
        c4.metric("Net/week", _fmt_money(tot_value - res.wages_cost))
        st.caption(
            "Value/week e' GIA' al netto del costo ingredienti (savings/margin "
            "= prezzo \u2212 costo di produzione unitario). 'Ingredient orders/week' "
            "e' la spesa settimanale in ordini ai grossisti da sostenere per "
            "alimentare la produzione \u2014 utile per il cash flow, non va "
            "sottratta di nuovo dal netto."
        )
