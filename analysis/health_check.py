import math


from dataclasses import dataclass
from typing import List
from collections import defaultdict

import pandas as pd

from core import game_data
from core.game_data import get_demand_multipliers, get_furniture_for_business, get_products_for_business, get_item_by_name, get_all_business_types, _game_data
from analysis.profit_loss import calculate_profit_loss
from analysis.revenue_analyzer import extract_business_name_from_string








MANDATORY_FURNITURE = [
    {"name": "Toilet",              "internal": "Toilet",              "price": 380},
    {"name": "Cleaning Station",    "internal": "CleaningStation",     "price": 100},
    {"name": "Cash Register",       "internal": "CashRegister",       "price": 900},
    {"name": "Security Guard Locker","internal": "SecurityGuardLocker","price": 2000},
]



@dataclass 
class ProductScore:
    name:str
    internal_name: str
    market_price: float
    wholesale_price: float
    margin: float
    sales_ratio: float
    impact: float
    probability: float
    score: float
    
    
    
def rank_products(biz_name: str) -> List[ProductScore]:
    products = get_products_for_business(biz_name)
    result = []
    
    
    for p in products:
        item = get_item_by_name(p['internal_name'])
        
        if item:
            sales_ratio = item.get('productSalesRatio', 1.0)
        else:
            sales_ratio = 1.0
            
            
        margin = p['market'] - p['wholesale']
        
        probability = sales_ratio * p['impact']
        
        score = margin * probability
        
        result.append(ProductScore(
            name=p['name'],
            internal_name=p['internal_name'],
            market_price=p['market'],
            wholesale_price=p['wholesale'],
            margin=margin,
            sales_ratio=sales_ratio,
            impact=p['impact'],
            probability=probability,
            score=score
        ))
        
    return sorted(result, key=lambda x:x.score, reverse=True)



# =====================================
# ZONE RANKING
# =====================================

NEIGHBOURHOOD_NAMES = {0: 'Murray Hill', 1: 'Industry City', 2: 'Midtown', 3: "Hell's Kitchen", 5: 'Lower Manhattan',
                       6: 'Garment District'}

@dataclass 
class ZoneInfo:
    neighbourhood_id: int
    name: str 
    avg_traffic: float
    n_buildings: float
    product_match: float
    
    
def rank_zone(biz_name:str) -> List[ZoneInfo]:
    business_types = get_all_business_types()
    bt = next((b for b in business_types if b["m_Name"] == biz_name), None)
    if not bt:
        return []
    
    building_type_id = bt["suitableBuildingType"]
    
    by_neighbourhood = defaultdict(list)
    for b in _game_data["buildings"]:
        if b["BuildingType"] == building_type_id:
            by_neighbourhood[b["Neighbourhood"]].append(b)
            
    result = []
    
    for nid, lista_edifici in by_neighbourhood.items():
        n_buildings = len(lista_edifici)
        avg_traffic = sum(b["trafficIndex"] for b in lista_edifici) / n_buildings
        
    
        result.append(ZoneInfo(
            nid,
            NEIGHBOURHOOD_NAMES.get(nid, f"Zone {nid}"),
            round(avg_traffic, 1),
            n_buildings,
            1.0
        ))
        
        
    return sorted(result, key= lambda x:x.avg_traffic, reverse=True)
    
   
def compute_recommended_hours(biz_name: str, threshold: float = 0.3) -> tuple[int, int]:
    """Recommended open/close hours based on heatmap values >= threshold."""
    demand = get_demand_multipliers(biz_name)
    hourly = demand['hourly']
    daily = demand['daily']
    avg_daily = sum(d['multiplier'] for d in daily) / len(daily)
    
    good_hours = []
    for h in hourly:
        for hour in range(h['start'], h['end']):
            if h['multiplier'] * avg_daily >= threshold:
                good_hours.append(hour)
    
    if not good_hours:
        return 8, 22
    return min(good_hours), max(good_hours) + 1

    
@dataclass
class MiniFurniture:
    name: str
    quantity: int
    price: float
    capacity: float
    is_workstation: bool
    

@dataclass
class BepResult:
    furniture: List[MiniFurniture]
    setup_cost: float
    employees: int
    revenue: float
    costs: float
    profit: float
    break_even: float
    daily_customers: float
    open_hour: int
    close_hour: int
    
    
