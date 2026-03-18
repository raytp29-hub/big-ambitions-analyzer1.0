"""
Business Health Check Module
Compares actual player performance against theoretical potential
based on game data (demand curves, product margins, capacity).
"""

import pandas as pd
import numpy as np
from typing import List, Optional
from analysis.schedule_models import DailySchedule
from analysis.revenue_analyzer import extract_business_name_from_string
from core.game_data import (
    get_demand_multipliers,
    get_products_for_business,
    get_item_by_name,
    display_to_internal,
)


# Map day-of-week index (0=Mon ... 6=Sun) to game data day number (1=Mon ... 7=Sun)
_DOW_TO_GAME_DAY = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7}
_DAY_NAMES_ORDERED = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _get_hourly_multiplier(hourly_data: list, hour: int) -> float:
    """Get the demand multiplier for a specific hour from hourly ranges."""
    for h in hourly_data:
        if h['start'] <= hour < h['end']:
            return h['multiplier']
    return 0.0


def _get_daily_multiplier(daily_data: list, game_day_num: int) -> float:
    """Get the demand multiplier for a specific day of week (1-7)."""
    for d in daily_data:
        if d['day'] == game_day_num:
            return d['multiplier']
    return 1.0


def calculate_revenue_per_customer(business_internal_name: str) -> float:
    """
    Calculate expected revenue per customer visit.

    Uses product margins weighted by salesRatio: each customer generates
    revenue = sum(margin × salesRatio) across all products.
    """
    products = get_products_for_business(business_internal_name)
    if not products:
        return 0.0

    total_revenue_per_customer = 0.0
    for p in products:
        margin = p['market'] - p['wholesale']
        # Get salesRatio from item data
        item = get_item_by_name(p['internal_name'])
        sales_ratio = item.get('productSalesRatio', 1.0) if item else 1.0
        total_revenue_per_customer += margin * sales_ratio

    return total_revenue_per_customer


def calculate_theoretical_daily_revenue(
    business_internal_name: str,
    effective_capacity: int,
    weekly_schedule: List[DailySchedule],
) -> dict:
    """
    Calculate theoretical revenue for each day of the week.

    Returns:
        {
            'per_day_of_week': {0: revenue_mon, 1: revenue_tue, ...},
            'weekly_total': float,
            'avg_daily': float,  (average over open days only)
            'revenue_per_customer': float,
        }
    """
    demand = get_demand_multipliers(business_internal_name)
    rev_per_customer = calculate_revenue_per_customer(business_internal_name)

    if demand is None or rev_per_customer == 0:
        return {
            'per_day_of_week': {i: 0.0 for i in range(7)},
            'weekly_total': 0.0,
            'avg_daily': 0.0,
            'revenue_per_customer': rev_per_customer,
        }

    hourly_data = demand['hourly']
    daily_data = demand['daily']

    # Build schedule lookup: day_name -> DailySchedule
    schedule_map = {}
    for ds in weekly_schedule:
        schedule_map[ds.day_name] = ds

    per_day = {}
    open_days = 0

    for dow_idx, day_name in enumerate(_DAY_NAMES_ORDERED):
        ds = schedule_map.get(day_name)
        if ds is None or not ds.is_open:
            per_day[dow_idx] = 0.0
            continue

        open_days += 1
        game_day_num = _DOW_TO_GAME_DAY[dow_idx]
        daily_mult = _get_daily_multiplier(daily_data, game_day_num)

        daily_customers = 0.0
        for hour in range(ds.start_hour, ds.end_hour):
            hourly_mult = _get_hourly_multiplier(hourly_data, hour)
            hourly_customers = effective_capacity * hourly_mult * daily_mult
            daily_customers += hourly_customers

        per_day[dow_idx] = daily_customers * rev_per_customer

    weekly_total = sum(per_day.values())
    avg_daily = weekly_total / open_days if open_days > 0 else 0.0

    return {
        'per_day_of_week': per_day,
        'weekly_total': weekly_total,
        'avg_daily': avg_daily,
        'revenue_per_customer': rev_per_customer,
    }


