"""
Business Health Check — Analysis Module
  1. Product ranking  2. Zone ranking  3. BEP  4. Performance (CSV)
"""
import math, pandas as pd, numpy as np
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional, Dict
from core.game_data import (
    get_products_for_business, get_item_by_name, get_demand_multipliers,
    get_building_sizes_for_category, BUILDING_TYPE_NAMES,
    _game_data, _items_by_id, _product_to_furniture,
)

# --- Helpers ---
DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

def _find_biz(name): return next((b for b in _game_data['business_types'] if b['m_Name'] == name), None)

def _demand_funcs(biz_name):
    d = get_demand_multipliers(biz_name)
    if not d: return None, None
    hourly, daily = d['hourly'], d['daily']
    return (
        lambda h: next((x['multiplier'] for x in hourly if x['start'] <= h < x['end']), 0.0),
        lambda dow: next((x['multiplier'] for x in daily if x['day'] == dow + 1), 1.0),
    )

def _weekly_cust(hm, dm, traffic, cap, start, end, days_mask=None):
    if days_mask is None: days_mask = [True] * 7
    days = [sum(min(traffic * hm(h) * dm(dow), cap) for h in range(start, end)) if days_mask[dow] else 0 for dow in range(7)]
    opens = sum(1 for c in days if c > 0)
    total = sum(days)
    return total, opens, (total / opens if opens else 0), days

# ============================================================================
# 1. PRODUCT RANKING
# ============================================================================
@dataclass
class ProductScore:
    name: str; internal_name: str; market_price: float; wholesale_price: float
    margin: float; sales_ratio: float; impact: float; effective_ratio: float; score: float

def rank_products(biz_name: str) -> List[ProductScore]:
    results = []
    for p in get_products_for_business(biz_name):
        item = get_item_by_name(p['internal_name'])
        sr = item.get('productSalesRatio', 1.0) if item else 1.0
        imp, eff = p.get('impact', 1.0), sr * p.get('impact', 1.0)
        margin = p['market'] - p['wholesale']
        results.append(ProductScore(p['name'], p['internal_name'], p['market'], p['wholesale'],
            round(margin, 2), round(sr, 2), round(imp, 2), round(eff, 4), round(margin * eff, 2)))
    return sorted(results, key=lambda x: -x.score)

# ============================================================================
# 2. ZONE RANKING
# ============================================================================
NEIGHBOURHOOD_NAMES = {0: 'Murray Hill', 1: 'Industry City', 2: 'Midtown',
    3: "Hell's Kitchen", 5: 'Lower Manhattan', 6: 'Garment District'}

@dataclass
class ZoneInfo:
    neighbourhood_id: int; name: str; avg_traffic: float; n_buildings: int; product_match: float

@dataclass
class BuildingOption:
    code: str; sqm: int; capacity: int

def rank_zones(biz_name: str, game_data: dict) -> List[ZoneInfo]:
    bt = _find_biz(biz_name)
    if not bt: return []
    products = bt.get('businessProducts', [])
    restrictions = [(_items_by_id.get(p['itemName']) or {}).get('limitDemandToNeighbourhoods', []) for p in products]
    by_neigh = defaultdict(list)
    for b in game_data['buildings']:
        if b['BuildingType'] == bt['suitableBuildingType']:
            by_neigh[b['Neighbourhood']].append(b)
    results = []
    for nid, bldgs in by_neigh.items():
        avg_t = sum(b['trafficIndex'] for b in bldgs) / len(bldgs)
        match = sum(1 for r in restrictions if not r or nid in r) / len(restrictions) if restrictions else 0
        results.append(ZoneInfo(nid, NEIGHBOURHOOD_NAMES.get(nid, f'Zone {nid}'), round(avg_t, 1), len(bldgs), round(match, 2)))
    return sorted(results, key=lambda x: (-x.product_match, -x.avg_traffic))

def get_building_options(biz_name: str, biz_types) -> List[BuildingOption]:
    bt = next((b for b in biz_types if b['m_Name'] == biz_name), None)
    if not bt: return []
    cat = BUILDING_TYPE_NAMES.get(bt['suitableBuildingType'])
    if not cat: return []
    return sorted([BuildingOption(f"{s['letter']}{v['number']}", s['sqm'], v['capacity'])
        for s in get_building_sizes_for_category(cat) for v in s['versions']], key=lambda x: -x.capacity)

# ============================================================================
# 3. BEP & THEORETICAL PROJECTION
# ============================================================================
@dataclass
class MinFurniture:
    name: str; products_served: List[str]; capacity_each: int; qty: int
    total_capacity: int; unit_price: float; total_price: float; is_workstation: bool

