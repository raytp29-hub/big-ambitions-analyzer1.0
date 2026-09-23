"""
analysis/schedule_compare.py
Confronto fra lo schedule ATTUALE del save e quello OTTIMIZZATO dal solver,
per la Health Check (Staffing — your schedule vs optimized).

- current_schedule_result(): trasforma i turni del save nello stesso formato
  dell'OptimizationResult (schedule + daily_shifts), così la griglia "stile gioco"
  (visualization/schedule_grid.py) disegna tutti e due allo stesso modo.
- compare_schedules(): ore e costo per dipendente e per ruolo, prima e dopo.

Costi = ore × salario orario (niente assicurazione/HR), come nello Schedule Optimizer:
i due numeri si confrontano alla pari.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pandas as pd

from analysis.business_alerts import hours_in_slot
from analysis.schedule_constraints import DAYS_OF_WEEK


def current_schedule_result(setup, shifts: pd.DataFrame) -> SimpleNamespace:
    """I turni del save di questo business → {schedule, daily_shifts} come l'optimizer.
    `setup` = SavedScheduleSetup (employees + employee_ids allineati); `shifts` = righe
    di snapshot.shifts del business. I turni di dipendenti non in `setup` vengono saltati."""
    uid_by_id = {str(i): e.uid for i, e in zip(setup.employee_ids, setup.employees)}
    schedule = {e.uid: {d: [] for d in DAYS_OF_WEEK} for e in setup.employees}
    daily = {d: {} for d in DAYS_OF_WEEK}
    for n, s in enumerate(shifts.itertuples()):
        uid = uid_by_id.get(str(s.employee_id))
        hours = hours_in_slot(int(s.start_hour), int(s.end_hour))
        if uid is None or not hours or not 1 <= int(s.day) <= 7:
            continue
        day = DAYS_OF_WEEK[int(s.day) - 1]
        sid = f"save_{n}"
        start = int(s.start_hour)
        daily[day][sid] = {"start": start, "end": start + len(hours),   # oltre 24 = dopo mezzanotte
                           "hours": len(hours), "type": "save"}
        schedule[uid][day].append(sid)
    return SimpleNamespace(schedule=schedule, daily_shifts=daily)


def hours_per_employee(result, employees) -> dict[str, int]:
    """uid → ore/settimana nello schedule `result` (attuale o ottimizzato)."""
    out = {}
    for e in employees:
        total = 0
        for day, sids in result.schedule.get(e.uid, {}).items():
            for sid in sids:
                info = result.daily_shifts.get(day, {}).get(sid)
                if info:
                    total += int(info.get("hours", info["end"] - info["start"]))
        out[e.uid] = total
    return out


@dataclass(frozen=True)
class EmployeeChange:
    name: str
    role: str
    wage: float
    current_hours: int
    optimized_hours: int

    @property
    def delta_hours(self) -> int:
        return self.optimized_hours - self.current_hours

    @property
    def delta_cost(self) -> float:
        return self.delta_hours * self.wage

    @property
    def status(self) -> str:
        """dropped | added | fewer | more | same"""
        if self.current_hours > 0 and self.optimized_hours == 0:
            return "dropped"
        if self.current_hours == 0 and self.optimized_hours > 0:
            return "added"
        if self.delta_hours < 0:
            return "fewer"
        if self.delta_hours > 0:
            return "more"
        return "same"


@dataclass(frozen=True)
class RoleChange:
    role: str
    current_hours: int
    optimized_hours: int
    current_cost: float
    optimized_cost: float

    @property
    def delta_hours(self) -> int:
        return self.optimized_hours - self.current_hours

    @property
    def delta_cost(self) -> float:
        return self.optimized_cost - self.current_cost


@dataclass(frozen=True)
class ScheduleComparison:
    employees: list = field(default_factory=list)   # list[EmployeeChange]
    roles: list = field(default_factory=list)       # list[RoleChange]

    @property
    def current_cost(self) -> float:
        return sum(e.current_hours * e.wage for e in self.employees)

    @property
    def optimized_cost(self) -> float:
        return sum(e.optimized_hours * e.wage for e in self.employees)

    @property
    def current_hours(self) -> int:
        return sum(e.current_hours for e in self.employees)

    @property
    def optimized_hours(self) -> int:
        return sum(e.optimized_hours for e in self.employees)

    @property
    def saving(self) -> float:
        """> 0 = l'ottimizzato costa meno."""
        return self.current_cost - self.optimized_cost


def compare_schedules(employees, current, optimized) -> ScheduleComparison:
    now = hours_per_employee(current, employees)
    opt = hours_per_employee(optimized, employees)
    changes = [EmployeeChange(e.name, e.role, float(e.hourly_wage), now[e.uid], opt[e.uid])
               for e in employees]
    roles = {}
    for c in changes:
        r = roles.setdefault(c.role, [0, 0, 0.0, 0.0])
        r[0] += c.current_hours
        r[1] += c.optimized_hours
        r[2] += c.current_hours * c.wage
        r[3] += c.optimized_hours * c.wage
    role_rows = [RoleChange(role, *v) for role, v in sorted(roles.items())]
    order = {"dropped": 0, "fewer": 1, "more": 2, "added": 3, "same": 4}
    changes.sort(key=lambda c: (order[c.status], c.role, c.name))
    return ScheduleComparison(employees=changes, roles=role_rows)


def run_saved_business(bundle, address: str, window_days: int = 14):
    """Carica il business dal save (come lo Step 0 dello Schedule Optimizer) e lancia il
    solver a turni variabili con i clienti reali. Restituisce (setup, current, result);
    (None, None, None) se il tipo di business non è nel game data."""
    from analysis.schedule_from_save import load_schedule_setup
    from analysis.schedule_optimizer import optimize_schedule_variable
    from analysis.staffing_fit import NEED_BUFFER

    setup = load_schedule_setup(bundle, address, window_days=window_days)
    if setup is None:
        return None, None, None
    shifts = bundle.snapshot.shifts
    current = current_schedule_result(setup, shifts[shifts["address"] == address])
    result = optimize_schedule_variable(
        business_setup=setup.building,
        employees=setup.employees,
        weekly_schedule=setup.weekly_schedule,
        max_simultaneous=setup.max_simultaneous,
        selected_furniture=setup.selected_furniture,
        customers_by_hour=setup.customers_by_hour,
        need_buffer=NEED_BUFFER if setup.customers_by_hour else 1.0,
    )
    return setup, current, result