def get_actual_daily_data(
    df: pd.DataFrame,
    business_display_name: str,
) -> pd.DataFrame:
    """
    Extract daily revenue and costs for a specific business from CSV.

    Returns DataFrame with columns:
        game_day, revenue, costs, profit, day_of_week (0=Mon..6=Sun)
    """
    # Revenue
    rev_df = df[df['type'] == 'Revenue'].copy()
    rev_df['business'] = rev_df['description'].apply(extract_business_name_from_string)
    rev_df = rev_df[rev_df['business'] == business_display_name]
    daily_revenue = rev_df.groupby('day')['price'].sum().reset_index()
    daily_revenue.columns = ['game_day', 'revenue']

    # Costs: wages, marketing, health insurance, hr training for this business
    cost_types = ['Wage', 'Replacement Wage', 'Marketing', 'Health Insurance', 'HR Training']
    cost_df = df[df['type'].isin(cost_types)].copy()

    # Filter costs belonging to this business (check if business name is in description)
    biz_lower = business_display_name.lower()
    cost_df = cost_df[cost_df['description'].str.lower().str.contains(biz_lower, na=False)]
    daily_costs = cost_df.groupby('day')['price'].sum().abs().reset_index()
    daily_costs.columns = ['game_day', 'costs']

    # Merge
    if daily_revenue.empty:
        return pd.DataFrame(columns=['game_day', 'revenue', 'costs', 'profit', 'day_of_week'])

    result = daily_revenue.merge(daily_costs, on='game_day', how='left')
    result['costs'] = result['costs'].fillna(0.0)
    result['profit'] = result['revenue'] - result['costs']

    # Map game day to day of week (Day 1 = Monday → 0)
    result['day_of_week'] = (result['game_day'].astype(int) - 1) % 7

    return result.sort_values('game_day').reset_index(drop=True)


def _detect_peak_hours(business_internal_name: str) -> Optional[dict]:
    """Find the peak demand hours for a business."""
    demand = get_demand_multipliers(business_internal_name)
    if demand is None:
        return None

    hourly_data = demand['hourly']
    # Find hours with multiplier > 0.5
    peak_hours = []
    for hour in range(24):
        mult = _get_hourly_multiplier(hourly_data, hour)
        if mult >= 0.5:
            peak_hours.append(hour)

    if not peak_hours:
        return None

    return {
        'start': min(peak_hours),
        'end': max(peak_hours) + 1,
        'hours': peak_hours,
    }


def compute_health_check(
    df: pd.DataFrame,
    business_display_name: str,
    business_internal_name: str,
    effective_capacity: int,
    weekly_schedule: List[DailySchedule],
) -> dict:
    """
    Main orchestrator: compute all health check metrics.

    Returns:
        {
            'performance_score': float (0-100+),
            'avg_daily_revenue': float,
            'avg_theoretical_revenue': float,
            'profit_margin': float (%),
            'cost_revenue_ratio': float (%),
            'daily_comparison': pd.DataFrame,
            'trend_direction': str,
            'diagnostics': List[dict],
            'rating': str,
            'theoretical': dict,
        }
    """
    # 1. Theoretical calculation
    theoretical = calculate_theoretical_daily_revenue(
        business_internal_name, effective_capacity, weekly_schedule
    )

    # 2. Actual data from CSV
    actual = get_actual_daily_data(df, business_display_name)

    # 3. Build daily comparison
    if not actual.empty:
        # Add theoretical revenue for each day based on day_of_week
        actual['theoretical'] = actual['day_of_week'].map(theoretical['per_day_of_week'])
        actual['performance_pct'] = np.where(
            actual['theoretical'] > 0,
            (actual['revenue'] / actual['theoretical'] * 100),
            0.0
        )

        avg_actual_rev = actual['revenue'].mean()
        avg_theoretical_rev = actual['theoretical'].mean()
        total_revenue = actual['revenue'].sum()
        total_costs = actual['costs'].sum()
        total_profit = actual['profit'].sum()

        performance_score = (avg_actual_rev / avg_theoretical_rev * 100) if avg_theoretical_rev > 0 else 0.0
        profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0.0
        cost_revenue_ratio = (total_costs / total_revenue * 100) if total_revenue > 0 else 0.0

        # Trend detection via linear regression on performance
        if len(actual) >= 3:
            x = np.arange(len(actual))
            y = actual['revenue'].values
            slope = np.polyfit(x, y, 1)[0]
            if slope > avg_actual_rev * 0.02:
                trend = 'improving'
            elif slope < -avg_actual_rev * 0.02:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'stable'
    else:
        avg_actual_rev = 0.0
        avg_theoretical_rev = theoretical['avg_daily']
        performance_score = 0.0
        profit_margin = 0.0
        cost_revenue_ratio = 0.0
        trend = 'stable'

    # 4. Rating
    if performance_score >= 85:
        rating = 'Excellent'
    elif performance_score >= 65:
        rating = 'Good'
    elif performance_score >= 40:
        rating = 'Below Average'
    else:
        rating = 'Poor'

    # 5. Diagnostics
    diagnostics = _generate_diagnostics(
        performance_score, profit_margin, cost_revenue_ratio,
        trend, business_internal_name, weekly_schedule, actual
    )

    return {
        'performance_score': round(performance_score, 1),
        'avg_daily_revenue': round(avg_actual_rev, 2),
        'avg_theoretical_revenue': round(avg_theoretical_rev, 2),
        'profit_margin': round(profit_margin, 1),
        'cost_revenue_ratio': round(cost_revenue_ratio, 1),
        'daily_comparison': actual,
        'trend_direction': trend,
        'diagnostics': diagnostics,
        'rating': rating,
        'theoretical': theoretical,
        'n_days': len(actual) if not actual.empty else 0,
    }