@dataclass
class BepResult:
    furniture: List[MinFurniture]; total_furniture_cost: float
    building_capacity: int; traffic_index: int
    profit_per_customer: float; rev_per_customer: float; cost_per_customer: float
    theo_daily_customers: float; theo_daily_revenue: float; theo_daily_wholesale: float
    daily_rent: float; daily_wages: float; n_employees: int; total_daily_costs: float
    daily_profit: float; bep_customers_per_day: float; bep_days_to_recover: float; is_profitable: bool

def compute_optimal_furniture(biz_name: str, cap: int, selected_products: List[str] = None) -> List[MinFurniture]:
    """Cheapest furniture for selected products (or all), scaled to building capacity."""
    bt = _find_biz(biz_name)
    if not bt: return []
    products = bt.get('businessProducts', [])
    if selected_products:
        products = [p for p in products if _items_by_id.get(p['itemName'], {}).get('m_Name') in selected_products]
    biz_skills = set(bt.get('employeePrimarySkills', []))
    prod_furn = {p['itemName']: sorted([f for f in _product_to_furniture.get(p['itemName'], []) if f.get('isFurniture')],
        key=lambda x: x.get('defaultMarketPrice', 0)) for p in products}

    selected, uncovered = {}, set(prod_furn.keys())
    while uncovered:
        best, best_covers, best_price = None, set(), float('inf')
        for pid in uncovered:
            for furn in prod_furn.get(pid, []):
                covers = {op for op in uncovered if furn in prod_furn.get(op, [])}
                price = furn.get('defaultMarketPrice', 0)
                if len(covers) > len(best_covers) or (len(covers) == len(best_covers) and price < best_price):
                    best, best_covers, best_price = furn, covers, price
        if not best: break
        selected[best['m_Name']] = (best, [_items_by_id[pid]['m_Name'] for pid in best_covers if pid in _items_by_id])
        uncovered -= best_covers

    if not any(d.get('assignable') for d, _ in selected.values()):
        ws = min((i for i in _game_data['items'] if i.get('assignable') and i.get('isFurniture')
                  and set(i.get('suitableSkills', [])) & biz_skills), key=lambda x: x.get('defaultMarketPrice', 0), default=None)
        if ws and ws['m_Name'] not in selected: selected[ws['m_Name']] = (ws, [])

    return [MinFurniture(fn, pn, fd.get('addedCustomersPerHour', 0),
            q := math.ceil(cap / fd['addedCustomersPerHour']) if fd.get('addedCustomersPerHour', 0) > 0 else 1,
            fd.get('addedCustomersPerHour', 0) * q, fd.get('defaultMarketPrice', 0),
            fd.get('defaultMarketPrice', 0) * q, bool(fd.get('assignable')))
        for fn, (fd, pn) in selected.items()]

def compute_bep(biz_name, cap, traffic, rent, wage, start=8, end=22, days_mask=None, selected_products=None):
    furniture = compute_optimal_furniture(biz_name, cap, selected_products)
    if not furniture: return None
    total_furn = sum(f.total_price for f in furniture)

    products = rank_products(biz_name)
    if selected_products:
        products = [p for p in products if p.internal_name in selected_products]
    if not products: return None
    rev_pc = sum(p.market_price * p.effective_ratio for p in products)
    cost_pc = sum(p.wholesale_price * p.effective_ratio for p in products)
    profit_pc = rev_pc - cost_pc

    hm, dm = _demand_funcs(biz_name)
    if not hm: return None
    _, _, avg_cust, _ = _weekly_cust(hm, dm, traffic, cap, start, end, days_mask)

    n_emp = max(1, sum(f.qty for f in furniture if f.is_workstation))
    wages = n_emp * wage * max(0, end - start)
    wholesale = avg_cust * cost_pc
    total_costs, revenue = rent + wages + wholesale, avg_cust * rev_pc
    profit = revenue - total_costs
    fixed = rent + wages
    bep_c = fixed / profit_pc if profit_pc > 0 else float('inf')
    bep_d = total_furn / profit if profit > 0 else float('inf')

    return BepResult(furniture, round(total_furn, 2), cap, traffic,
        round(profit_pc, 2), round(rev_pc, 2), round(cost_pc, 2),
        round(avg_cust, 1), round(revenue, 2), round(wholesale, 2),
        rent, round(wages, 2), n_emp, round(total_costs, 2),
        round(profit, 2), round(bep_c, 1), round(bep_d, 1), profit > 0)

# --- Schedule Analysis ---
@dataclass
class ScheduleAnalysis:
    coverage_pct: float; current_weekly: float; max_weekly: float
    missed_by_hours: List[dict]; missed_by_days: List[dict]

