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

    render_factory_schedule()


def render_factory_schedule():
    """Dedicated factory schedule: maximize staffed workstation-hours."""
    st.divider()
    st.subheader("🗓️ Factory Schedule (dedicated)")
    st.caption(
        "One worker per assembly workstation at a time; when a shift ends, "
        "another worker takes over. Goal: keep every workstation staffed "
        "for as many hours as possible."
    )
    from analysis.factory_scheduler import optimize_factory_schedule, DAYS_OF_WEEK

    c1, c2, c3 = st.columns(3)
    with c1:
        n_ws = st.number_input(
            "Assembly workstations", min_value=1, value=4, step=1,
            key="fs_n_ws", help="Quante assembly machine hai piazzato in factory",
        )
    with c2:
        always_open = st.checkbox("Open 24/7", value=True, key="fs_247")
    with c3:
        max_days = st.number_input(
            "Max working days/week per employee", min_value=1, max_value=7,
            value=6, key="fs_max_days",
        )
    if always_open:
        start_h, end_h = 0, 24
        open_days = list(DAYS_OF_WEEK)
    else:
        start_h, end_h = st.slider(
            "Operating hours", 0, 24, (0, 24), key="fs_hours")
        open_days = st.multiselect(
            "Open days", DAYS_OF_WEEK, default=list(DAYS_OF_WEEK), key="fs_days")

    # --- valore economico dell'ora-macchina (opzionale) ---
    e1, e2 = st.columns(2)
    with e1:
        batches_per_hour = st.number_input(
            "Batches/hour per workstation (optional, measured in game)",
            min_value=0.0, value=0.0, step=0.1, key="fs_bph",
            help="0 = pure coverage mode: ignora i salari e riempi tutto",
        )
    with e2:
        metric = st.selectbox(
            "Value metric", ["Savings vs wholesale", "Margin @market"],
            key="fs_metric",
            help="Risparmio se produci per i tuoi negozi; margine se vendi a prezzo market",
        )
    value_per_hour = 0.0
    recipe_name = st.session_state.get("factory_recipe")
    if batches_per_hour > 0 and recipe_name:
        eco = get_recipe_economics(recipe_name)
        if eco:
            per_batch = (eco["savings_vs_wholesale"] if metric == "Savings vs wholesale"
                         else eco["margin_if_sold_at_market"]) * eco["output_amount"]
            value_per_hour = batches_per_hour * per_batch
            st.caption(
                f"Recipe **{eco['display_name']}**: {_fmt_money(per_batch)}/batch → "
                f"machine-hour value {_fmt_money(value_per_hour)}"
            )

    # --- dipendenti dallo Step 2 ---
    all_emps = st.session_state.get("employees", [])
    workers = [e for e in all_emps if e.role == "Factory Worker"]
    st.caption(f"👥 Factory Workers from Step 2: **{len(workers)}** "
               f"(other roles are ignored here)")
    if not workers:
        st.info("Add employees with role 'Factory Worker' in Step 2 first.")
        return

    if not st.button("🚀 Optimize factory schedule", key="fs_run"):
        return
    res = optimize_factory_schedule(
        workers, int(n_ws), start_h, end_h, open_days,
        value_per_hour=value_per_hour, max_days_per_week=int(max_days),
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Coverage", f"{res.coverage_pct:.0f}%")
    m2.metric("Machine-hours", f"{res.covered_machine_hours:.0f}/{res.total_machine_hours:.0f}")
    m3.metric("Wages/week", _fmt_money(res.wages_cost))
    if value_per_hour > 0:
        m4.metric("Net value/week", _fmt_money(res.net_value))

    # griglia giorni × turni
    rows = []
    for day, day_shifts in res.assignments.items():
        row = {"Day": day}
        for sh in res.shifts_by_day[day]:
            names = day_shifts.get(sh["name"], [])
            free = res.uncovered[day][sh["name"]]
            label = f"{sh['start']%24:02d}-{sh['end']%24 or 24:02d}"
            cell = ", ".join(names) if names else "—"
            if free > 0:
                cell += f"  (⚠️ {free} free)"
            row[label] = cell
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    missing = res.workers_for_full_coverage - len(workers)
    if missing > 0:
        st.warning(
            f"Full coverage needs **{res.workers_for_full_coverage}** Factory Workers "
            f"({missing} more than the current {len(workers)}) with "
            f"{int(max_days)} working days/week each."
        )
    else:
        st.success("Roster is large enough for full coverage. 🎉")
    if res.skipped_negative:
        st.info(
            "Not scheduled (wage ≥ machine-hour value): "
            + ", ".join(res.skipped_negative)
        )
