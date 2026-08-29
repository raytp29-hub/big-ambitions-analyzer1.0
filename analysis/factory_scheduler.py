"""
Dedicated factory scheduler — separate from the business optimizer.

A factory has no customer demand: production scales with staffed
workstation-hours (1 worker per assembly machine at a time; when a shift
ends another worker can take over). The objective is therefore to fill
every workstation slot for as many hours as possible, as long as the
value produced in that hour beats the worker's wage.

Deliberately NOT an LP: with identical stations and one role, a greedy
assignment (cheapest compatible worker first, per shift) is optimal per
shift and transparent to the user. No new dependencies.

value_per_hour <= 0 means "coverage mode": schedule everyone possible,
wages are reported but don't gate the assignment.
"""
from dataclasses import dataclass, field
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
    assignments: Dict[str, Dict[str, List[str]]]   # day -> shift_name -> [emp names]
    shifts_by_day: Dict[str, List[dict]]
    covered_machine_hours: float
    total_machine_hours: float
    wages_cost: float
    production_value: float
    uncovered: Dict[str, Dict[str, int]]           # day -> shift -> free slots
    skipped_negative: List[str] = field(default_factory=list)
    workers_for_full_coverage: int = 0

    @property
    def coverage_pct(self) -> float:
        return (self.covered_machine_hours / self.total_machine_hours * 100) \
            if self.total_machine_hours else 0.0

    @property
    def net_value(self) -> float:
        return self.production_value - self.wages_cost


def optimize_factory_schedule(
    employees: List,
    n_workstations: int,
    start_hour: int = 0,
    end_hour: int = 24,
    open_days: Optional[List[str]] = None,
    value_per_hour: float = 0.0,
    max_days_per_week: int = 6,
) -> FactoryScheduleResult:
    """
    Greedy coverage scheduler.

    For each day and shift, fill up to `n_workstations` slots picking the
    cheapest available Factory Workers (1 shift/day each, at most
    `max_days_per_week` working days, schedule demands respected).
    When value_per_hour > 0, a worker is scheduled only if
    value_per_hour > hourly_wage (economic mode).
    """
    open_days = open_days or list(DAYS_OF_WEEK)
    shifts = generate_factory_shifts(start_hour, end_hour)
    by_wage = sorted(employees, key=lambda e: e.hourly_wage)

    days_worked = {e.uid: 0 for e in by_wage}
    assignments, uncovered, shifts_by_day = {}, {}, {}
    covered = total = wages = value = 0.0
    skipped = set()

    for day in DAYS_OF_WEEK:
        if day not in open_days:
            continue
        shifts_by_day[day] = shifts
        assignments[day] = {}
        uncovered[day] = {}
        used_today = set()
        for sh in shifts:
            # chi ha lavorato meno giorni ha priorità (spalma la settimana),
            # a parità vince il salario più basso
            by_wage = sorted(by_wage, key=lambda e: (days_worked[e.uid], e.hourly_wage))
            total += n_workstations * sh['hours']
            crew = []
            for emp in by_wage:
                if len(crew) >= n_workstations:
                    break
                if emp.uid in used_today:
                    continue
                if days_worked[emp.uid] >= max_days_per_week:
                    continue
                if _shift_blocked_by_demands(emp, sh['type']):
                    continue
                if value_per_hour > 0 and emp.hourly_wage >= value_per_hour:
                    skipped.add(emp.name)
                    continue
                crew.append(emp)
                used_today.add(emp.uid)
                covered += sh['hours']
                wages += emp.hourly_wage * sh['hours']
                if value_per_hour > 0:
                    value += value_per_hour * sh['hours']
            for emp in crew:
                days_worked[emp.uid] += 1
            assignments[day][sh['name']] = [e.name for e in crew]
            uncovered[day][sh['name']] = n_workstations - len(crew)

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
        production_value=value,
        uncovered=uncovered,
        skipped_negative=sorted(skipped),
        workers_for_full_coverage=full,
    )