def analyze_schedule(biz_name, traffic, cap, start, end, days_mask):
    hm, dm = _demand_funcs(biz_name)
    if not hm: return None
    max_w, _, _, _ = _weekly_cust(hm, dm, traffic, cap, 0, 24)
    cur_w, _, _, _ = _weekly_cust(hm, dm, traffic, cap, start, end, days_mask)
    coverage = (cur_w / max_w * 100) if max_w > 0 else 0

    missed_hours = []
    for h in range(24):
        if start <= h < end: continue
        lost = sum(min(traffic * hm(h) * dm(dow), cap) for dow in range(7) if days_mask[dow])
        n = sum(days_mask)
        if lost > 0:
            missed_hours.append({'hour': f"{h:02d}:00", 'weekly_lost': round(lost, 1),
                'avg_daily_lost': round(lost / n, 1) if n else 0})
    missed_hours.sort(key=lambda x: -x['weekly_lost'])

    missed_days = [{'day': DAY_NAMES[dow], 'lost_customers': round(
        sum(min(traffic * hm(h) * dm(dow), cap) for h in range(start, end)), 1)}
        for dow in range(7) if not days_mask[dow]]
    missed_days = [d for d in missed_days if d['lost_customers'] > 0]
    missed_days.sort(key=lambda x: -x['lost_customers'])

    return ScheduleAnalysis(round(coverage, 1), round(cur_w, 1), round(max_w, 1),
        missed_hours[:5], missed_days)

# ============================================================================
# 4. PERFORMANCE CHECK
# ============================================================================
@dataclass
class PerformanceResult:
    theo_daily_revenue: List[float]; theo_daily_customers: List[float]
    theo_avg_revenue: float; rev_per_customer: float
    actual_data: pd.DataFrame; actual_avg_revenue: float; n_days: int
    performance_pct: float; trend: str; rating: str

def compute_performance(df, biz_display, biz_internal, traffic, cap, start=8, end=22, selected_products=None):
    products = rank_products(biz_internal)
    if selected_products:
        products = [p for p in products if p.internal_name in selected_products]
    if not products: return None
    rev_pc = sum(p.market_price * p.effective_ratio for p in products)

    hm, dm = _demand_funcs(biz_internal)
    if not hm: return None
    _, _, _, daily_c = _weekly_cust(hm, dm, traffic, cap, start, end)
    theo_cust = [round(c, 1) for c in daily_c]
    theo_rev = [round(c * rev_pc, 2) for c in daily_c]
    opens = [i for i in range(7) if theo_rev[i] > 0]
    theo_avg = sum(theo_rev) / len(opens) if opens else 0

    from analysis.revenue_analyzer import extract_business_name_from_string
    rev_df = df[df['type'] == 'Revenue'].copy()
    rev_df['business'] = rev_df['description'].apply(extract_business_name_from_string)
    daily_rev = rev_df[rev_df['business'] == biz_display].groupby('day')['price'].sum().reset_index()
    daily_rev.columns = ['game_day', 'revenue']
    if daily_rev.empty: return None

    cost_df = df[df['type'].isin(['Wage', 'Replacement Wage', 'Marketing', 'Health Insurance', 'HR Training'])].copy()
    cost_df = cost_df[cost_df['description'].str.lower().str.contains(biz_display.lower(), na=False, regex=False)]
    daily_costs = cost_df.groupby('day')['price'].sum().abs().reset_index()
    daily_costs.columns = ['game_day', 'costs']

    actual = daily_rev.merge(daily_costs, on='game_day', how='left')
    actual['costs'] = actual['costs'].fillna(0)
    actual['profit'] = actual['revenue'] - actual['costs']
    actual['day_of_week'] = (actual['game_day'].astype(int) - 1) % 7
    actual['theoretical'] = actual['day_of_week'].map(lambda d: theo_rev[d])
    actual = actual.sort_values('game_day').reset_index(drop=True)

    actual_avg = actual['revenue'].mean()
    perf_pct = (actual_avg / theo_avg * 100) if theo_avg > 0 else 0
    trend = 'stable'
    if len(actual) >= 3:
        slope = np.polyfit(np.arange(len(actual)), actual['revenue'].values, 1)[0]
        if slope > actual_avg * 0.02: trend = 'improving'
        elif slope < -actual_avg * 0.02: trend = 'declining'
    rating = 'Excellent' if perf_pct >= 85 else 'Good' if perf_pct >= 65 else 'Below Average' if perf_pct >= 40 else 'Poor'

    return PerformanceResult(theo_rev, theo_cust, round(theo_avg, 2), round(rev_pc, 2),
        actual, round(actual_avg, 2), len(actual), round(perf_pct, 1), trend, rating)

# ============================================================================
# 5. OPTIMIZER — find best product mix + schedule
# ============================================================================
@dataclass
class OptimalSetup:
    best_products: List[str]; best_start: int; best_end: int; best_days: List[bool]
    best_daily_profit: float; best_daily_revenue: float; best_daily_costs: float
    best_customers: float; n_employees: int
    current_daily_profit: float; current_daily_revenue: float; current_daily_costs: float
    current_customers: float; improvement_pct: float
    product_contributions: List[dict]  # [{name, margin, eff_ratio, profit_contrib}]
    schedule_heatmap: List[List[float]]  # 7 days × 24 hours profit matrix

