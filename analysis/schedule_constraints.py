"""
Schedule Constraints and Configuration
Loads furniture data from CSV and defines employee demand options
"""
import pandas as pd
from pathlib import Path
from typing import Dict, List

# ============================================================================
# LOAD FURNITURE DATA FROM CSV
# ============================================================================

def load_furniture_capacity() -> Dict[str, int]:
    """
    Load furniture customer capacity from scraped wiki data.
    Returns dict: {furniture_name: customer_capacity}
    """
    try:
        # Try different possible paths
        possible_paths = [
            Path(__file__).parent.parent / 'data' / 'business_furniture_clean.csv',
            Path('data/business_furniture_clean.csv'),
            Path('../data/business_furniture_clean.csv')
        ]
        
        df = None
        for path in possible_paths:
            if path.exists():
                df = pd.read_csv(path)
                break
        
        if df is None:
            print("Warning: Could not find business_furniture_clean.csv")
            return {}
        
        # Create dictionary: furniture_name -> customer_capacity
        # For duplicates, take the max capacity
        furniture_dict = {}
        for _, row in df.iterrows():
            appliance = str(row['appliance']).strip()
            capacity = int(row['customer_capacity'])
            
            if appliance in furniture_dict:
                furniture_dict[appliance] = max(furniture_dict[appliance], capacity)
            else:
                furniture_dict[appliance] = capacity
        
        return furniture_dict
    
    except Exception as e:
        print(f"Error loading furniture CSV: {e}")
        return {}


# Load furniture capacity on module import
FURNITURE_CAPACITY = load_furniture_capacity()


# ============================================================================
# BUILDING DATA
# ============================================================================

BUILDING_DATA = {
    'Retail': {
        'A1': 15, 'A2': 15,
        'C1': 30, 'C2': 30,
        'D2': 40,
        'M1': 75, 'M2': 75
    },
    'Office': {
        'A3': 4,
        'C1': 8, 'C2': 8,
        'D2': 10,
        'J1': 10,
        'K1': 50
    }
}


def get_building_capacity(business_type: str, building_code: str) -> int:
    """Get capacity limit for a specific building"""
    return BUILDING_DATA.get(business_type, {}).get(building_code, 0)


def get_available_buildings(business_type: str) -> List[str]:
    """Get list of available building codes for a business type"""
    return sorted(BUILDING_DATA.get(business_type, {}).keys())


# ============================================================================
# BUSINESS TYPES
# ============================================================================

BUSINESS_TYPES = ['Retail', 'Office']


# ============================================================================
# EMPLOYEE ROLES
# ============================================================================

EMPLOYEE_ROLES = {
    'Retail': [
        'Cleaning',
        'Customer Service',
        'DJ',
        'Security Guard',
        'Cashier'
    ],
    'Office': [
        'Cleaning',
        'Graphic Designer',
        'HR Manager',
        'Lawyer',
        'Logistics Manager',
        'Programmer',
        'Purchasing Agent'
    ]
}


def get_roles_for_business_type(business_type: str) -> List[str]:
    """Get available employee roles for a business type"""
    return EMPLOYEE_ROLES.get(business_type, [])


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
        'equipment': {item: item for item in EQUIPMENT_DEMANDS}  # equipment uses item name as key and display
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



def load_business_furniture_data():
    """Load the complete business furniture CSV"""
    csv_path = Path(__file__).parent / 'data' / 'business_furniture_complete.csv'
    if not csv_path.exists():
        csv_path = Path('data/business_furniture_complete.csv')
        
    return pd.read_csv(csv_path)


def get_available_categories() -> List[str]:
    """Get list of available business categories (Retail, Office)"""
    df = load_business_furniture_data()
    return sorted(df['category'].dropna().unique().tolist())


def get_business_tupes_for_category(category:str) -> List[str]:
    """Get business types for a specific category"""
    df = load_business_furniture_data()
    df_filtered = df[df['category'] == category]
    
    #Exclude Headquarters
    excluded_business = ['Headquarters']
    df_filtered = df_filtered[~df_filtered['business_type'].isin(excluded_business)]
    
    return sorted(df_filtered['business_type'].unique().tolist())


def get_furniture_for_business(business_type: str) -> pd.DataFrame:
    """Get available furniture for a specific business type"""
    df = load_business_furniture_data()
    df_filtered = df[df['business_type'] == business_type]
    # Remove duplicates (same furniture might appear multiple times)
    return df_filtered.drop_duplicates(subset=['furniture_name']).reset_index(drop=True)


def parse_price(price_str: str) -> float:
    """Parse price string like '$1,400' to float"""
    if pd.isna(price_str):
        return 0.0
    return float(str(price_str).replace('$', '').replace(',', ''))