def compute_bep(biz_name:str, building_cap: int, traffic: int, daily_rent: float, hourly_wage= 22.0):
    products = rank_products(biz_name)
    
    core_products = [p for p in products if p.impact >= 0.90]
    
    if not core_products:
        core_products = products[:3]
        
    furnitures = get_furniture_for_business(biz_name)
    
    needed_furniture = {}
    
    for p in core_products:
        for f in furnitures:
            if p.name in f["can_showcase"]:
                needed_furniture[f["item_name"]] = f
                break
            
            
            
            
            
    if not needed_furniture:
        cheapest = sorted(
            [f for f in furnitures if f["added_customers_per_hour"] > 0],
            key= lambda x: x["price"]
        )
        if cheapest:
            needed_furniture[cheapest[0]["item_name"]] = cheapest[0]
                
                
                
                
    
    furniture_list = []
    for f in needed_furniture.values():
        if f["added_customers_per_hour"] == 0:
            continue
        qty = math.ceil(building_cap / f["added_customers_per_hour"])
        furniture_list.append(MiniFurniture(
            name= f["display_name"],
            quantity= qty,
            price= f["price"],
            capacity= f["added_customers_per_hour"],
            is_workstation= f["is_workstation"]
        ))
        
        
               
    
    has_workstation = any(f.is_workstation for f in furniture_list)
    
    if not has_workstation:
        workstation = sorted(
            [f for f in furnitures if f["is_workstation"]], key= lambda x: x["price"]
        )
        if workstation:
            ws = workstation[0]
            furniture_list.append(MiniFurniture(
                name= ws["display_name"],
                quantity= 1,
                price= ws["price"],
                capacity= ws["added_customers_per_hour"],
                is_workstation= True
            ))
        
    
    
        # --- Mandatory furniture ---
    existing_names = {f.name for f in furniture_list}
    for mf in MANDATORY_FURNITURE:
        if mf["name"] not in existing_names:
            furniture_list.append(MiniFurniture(
                name=mf["name"],
                quantity=1,
                price=mf["price"],
                capacity=0,
                is_workstation=False
            ))

    
    
    
        
    n_employees = sum(f.quantity for f in furniture_list if f.is_workstation)
    if n_employees == 0:
        n_employees = 1
        
        
        
    demand = get_demand_multipliers(biz_name)
    hourly = demand["hourly"]
    daily = demand["daily"]
    
    
    furniture_cap = sum(f.capacity * f.quantity for f in furniture_list)
    effective_cap = min(furniture_cap, building_cap)
    

    rev_per_customer = sum(p.market_price * p.probability for p in core_products)
    cost_per_customer = sum(p.wholesale_price * p.probability for p in core_products)
    profit_per_customer = rev_per_customer - cost_per_customer
    hourly_wage_cost = n_employees * hourly_wage
    
    
    
    
    total_weekly_customers = 0
    total_profitable_hours = 0
    
    # 1. Orari ottimali (basati su media giornaliera)
    avg_daily_mult = sum(d['multiplier'] for d in daily) / len(daily)
    profitable_hours = set()

    for h in hourly:
        for hour in range(h['start'], h['end']):
            customers = min(traffic * h['multiplier'] * avg_daily_mult, effective_cap)
            hour_profit = (customers * profit_per_customer) - hourly_wage_cost
            if hour_profit > 0:
                profitable_hours.add(hour)

    open_hour = min(profitable_hours) if profitable_hours else 8
    close_hour = max(profitable_hours) + 1 if profitable_hours else 22



    for d in daily:
        for hour in range(open_hour, close_hour):
            h_mult = next((h['multiplier'] for h in hourly if h['start'] <= hour < h['end']), 0)
            customers = min(traffic * h_mult * d['multiplier'], effective_cap)
            total_weekly_customers += customers
            total_profitable_hours += 1       
            
    open_days = sum(1 for d in daily if any(
        min(traffic * h["multiplier"] * d["multiplier"], effective_cap) * profit_per_customer - hourly_wage_cost > 0 for h in hourly
    ))
    
    
    
    
    
    if open_days == 0:
        return None
    
    daily_customers = total_weekly_customers / open_days
    daily_revenue = daily_customers * rev_per_customer
    daily_wholesale = daily_customers * cost_per_customer
    daily_wages = (total_profitable_hours / open_days) * hourly_wage * n_employees
    daily_costs = daily_rent + daily_wages + daily_wholesale
    daily_profit = daily_revenue - daily_costs
    setup_cost = sum(f.price * f.quantity for f in furniture_list)
    break_even = setup_cost / daily_profit if daily_profit > 0 else float('inf')
    
    
    return BepResult(
        furniture= furniture_list,
        setup_cost= setup_cost,
        employees= n_employees,
        daily_customers= daily_customers,
        revenue= daily_revenue,
        costs= daily_costs,
        profit= daily_profit,
        break_even= break_even,
        open_hour= open_hour,
        close_hour= close_hour
    )
    
    
    
    
