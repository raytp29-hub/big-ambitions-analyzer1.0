"""
Schedule Constraints and Configuration
Loads game data from JSON via core.game_data module.
All business types, buildings, furniture, and roles are derived from the game data.
"""
import sys
from pathlib import Path
import pandas as pd
from typing import Dict, List

# Ensure project root is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.game_data import (
    get_business_categories,
    get_businesses_for_category,
    get_building_sizes_for_category,
    get_building_capacity as _get_building_capacity,
    get_furniture_for_business as _get_furniture_for_business,
    get_employee_roles_for_business,
    format_item_name,
)


# ============================================================================
# BUSINESS CATEGORIES & TYPES (from game data)
# ============================================================================

def get_available_categories() -> List[str]:
    """Get list of business categories: Cinema, Office, Retail, Theater, Warehouse"""
    return get_business_categories()


def get_business_tupes_for_category(category: str) -> List[str]:
    """
    Get business types for a category. Returns display names.
    e.g., 'Retail' -> ['Bookstore', 'Clothing Store', 'Coffee Shop', ...]
    """
    raw_names = get_businesses_for_category(category)
    # Exclude Headquarters from the UI list
    excluded = ['Headquarter']
    return [format_item_name(name) for name in raw_names if name not in excluded]


# ============================================================================
# BUILDING DATA (from game data)
# ============================================================================

def get_available_buildings(business_category: str) -> List[str]:
    """
    Get list of available building codes for a category.
    Returns codes like 'A1', 'A2', 'C1', 'S1', 'R3', etc.
    """
    sizes = get_building_sizes_for_category(business_category)
    codes = []
    for size in sizes:
        for version in size['versions']:
            codes.append(f"{size['letter']}{version['number']}")
    return sorted(codes)


def get_building_capacity(business_category: str, building_code: str) -> int:
    """
    Get capacity limit for a specific building code.
    e.g., get_building_capacity('Retail', 'A1') -> 15
          get_building_capacity('Cinema', 'S2') -> 125
    """
    # Parse code: letter(s) + version number (last char)
    letter = building_code[:-1]
    version = int(building_code[-1])
    return _get_building_capacity(business_category, letter, version)


# ============================================================================
# FURNITURE (from game data)
# ============================================================================

def get_furniture_for_business(business_type: str) -> pd.DataFrame:
    """
    Get available furniture for a business type.
    Accepts display name ('Coffee Shop') or internal name ('CoffeeShop').
    Returns DataFrame compatible with existing UI code.
    """
    # Convert display name to internal name (remove spaces)
    internal_name = business_type.replace(' ', '')
    furniture_list = _get_furniture_for_business(internal_name)

    if not furniture_list:
        return pd.DataFrame(columns=[
            'furniture_name', 'customer_capacity', 'price', 'is_workstation'
        ])

    rows = []
    for f in furniture_list:
        rows.append({
            'furniture_name': f['display_name'],
            'customer_capacity': f['added_customers_per_hour'],
            'price': f'${f["price"]:,.0f}',
            'is_workstation': f['is_workstation'],
            'item_name_internal': f['item_name'],
        })

    return pd.DataFrame(rows)


def parse_price(price_str: str) -> float:
    """Parse price string like '$1,400' to float"""
    if pd.isna(price_str):
        return 0.0
    return float(str(price_str).replace('$', '').replace(',', ''))


# ============================================================================
# EMPLOYEE ROLES (from game data)
# ============================================================================

def get_roles_for_business_type(business_type: str) -> List[str]:
    """
    Get available employee roles for a business type.
    Accepts display name ('Coffee Shop') or internal name ('CoffeeShop').
    """
    internal_name = business_type.replace(' ', '')
    return get_employee_roles_for_business(internal_name)


# ============================================================================
# WORKSTATION CAPACITY
# ============================================================================

def calculate_workstation_capacity(selected_furniture: List[Dict], business_category: str) -> int:
    """
    Calculate max simultaneous employees based on workstations.
    Uses is_workstation flag from game data instead of hardcoded name checks.
    """
    workstation_count = 0
    for furn in selected_furniture:
        if furn.get('is_workstation', False):
            workstation_count += furn.get('quantity', 1)
    return workstation_count if workstation_count > 0 else 1


# ============================================================================
# INSURANCE LEVELS
# ============================================================================

INSURANCE_LEVELS = ['bronze', 'silver', 'gold']


# ============================================================================
# DEMAND PRIORITIES
# ============================================================================

DEMAND_PRIORITIES = ['critical', 'important', 'nice_to_have']


# ============================================================================
# SCHEDULE DEMANDS
# ============================================================================

SCHEDULE_DEMANDS = {
    'part_time': 'Part-time (10-30 hours/week)',
    'full_time': 'Full-time (30-50 hours/week)',
    'four_days': 'Four days week',
    'five_days': 'Five days week',
    'no_morning': 'No morning shifts (6:00-10:00)',
    'no_afternoon': 'No afternoon shifts (14:00-16:00)',
    'no_evening': 'No evening shifts (18:00-22:00)',
    'no_night': 'No night shifts (22:00-4:00)',
    'free_weekend': 'Free weekend (no Sat/Sun)',
    'no_cleaning': 'No cleaning shifts'
}


# ============================================================================
# BENEFITS DEMANDS
# ============================================================================

BENEFITS_DEMANDS = {
    'bronze_insurance': 'Bronze Health Insurance or higher',
    'silver_insurance': 'Silver Health Insurance or higher',
    'gold_insurance': 'Gold Health Insurance'
}


# ============================================================================
# ENVIRONMENT DEMANDS
# ============================================================================

ENVIRONMENT_DEMANDS = {
    'peaceful_environment': 'Peaceful work environment (owner happiness ≥ 50%)',
    'clean_environment': 'Clean work environment (cleanliness ≥ 80%)'
}


# ============================================================================
# EQUIPMENT DEMANDS
# ============================================================================

EQUIPMENT_DEMANDS = [
    'Cheap Coffee Machine',
    'Classic Phone',
    'Computer Monitor',
    'Executive Office Desk',
    'Graphic Tablet',
    'Graphic Tablet (with Screen)',
    'Meeting Table (Large)',
    'Modular Sofa 1',
    'Mouse Pad',
    'Multipurpose Chair',
    'Office Chair',
    'Office Phone',
    'Preben Sofa',
    'Standard Fridge',
    'Standard Office Desk',
    'Stump Mesh Office Chair',
    'Water Cooler'
]


# ============================================================================
# ALL DEMANDS (Combined)
# ============================================================================

def get_all_demands_by_category() -> Dict[str, Dict[str, str]]:
    """Get all available demands organized by category"""
    return {
        'schedule': SCHEDULE_DEMANDS,
        'benefits': BENEFITS_DEMANDS,
        'environment': ENVIRONMENT_DEMANDS,
        'equipment': {item: item for item in EQUIPMENT_DEMANDS}
    }


# ============================================================================
# DAYS OF WEEK
# ============================================================================

DAYS_OF_WEEK = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday'
]


# ============================================================================
# DEFAULT HOURS
# ============================================================================

DEFAULT_START_HOUR = 8
DEFAULT_END_HOUR = 22