def compute_optimal_setup(biz_name, cap, traffic, rent, wage, start=8, end=22,
                          days_mask=None, selected_products=None):
    """Find optimal product mix + schedule to maximize daily profit."""
    if days_mask is None: days_mask = [True] * 7
    hm, dm = _demand_funcs(biz_name)
    if not hm: return None

    all_prods = rank_products(biz_name)
    if not all_prods: return None

    # --- Product optimization: keep only margin-positive products ---
    profitable_prods = [p for p in all_prods if p.margin > 0]
    if not profitable_prods: profitable_prods = all_prods[:1]

    # Product contribution breakdown
    contributions = [{'name': p.name, 'internal': p.internal_name, 'margin': p.margin,
        'eff_ratio': p.effective_ratio, 'profit_contrib': round(p.margin * p.effective_ratio, 2)}
        for p in all_prods]

    best_names = [p.internal_name for p in profitable_prods]
    best_rev_pc = sum(p.market_price * p.effective_ratio for p in profitable_prods)
    best_cost_pc = sum(p.wholesale_price * p.effective_ratio for p in profitable_prods)
    best_profit_pc = best_rev_pc - best_cost_pc

    # --- Schedule optimization: try all start/end combos + day combos ---
    # Precompute hourly profit contribution per day-of-week
    furniture = compute_optimal_furniture(biz_name, cap, best_names)
    n_emp = max(1, sum(f.qty for f in furniture if f.is_workstation)) if furniture else 1
    hourly_wage_cost = n_emp * wage

    # Build profit heatmap: net profit per hour per day
    heatmap = []
    for dow in range(7):
        row = []
        for h in range(24):
            cust = min(traffic * hm(h) * dm(dow), cap)
            revenue = cust * best_profit_pc  # margin per customer × customers
            net = revenue - hourly_wage_cost  # subtract wage cost for that hour
            row.append(round(net, 2))
        heatmap.append(row)

    # Find best contiguous hour block + day selection
    best_profit, best_s, best_e, best_dm = -float('inf'), 8, 22, [True] * 7

    for s in range(0, 22):
        for e in range(s + 1, 25):
            # For each hour window, pick days where opening is profitable
            opt_days = [False] * 7
            for dow in range(7):
                day_profit = sum(heatmap[dow][h] for h in range(s, e))
                opt_days[dow] = day_profit > 0  # only open if that day is profitable

            if not any(opt_days): continue
            _, opens, avg_cust, _ = _weekly_cust(hm, dm, traffic, cap, s, e, opt_days)
            if opens == 0: continue

            daily_rev = avg_cust * best_rev_pc
            daily_wages = n_emp * wage * (e - s)
            daily_wholesale = avg_cust * best_cost_pc
            daily_profit = daily_rev - rent - daily_wages - daily_wholesale

            if daily_profit > best_profit:
                best_profit, best_s, best_e, best_dm = daily_profit, s, e, opt_days

    # Compute best scenario metrics
    _, b_opens, b_avg_c, _ = _weekly_cust(hm, dm, traffic, cap, best_s, best_e, best_dm)
    b_rev = b_avg_c * best_rev_pc
    b_wages = n_emp * wage * (best_e - best_s)
    b_wholesale = b_avg_c * best_cost_pc
    b_costs = rent + b_wages + b_wholesale

    # Compute current scenario
    cur_prods = [p for p in all_prods if not selected_products or p.internal_name in selected_products]
    if not cur_prods: cur_prods = all_prods
    cur_rev_pc = sum(p.market_price * p.effective_ratio for p in cur_prods)
    cur_cost_pc = sum(p.wholesale_price * p.effective_ratio for p in cur_prods)

    _, c_opens, c_avg_c, _ = _weekly_cust(hm, dm, traffic, cap, start, end, days_mask)
    c_rev = c_avg_c * cur_rev_pc
    c_wages = n_emp * wage * (end - start)
    c_wholesale = c_avg_c * cur_cost_pc
    c_costs = rent + c_wages + c_wholesale
    c_profit = c_rev - c_costs

    improvement = ((best_profit - c_profit) / abs(c_profit) * 100) if c_profit != 0 else 0

    return OptimalSetup(
        best_names, best_s, best_e, best_dm,
        round(best_profit, 2), round(b_rev, 2), round(b_costs, 2), round(b_avg_c, 1), n_emp,
        round(c_profit, 2), round(c_rev, 2), round(c_costs, 2), round(c_avg_c, 1),
        round(improvement, 1), contributions, heatmap)