@dataclass
class PerformanceResult:
    actual_revenue: float
    theo_revenue: float
    actual_wages: float
    theo_wages: float
    performance_pct: float
    performance_wage: float
    rating: str
    n_days: int
    daily_data: pd.DataFrame
    
    
    
def compute_performance(df, business_name:str, bep: BepResult, hourly_wage: float = 22.0) -> PerformanceResult:
    pl = calculate_profit_loss(df)
    business_row = pl[pl["business"] == business_name]
    
    if business_row.empty:
        return None
    
    actual_revenue = business_row["revenue"].iloc[0]
    actual_wages = business_row["wages"].iloc[0]
    
    
    rev_df = df[df['type'] == 'Revenue'].copy()
    rev_df['business'] = rev_df['description'].apply(extract_business_name_from_string)
    daily_data = rev_df[rev_df['business'] == business_name].groupby('day')['price'].sum().reset_index()
    daily_data.columns = ['day', 'revenue']
    
    wage_df = df[df['type'].isin(['Wage', 'Replacement Wage'])].copy()
    wage_df['business'] = wage_df['description'].apply(
        lambda x: x.split("(")[1].split("Daily")[0].strip() if "(" in x else None
    )
    daily_wages = wage_df[wage_df['business'] == business_name].groupby('day')['price'].sum().abs().reset_index()
    daily_wages.columns = ['day', 'wages']
    
    
    daily_data = daily_data.merge(daily_wages, on='day', how='left')
    daily_data['wages'] = daily_data['wages'].fillna(0)
    
    
    n_days = len(daily_data)
    theo_revenue = bep.revenue
    theo_wages = bep.employees * hourly_wage * (bep.close_hour - bep.open_hour)
    
    avg_daily_revenue = actual_revenue / n_days
    avg_daily_wages = actual_wages / n_days
    
    performance_pct = (avg_daily_revenue / theo_revenue * 100) if theo_revenue > 0 else 0
    performance_wage = (avg_daily_wages / theo_wages * 100) if theo_wages > 0 else 0
    
    if performance_pct >= 85:
        rating = "Excellent"
    elif performance_pct >= 65:
        rating = "Good"
    elif performance_pct >= 40:
        rating = "Below Average"
    else:
        rating = "Poor"



    

    return PerformanceResult(
        actual_revenue=avg_daily_revenue,
        theo_revenue=theo_revenue,
        actual_wages=avg_daily_wages,
        theo_wages=theo_wages,
        performance_pct=round(performance_pct, 1),
        performance_wage=round(performance_wage,1),
        rating=rating,
        n_days=n_days,
        daily_data=daily_data
    )



# =====================================
# ACTION REPORT
# =====================================

@dataclass
class ReportItem:
    icon: str          # emoji
    priority: int      # 1 = highest
    title: str
    detail: str


