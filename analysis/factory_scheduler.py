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

    Constraints: 1 worker per workstation per shift, 1 shift/day per
    worker, at most `max_days_per_week` working days, critical schedule
    demands respected. Wages never exclude anyone; they only break ties
    (fewest days worked first, then lowest wage).

    Without a production plan, shifts are filled in order (all machines
    of shift 1, then shift 2, ...). With `groups` (ordered by priority),
    filling is per RECIPE across all shifts: the highest-value recipe is
    saturated for the whole day before any worker goes to the next one,
    so scarce worker-hours maximize production value.

    `assignments[day][shift]` is positional: index i = machine slot i
    (None = uncovered slot), so the grid can map workers to machines.
    """
    open_days = open_days or list(DAYS_OF_WEEK)
    shifts = generate_factory_shifts(start_hour, end_hour)

    group_layout = [(g['label'], int(g['n_machines'])) for g in (groups or [])
                    if int(g.get('n_machines', 0)) > 0]
    if group_layout:
        n_workstations = sum(n for _, n in group_layout)
    covered_by_group = {label: 0.0 for label, _ in group_layout}

    # slot index -> group label (None when no plan is used)
    slot_group = []
    for label, n in group_layout:
        slot_group.extend([label] * n)
    if not slot_group:
        slot_group = [None] * n_workstations

    days_worked = {e.uid: 0 for e in employees}
    assignments, uncovered, shifts_by_day = {}, {}, {}
    covered = total = wages = 0.0

    for day in DAYS_OF_WEEK:
        if day not in open_days:
            continue
        shifts_by_day[day] = shifts
        used_today = set()
        slots = {sh['name']: [None] * n_workstations for sh in shifts}
        total += n_workstations * sum(sh['hours'] for sh in shifts)

        # fill order: column-major (recipe first) with a plan,
        # row-major (shift first) without
        if group_layout:
            fill_order = []
            offset = 0
            for label, n in group_layout:
                for sh in shifts:
                    for k in range(n):
                        fill_order.append((sh, offset + k))
                offset += n
        else:
            fill_order = [(sh, k) for sh in shifts for k in range(n_workstations)]

        for sh, slot in fill_order:
            cands = [e for e in employees
                     if e.uid not in used_today
                     and days_worked[e.uid] < max_days_per_week
                     and not _shift_blocked_by_demands(e, sh['type'])]
            if not cands:
                continue
            # spread the week first (fewest days worked), then lowest wage
            cands.sort(key=lambda e: (days_worked[e.uid], e.hourly_wage))
            emp = cands[0]
            slots[sh['name']][slot] = emp.uid
            used_today.add(emp.uid)
            covered += sh['hours']
            wages += emp.hourly_wage * sh['hours']
            g = slot_group[slot]
            if g is not None:
                covered_by_group[g] += sh['hours']

        assignments[day] = {}
        uncovered[day] = {}
        for sh in shifts:
            filled = slots[sh['name']]
            assignments[day][sh['name']] = filled
            uncovered[day][sh['name']] = sum(1 for u in filled if u is None)
        for uid in used_today:
            days_worked[uid] += 1

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
