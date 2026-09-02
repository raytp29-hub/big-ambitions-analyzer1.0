"""
Dedicated factory scheduler — separate from the business optimizer.

A factory has no customer demand: production scales with staffed
workstation-hours (1 worker per assembly machine at a time; when a shift
ends another worker can take over). The objective is therefore PURE
COVERAGE: fill every workstation slot for as many hours as possible.
Wages NEVER gate the assignment — in Big Ambitions a staffed machine
produces far more value than any wage; economics are reported by the UI
(production plan), not decided here.

Deliberately NOT an LP: with identical stations and one role, a greedy
assignment (spread days first, then lowest wage) is optimal per shift
and transparent to the user. No new dependencies.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
                'Saturday', 'Sunday']


def classify_shift_type(start_hour: int) -> str:
    """Coarse shift type from its starting hour (mirrors the business one)."""
    s = start_hour % 24
    if 5 <= s < 12:
        return 'morning'
    if 12 <= s < 18:
        return 'afternoon'
    return 'night'


def generate_factory_shifts(start_hour: int, end_hour: int) -> List[dict]:
    """
    Split the operating window into consecutive shifts of ~8 hours.
    Unlike the business generator, a 24h window yields THREE shifts
    (0-8, 8-16, 16-24), so round-the-clock coverage is actually possible.
    Overnight windows (end < start) are supported.
    """
    total = (end_hour - start_hour) % 24
    if total == 0:
        total = 24
    shifts = []
    cursor = 0
    i = 1
    while cursor < total:
        length = min(8, total - cursor)
        # avoid a stub shift: merge a leftover < 4h into the previous one
        if length < 4 and shifts:
            shifts[-1]['end'] += length
            shifts[-1]['hours'] += length
            break
        s = (start_hour + cursor) % 24
        shifts.append({
            'name': f'shift_{i}',
            'start': s,
            'end': s + length,
            'hours': length,
            'type': classify_shift_type(s),
        })
        cursor += length
        i += 1
    return shifts


def _shift_blocked_by_demands(employee, shift_type: str) -> bool:
    """Minimal, self-contained check of schedule demands (critical only)."""
    blocked = set()
    for d in getattr(employee, 'demands', []) or []:
        if getattr(d, 'category', None) != 'schedule':
            continue
        if getattr(d, 'priority', 'critical') != 'critical':
            continue
        c = getattr(d, 'constraint', '')
        if c == 'no_morning':
            blocked.add('morning')
        elif c == 'no_afternoon':
            blocked.add('afternoon')
        elif c in ('no_evening', 'no_night'):
            blocked.add('night')
        if c == 'no_evening':
            blocked.add('afternoon')
    return shift_type in blocked


@dataclass
class FactoryScheduleResult:
    assignments: Dict[str, Dict[str, List[str]]]   # day -> shift_name -> [emp UIDs]
    shifts_by_day: Dict[str, List[dict]]
    covered_machine_hours: float
    total_machine_hours: float
    wages_cost: float
    uncovered: Dict[str, Dict[str, int]]           # day -> shift -> free slots
    workers_for_full_coverage: int = 0
    # production-plan groups (ordered by priority); empty when no plan is used
    group_layout: List[tuple] = None               # [(label, n_machines), ...]
    covered_hours_by_group: Dict[str, float] = None

    @property
    def coverage_pct(self) -> float:
        return (self.covered_machine_hours / self.total_machine_hours * 100) \
            if self.total_machine_hours else 0.0


def optimize_factory_schedule(
    employees: List,
    n_workstations: int,
    start_hour: int = 0,
    end_hour: int = 24,
    open_days: Optional[List[str]] = None,
    max_days_per_week: int = 6,
    groups: Optional[List[dict]] = None,
) -> FactoryScheduleResult:
    """
    Greedy pure-coverage scheduler.

    For each day and shift, fill up to `n_workstations` slots with the
    available Factory Workers (1 shift/day each, at most
    `max_days_per_week` working days, critical schedule demands
    respected). Wages never exclude anyone: they only break ties
    (fewest days worked first, then lowest wage) and are reported.
    """
    open_days = open_days or list(DAYS_OF_WEEK)
    shifts = generate_factory_shifts(start_hour, end_hour)
    roster = sorted(employees, key=lambda e: e.hourly_wage)

    # production plan: groups are ORDERED by priority (highest value first).
    # The crew of each shift fills machines in group order, so scarce
    # worker-hours go to the most valuable recipes first.
    group_layout = [(g['label'], int(g['n_machines'])) for g in (groups or [])
                    if int(g.get('n_machines', 0)) > 0]
    if group_layout:
        n_workstations = sum(n for _, n in group_layout)
    covered_by_group = {label: 0.0 for label, _ in group_layout}

    days_worked = {e.uid: 0 for e in roster}
    assignments, uncovered, shifts_by_day = {}, {}, {}
    covered = total = wages = 0.0

    for day in DAYS_OF_WEEK:
        if day not in open_days:
            continue
        shifts_by_day[day] = shifts
        assignments[day] = {}
        uncovered[day] = {}
        used_today = set()
        for sh in shifts:
            # chi ha lavorato meno giorni ha priorita' (spalma la settimana),
            # a parita' vince il salario piu' basso
            roster = sorted(roster, key=lambda e: (days_worked[e.uid], e.hourly_wage))
            total += n_workstations * sh['hours']
            crew = []
            for emp in roster:
                if len(crew) >= n_workstations:
                    break
                if emp.uid in used_today:
                    continue
                if days_worked[emp.uid] >= max_days_per_week:
                    continue
                if _shift_blocked_by_demands(emp, sh['type']):
                    continue
                crew.append(emp)
                used_today.add(emp.uid)
                covered += sh['hours']
                wages += emp.hourly_wage * sh['hours']
            for emp in crew:
                days_worked[emp.uid] += 1
            assignments[day][sh['name']] = [e.uid for e in crew]
            uncovered[day][sh['name']] = n_workstations - len(crew)
            if group_layout:
                offset = 0
                staffed = len(crew)
                for label, n_mach in group_layout:
                    got = min(max(staffed - offset, 0), n_mach)
                    covered_by_group[label] += got * sh['hours']
                    offset += n_mach

    # headcount for full coverage: every slot of every shift, every open day,
    # with each worker doing 1 shift/day and max_days_per_week days.
    slot_shifts_per_week = n_workstations * len(shifts) * len(
        [d for d in DAYS_OF_WEEK if d in open_days])
    import math
    full = math.ceil(slot_shifts_per_week / max(1, max_days_per_week))

    return FactoryScheduleResult(
        assignments=assignments,
        shifts_by_day=shifts_by_day,
        covered_machine_hours=covered,
        total_machine_hours=total,
        wages_cost=wages,
        uncovered=uncovered,
        workers_for_full_coverage=full,
        group_layout=group_layout,
        covered_hours_by_group=covered_by_group,
    )