def _generate_diagnostics(
    performance_score, profit_margin, cost_revenue_ratio,
    trend, business_internal_name, weekly_schedule, actual_df
) -> list:
    """Generate actionable diagnostic insights."""
    diags = []

    # Performance-based diagnostics
    if performance_score >= 85:
        diags.append({
            'icon': '✅', 'severity': 'success',
            'message': f'Business is performing well! ({performance_score:.0f}% of theoretical potential)'
        })
    elif performance_score >= 65:
        diags.append({
            'icon': '👍', 'severity': 'info',
            'message': f'Good performance at {performance_score:.0f}% — room for improvement'
        })
    elif performance_score >= 40:
        diags.append({
            'icon': '⚠️', 'severity': 'warning',
            'message': f'Below average at {performance_score:.0f}% — consider adding furniture or adjusting hours'
        })
    elif performance_score > 0:
        diags.append({
            'icon': '🔴', 'severity': 'error',
            'message': f'Poor performance at {performance_score:.0f}% — major improvements needed'
        })

    # Cost diagnostics
    if cost_revenue_ratio > 70:
        diags.append({
            'icon': '💸', 'severity': 'warning',
            'message': f'High cost-to-revenue ratio ({cost_revenue_ratio:.0f}%) — review staffing and expenses'
        })
    elif cost_revenue_ratio > 50:
        diags.append({
            'icon': '💰', 'severity': 'info',
            'message': f'Moderate cost-to-revenue ratio ({cost_revenue_ratio:.0f}%)'
        })
    elif cost_revenue_ratio > 0:
        diags.append({
            'icon': '✅', 'severity': 'success',
            'message': f'Healthy cost structure ({cost_revenue_ratio:.0f}% of revenue)'
        })

    # Trend diagnostics
    if trend == 'improving':
        diags.append({
            'icon': '📈', 'severity': 'success',
            'message': 'Revenue trend is improving over time'
        })
    elif trend == 'declining':
        diags.append({
            'icon': '📉', 'severity': 'warning',
            'message': 'Revenue trend is declining — investigate the cause'
        })

    # Peak hours alignment check
    peak = _detect_peak_hours(business_internal_name)
    if peak:
        schedule_map = {ds.day_name: ds for ds in weekly_schedule}
        # Check if any open day misses peak hours
        missed_peaks = []
        for day_name, ds in schedule_map.items():
            if ds.is_open:
                if ds.start_hour > peak['start'] + 1:
                    missed_peaks.append(f"{day_name} opens at {ds.start_hour}:00 but peak starts at {peak['start']}:00")
                if ds.end_hour < peak['end'] - 1:
                    missed_peaks.append(f"{day_name} closes at {ds.end_hour}:00 but peak goes until {peak['end']}:00")
        if missed_peaks:
            diags.append({
                'icon': '🕐', 'severity': 'warning',
                'message': f"Operating hours miss some peak demand periods ({peak['start']}:00-{peak['end']}:00). {missed_peaks[0]}"
            })
        else:
            diags.append({
                'icon': '🕐', 'severity': 'success',
                'message': f"Operating hours are well-aligned with peak demand ({peak['start']}:00-{peak['end']}:00)"
            })

    # Profit margin diagnostic
    if profit_margin < 0:
        diags.append({
            'icon': '🔴', 'severity': 'error',
            'message': f'Business is operating at a loss (margin: {profit_margin:.1f}%)'
        })
    elif profit_margin < 20:
        diags.append({
            'icon': '⚠️', 'severity': 'warning',
            'message': f'Low profit margin ({profit_margin:.1f}%) — consider reducing costs'
        })

    # Data quality
    if not actual_df.empty and len(actual_df) < 7:
        diags.append({
            'icon': 'ℹ️', 'severity': 'info',
            'message': f'Only {len(actual_df)} days of data — results may not be fully representative'
        })

    return diags