def generate_report(perf: PerformanceResult, bep: BepResult, recommended_hours: tuple[int, int] = None) -> List[ReportItem]:

    """
    Generate an action-plan report based on performance vs theoretical.
    Returns a list of ReportItem sorted by priority (1 = most urgent).
    """
    items = []

    rev_pct = perf.performance_pct        # actual_rev / theo_rev * 100
    wage_pct = perf.performance_wage      # actual_wage / theo_wage * 100
    gap = wage_pct - rev_pct              # positive = wages growing faster than revenue

    daily_profit = perf.actual_revenue - perf.actual_wages
    payback = bep.setup_cost / daily_profit if daily_profit > 0 else float('inf')

    # DOPO
    if recommended_hours:
        rec_open, rec_close = recommended_hours
    else:
        rec_open, rec_close = bep.open_hour, bep.close_hour
    optimal_hours = f"{rec_open:02d}:00 - {rec_close:02d}:00"


    # --- 1. Wage/Revenue gap analysis ---
    if gap > 25:
        wage_excess = perf.actual_wages - perf.theo_wages
        items.append(ReportItem(
            icon="🔴",
            priority=1,
            title="Wages disproportionate to revenue",
            detail=(
                f"You're spending {wage_pct:.0f}% of theoretical wages "
                f"but earning only {rev_pct:.0f}% of theoretical revenue. "
                f"That's ~${wage_excess:,.0f}/day overspent. "
                f"Review your employee scheduling — optimal hours for this business are {optimal_hours}."
            )
        ))
    elif gap > 10:
        items.append(ReportItem(
            icon="🟡",
            priority=2,
            title="Wages slightly above revenue ratio",
            detail=(
                f"Wages are at {wage_pct:.0f}% vs revenue at {rev_pct:.0f}% of theoretical. "
                f"Consider tightening your schedule to {optimal_hours} to cut unnecessary labor costs."
            )
        ))
    else:
        items.append(ReportItem(
            icon="✅",
            priority=5,
            title="Wages in line with revenue",
            detail=(
                f"Your wage spend ({wage_pct:.0f}%) is proportional to your revenue ({rev_pct:.0f}%). "
                f"No scheduling changes needed."
            )
        ))

    # --- 2. Revenue performance ---
    if rev_pct >= 85:
        items.append(ReportItem(
            icon="✅",
            priority=5,
            title="Revenue is strong",
            detail=f"You're earning {rev_pct:.0f}% of the theoretical maximum. Great performance."
        ))
    elif rev_pct >= 50:
        items.append(ReportItem(
            icon="🟡",
            priority=3,
            title="Revenue below potential",
            detail=(
                f"You're earning {rev_pct:.0f}% of the theoretical maximum. "
                f"This could be caused by insufficient furniture, a low-traffic location, "
                f"or operating outside peak demand hours ({optimal_hours})."
            )
        ))
    else:
        items.append(ReportItem(
            icon="🔴",
            priority=1,
            title="Revenue critically low",
            detail=(
                f"You're only earning {rev_pct:.0f}% of theoretical revenue. "
                f"Check that you have enough furniture to serve customers, "
                f"and consider relocating to a higher-traffic zone."
            )
        ))

    # --- 3. Profitability / Break-even ---
    if daily_profit <= 0:
        items.append(ReportItem(
            icon="🔴",
            priority=1,
            title="Business is operating at a loss",
            detail=(
                f"Daily profit: -${abs(daily_profit):,.0f}. "
                f"Revenue (${perf.actual_revenue:,.0f}) does not cover wages (${perf.actual_wages:,.0f}). "
                f"Immediate action required: reduce staff hours or improve revenue."
            )
        ))
    elif payback > 60:
        items.append(ReportItem(
            icon="🟡",
            priority=3,
            title="Slow payback on investment",
            detail=(
                f"At current pace (${daily_profit:,.0f}/day profit), "
                f"it will take ~{payback:.0f} days to recover the ${bep.setup_cost:,.0f} setup cost."
            )
        ))
    else:
        items.append(ReportItem(
            icon="✅",
            priority=5,
            title="Healthy payback timeline",
            detail=(
                f"Daily profit: ${daily_profit:,.0f}. "
                f"Setup cost (${bep.setup_cost:,.0f}) recovered in ~{payback:.0f} days."
            )
        ))

    # --- 4. Scheduling suggestion (always show optimal hours) ---
    items.append(ReportItem(
        icon="🕐",
        priority=4,
        title="Recommended schedule",
        detail=(
            f"Based on the demand curve for this business type, "
            f"the most profitable operating hours are {optimal_hours} "
            f"with {bep.employees} employee(s). "
            f"Theoretical daily wages at optimal schedule: ${perf.theo_wages:,.0f}."
        )
    ))

    return sorted(items, key=lambda x: x.priority)