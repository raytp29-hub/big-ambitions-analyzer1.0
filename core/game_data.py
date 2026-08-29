"""
Game Data Module - Single Source of Truth
Loads all game data from big_ambitions_game_data.json extracted via extract_master.py.
Run extract_master.py after each game update to refresh the data.
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional


# ============================================================================
# CONSTANTS (from game's enum definitions - stable across updates)
# ============================================================================

# As of the June 2026 game update, IDs are string identifiers prefixed "ba:"
# (e.g. "ba:skill_cleaning", "ba:buildingtype_retail") instead of integer enums.

# Display names for employee skills, keyed by their "ba:skill_*" identifier.
SKILL_DISPLAY: Dict[str, str] = {
    "ba:skill_customerservice": "Customer Service",
    "ba:skill_cleaning": "Cleaning",
    "ba:skill_lawyer": "Lawyer",
    "ba:skill_purchasingagent": "Purchasing Agent",
    "ba:skill_logisticsmanager": "Logistics Manager",
    "ba:skill_deliverydriver": "Delivery Driver",
    "ba:skill_programmer": "Programmer",
    "ba:skill_hrmanager": "HR Manager",
    "ba:skill_graphicdesigner": "Graphic Designer",
    "ba:skill_dj": "DJ",
    "ba:skill_hairstylist": "Hair Stylist",
    "ba:skill_securityguard": "Security Guard",
    "ba:skill_headhunter": "Headhunter",
    "ba:skill_factoryworker": "Factory Worker",
    "ba:skill_gymtrainer": "Gym Trainer",
    "ba:skill_actor": "Actor",
    "ba:skill_stagecrew": "Stage Crew",
    "ba:skill_projectionist": "Projectionist",
    "ba:skill_eventplanner": "Event Planner",
    "ba:skill_travelagent": "Travel Agent",
}

CLEANING_SKILL = "ba:skill_cleaning"


def _format_ba_id(ba_id: str) -> str:
    """Fallback display name for an unknown 'ba:namespace_value' identifier."""
    if isinstance(ba_id, str) and "_" in ba_id:
        return ba_id.split("_", 1)[1].replace("_", " ").title()
    return str(ba_id)


def skill_display(skill_id) -> str:
    """Human-readable name for a 'ba:skill_*' identifier."""
    return SKILL_DISPLAY.get(skill_id, _format_ba_id(skill_id))


# Building types relevant for player businesses: "ba:buildingtype_*" -> display name
PLAYER_BUILDING_TYPES: Dict[str, str] = {
    "ba:buildingtype_retail": "Retail",
    "ba:buildingtype_office": "Office",
    "ba:buildingtype_warehouse": "Warehouse",
    "ba:buildingtype_cinema": "Cinema",
    "ba:buildingtype_theater": "Theater",
}

# Reverse lookup: display name -> "ba:buildingtype_*" id
BUILDING_TYPE_IDS: Dict[str, str] = {v: k for k, v in PLAYER_BUILDING_TYPES.items()}

# Tag that marks a business type as creatable by the player
PLAYER_CREATION_TAG = "ba:businesstag_allowplayercreation"

# Gym equipment bitmask (items with type & this != 0 are workout machines)
GYM_EQUIPMENT_BITMASK = 1048576


# ============================================================================
# MODULE-LEVEL DATA (loaded once at import)
# ============================================================================

_game_data: Optional[dict] = None
_items_by_id: Dict[int, dict] = {}
_items_by_name: Dict[str, dict] = {}
_product_to_furniture: Dict[int, List[dict]] = {}  # reverse showcase lookup
_building_sizes_by_id: Dict[int, dict] = {}


# ============================================================================
# JSON LOADING AND INDEXING
# ============================================================================

def _find_json_path() -> Path:
    """Find big_ambitions_game_data.json by checking multiple locations."""
    candidates = [
        Path(__file__).parent.parent.parent / 'big_ambitions_game_data.json',
        Path(__file__).parent.parent / 'big_ambitions_game_data.json',
        Path('big_ambitions_game_data.json'),
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "big_ambitions_game_data.json not found. "
        "Run extract_master.py to generate it."
    )


def _load_and_index():
    """Load JSON and build all lookup indexes. Called once at import."""
    global _game_data, _items_by_id, _items_by_name
    global _product_to_furniture, _building_sizes_by_id

    json_path = _find_json_path()
    with open(json_path, 'r', encoding='utf-8') as f:
        _game_data = json.load(f)

    # Normalize: the old boolean field `allowPlayerCreation` is now encoded as a
    # tag. Recreate it so downstream filters (`allowPlayerCreation == 1`) keep working.
    for bt in _game_data['business_types']:
        bt['allowPlayerCreation'] = 1 if PLAYER_CREATION_TAG in bt.get('tags', []) else 0

    # Index items by ID and by name
    for item in _game_data['items']:
        _items_by_id[item['itemName']] = item
        _items_by_name[item['m_Name']] = item

    # Build reverse showcase lookup: product_id -> [furniture_items that can showcase it]
    for item in _game_data['items']:
        for showcased_id in item.get('itemsThatCanShowcase', []):
            if showcased_id not in _product_to_furniture:
                _product_to_furniture[showcased_id] = []
            _product_to_furniture[showcased_id].append(item)

    # Index building sizes by ID
    for bs in _game_data['building_sizes']:
        _building_sizes_by_id[bs['buildingSize']] = bs


# Load on import
_load_and_index()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_business_type(business_name: str) -> Optional[dict]:
    """Find business type dict by m_Name (e.g., 'CoffeeShop')."""
    for bt in _game_data['business_types']:
        if bt['m_Name'] == business_name:
            return bt
    return None


def format_item_name(camel_name: str) -> str:
    """
    Convert CamelCase to display name.
    'CoffeeShop' -> 'Coffee Shop'
    'FastFoodRestaurant' -> 'Fast Food Restaurant'
    'DJBooth' -> 'DJ Booth'
    'HRManager' -> 'HR Manager'
    """
    # Insert space before uppercase that follows lowercase
    result = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', camel_name)
    # Insert space before uppercase that is followed by lowercase (handles 'DJBooth' -> 'DJ Booth')
    result = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', result)
    return result


def _display_to_internal(display_name: str) -> str:
    """
    Convert display name back to CamelCase internal name.
    'Coffee Shop' -> 'CoffeeShop'
    'Fast Food Restaurant' -> 'FastFoodRestaurant'
    """
    return display_name.replace(' ', '')


def display_to_internal(display_name: str) -> str:
    """Public wrapper: convert display name to internal CamelCase name."""
    return _display_to_internal(display_name)


def _make_furniture_dict(item: dict) -> dict:
    """Convert a raw item dict into the furniture API format."""
    showcase_products = []
    for sid in item.get('itemsThatCanShowcase', []):
        prod = _items_by_id.get(sid)
        if prod:
            showcase_products.append(format_item_name(prod['m_Name']))

    return {
        'item_name': item['m_Name'],
        'display_name': format_item_name(item['m_Name']),
        'added_customers_per_hour': item.get('addedCustomersPerHour', 0),
        'price': item.get('defaultMarketPrice', 0.0),
        'wholesale_price': item.get('wholesalePrice', 0.0),
        'is_workstation': item.get('assignable', 0) == 1,
        'suitable_skills': [
            skill_display(s)
            for s in item.get('suitableSkills', [])
        ],
        'can_showcase': showcase_products,
        'quality': item.get('quality', 0),
        'grid_size': item.get('gridSize', 0.0),
        'is_furniture': item.get('isFurniture', 0) == 1,
    }


# ============================================================================
# PUBLIC API - BUSINESS CATEGORIES & TYPES
# ============================================================================

def get_business_categories() -> List[str]:
    """
    Return list of player-relevant business categories.
    Based on game's building types: ['Cinema', 'Office', 'Retail', 'Theater', 'Warehouse']
    """
    categories = set()
    for bt in _game_data['business_types']:
        if bt.get('allowPlayerCreation') == 1:
            btype_id = bt['suitableBuildingType']
            if btype_id in PLAYER_BUILDING_TYPES:
                categories.add(PLAYER_BUILDING_TYPES[btype_id])
    return sorted(categories)


def get_businesses_for_category(category: str) -> List[str]:
    """
    Return internal business names for a category.
    e.g., get_businesses_for_category('Retail') -> ['Bookstore', 'ClothingStore', 'CoffeeShop', ...]
    """
    btype_id = BUILDING_TYPE_IDS.get(category)
    if btype_id is None:
        return []
    result = []
    for bt in _game_data['business_types']:
        if (bt.get('allowPlayerCreation') == 1 and
                bt['suitableBuildingType'] == btype_id):
            result.append(bt['m_Name'])
    return sorted(result)


# ============================================================================
# PUBLIC API - BUILDING SIZES & CAPACITY
# ============================================================================

def get_building_sizes_for_category(category: str) -> List[dict]:
    """
    Return building sizes available for a category.

    Returns list of dicts:
    [
        {
            'letter': 'A',
            'size_id': 0,
            'sqm': 75,
            'versions': [
                {'number': 1, 'capacity': 15},
                {'number': 2, 'capacity': 15},
            ]
        },
        ...
    ]
    """
    btype_id = BUILDING_TYPE_IDS.get(category)
    if btype_id is None:
        return []

    results = []
    for bs in _game_data['building_sizes']:
        versions = bs.get('buildingVersions', [])

        # Find versions that support this building type
        matching_versions = []
        for v in versions:
            if btype_id in v.get('supportedBuildingTypes', []):
                # Find capacity for this version
                capacity = _find_capacity(bs, btype_id, v['number'])
                matching_versions.append({
                    'number': v['number'],
                    'capacity': capacity,
                })

        if matching_versions:
            letter = bs['m_Name'].replace('BuildingSize', '')
            results.append({
                'letter': letter,
                'size_id': bs['buildingSize'],
                'sqm': bs['squareMeters'],
                'versions': sorted(matching_versions, key=lambda x: x['number']),
            })

    return sorted(results, key=lambda x: x['sqm'])


def _find_capacity(building_size: dict, building_type_id: int, version_number: int) -> int:
    """
    Find customer capacity for a specific building size, type, and version.
    buildingVersion=0 in the data means 'applies to all versions'.
    """
    caps = building_size.get('customerCapacities', [])

    # First try exact version match
    for cap in caps:
        if cap['buildingType'] == building_type_id and cap['buildingVersion'] == version_number:
            return cap['amount']

    # Fallback to version 0 (applies to all)
    for cap in caps:
        if cap['buildingType'] == building_type_id and cap['buildingVersion'] == 0:
            return cap['amount']

    return 0


def get_building_capacity(category: str, size_letter: str, version: int = 1) -> int:
    """
    Get customer capacity for a specific building.
    e.g., get_building_capacity('Retail', 'A', 1) -> 15
          get_building_capacity('Cinema', 'S', 1) -> 150
    """
    btype_id = BUILDING_TYPE_IDS.get(category)
    if btype_id is None:
        return 0

    for bs in _game_data['building_sizes']:
        if bs['m_Name'] == f'BuildingSize{size_letter}':
            return _find_capacity(bs, btype_id, version)

    return 0


# ============================================================================
# PUBLIC API - FURNITURE
# ============================================================================

def get_furniture_for_business(business_name: str) -> List[dict]:
    """
    Derive all relevant furniture for a business from game data.

    Uses three mechanisms:
    1. Product -> Showcase reverse lookup (most retail businesses)
    2. Assignable workstations matching business skills
    3. Bitmask type matching (for Gym equipment)

    Always includes CleaningStation.

    Args:
        business_name: Internal name like 'CoffeeShop', 'Cinema', 'Theater'

    Returns:
        List of furniture dicts with display_name, price, capacity, etc.
    """
    bt = _get_business_type(business_name)
    if bt is None:
        return []

    seen = set()
    furniture = []
    biz_skills = set(bt.get('employeePrimarySkills', []))

    # Mechanism 1: Product showcase chain
    # For each product the business sells, find furniture that can showcase it
    for prod in bt.get('businessProducts', []):
        pid = prod['itemName']
        for furn_item in _product_to_furniture.get(pid, []):
            if furn_item['m_Name'] not in seen and furn_item.get('isFurniture', 0) == 1:
                seen.add(furn_item['m_Name'])
                furniture.append(_make_furniture_dict(furn_item))

    # Mechanism 2: Assignable workstations matching business skills
    for item in _game_data['items']:
        if (item.get('assignable') == 1 and
                item['m_Name'] not in seen):
            item_skills = set(item.get('suitableSkills', []))
            if item_skills & biz_skills:  # intersection = matching skills
                seen.add(item['m_Name'])
                furniture.append(_make_furniture_dict(item))

    # Mechanism 3: Bitmask type matching (for Gym workout equipment)
    if business_name == 'Gym':
        for item in _game_data['items']:
            if (item.get('type', 0) & GYM_EQUIPMENT_BITMASK and
                    item.get('isFurniture', 0) == 1 and
                    item.get('addedCustomersPerHour', 0) > 0 and
                    item['m_Name'] not in seen):
                seen.add(item['m_Name'])
                furniture.append(_make_furniture_dict(item))

    # Mechanism 4: Secondary showcase furniture via tag system.
    # Furniture items have tags that indicate which businesses they can be placed in.
    # The tag value matches the business's businessTypeName.
    # For businesses without tag coverage (newer ones), fall back to same building type.
    # Business tag on furniture uses the "ba:itemtag_*" namespace, while the
    # business's own id is "ba:businesstype_*" — convert to match item tags.
    _bt_name = bt.get('businessTypeName') or ''
    my_tag = ('ba:itemtag_' + _bt_name.split('_', 1)[1]) if '_' in _bt_name else _bt_name
    primary_product_ids = set(p['itemName'] for p in bt.get('businessProducts', []))

    # Check if this business has any tag coverage on furniture.
    # NOTE (bugfix 2026-08-29): consider ANY tagged furniture, not only showcase
    # furniture. Gym has tagged equipment (ba:itemtag_gym) but no tagged showcase
    # furniture, so it previously fell into the building-type fallback and picked
    # up every retail showcase (grills, salad bars, bookshelves, ...).
    has_tag_coverage = any(
        my_tag in item.get('tags', [])
        for item in _game_data['items']
        if item.get('isFurniture', 0) == 1
    )

    for item in _game_data['items']:
        if (item.get('isFurniture', 0) == 1 and
                item.get('addedCustomersPerHour', 0) > 0 and
                item.get('itemsThatCanShowcase') and
                item['m_Name'] not in seen):

            # Filter: must have this business's tag (or fall back for no-tag businesses)
            if has_tag_coverage:
                if my_tag not in item.get('tags', []):
                    continue
            else:
                # Fallback (bugfix 2026-08-29): only furniture that showcases at
                # least one product THIS business sells. The old sibling-based
                # fallback (all products of the same building type) flooded the
                # list with unrelated retail furniture.
                showcase_ids = set(item['itemsThatCanShowcase'])
                if not (showcase_ids & primary_product_ids):
                    continue

            # Only add as secondary if it showcases non-primary products
            showcase_ids = set(item['itemsThatCanShowcase'])
            if showcase_ids.issubset(primary_product_ids):
                continue  # already covered by primary mechanisms

            seen.add(item['m_Name'])
            fdict = _make_furniture_dict(item)
            secondary_products = []
            for pid in item['itemsThatCanShowcase']:
                prod_item = _items_by_id.get(pid)
                if prod_item:
                    secondary_products.append(prod_item['m_Name'])
            fdict['secondary_products'] = secondary_products
            furniture.append(fdict)

    # Always include CleaningStation
    cleaning = _items_by_name.get('CleaningStation')
    if cleaning and cleaning['m_Name'] not in seen:
        seen.add(cleaning['m_Name'])
        furniture.append(_make_furniture_dict(cleaning))

    # Sort: workstations first, then primary furniture, then secondary, then by name
    def _sort_key(x):
        is_secondary = bool(x.get('secondary_products'))
        return (not x['is_workstation'], is_secondary, -x['added_customers_per_hour'], x['display_name'])
    furniture.sort(key=_sort_key)

    return furniture


# ============================================================================
# PUBLIC API - EMPLOYEE ROLES
# ============================================================================

def get_employee_roles_for_business(business_name: str) -> List[str]:
    """
    Return human-readable skill names for a business.
    Always includes 'Cleaning'.

    e.g., get_employee_roles_for_business('Cinema') -> ['Cleaning', 'Customer Service', 'Projectionist']
          get_employee_roles_for_business('Theater') -> ['Actor', 'Cleaning', 'Customer Service', 'Stage Crew']
    """
    bt = _get_business_type(business_name)
    if bt is None:
        return ['Cleaning']

    skills = set(bt.get('employeePrimarySkills', []))
    skills.add(CLEANING_SKILL)  # Always add Cleaning

    return sorted([skill_display(s) for s in skills])


# ============================================================================
# PUBLIC API - PRODUCTS
# ============================================================================

def get_products_for_business(business_name: str) -> List[dict]:
    """
    Return products sold by a business with pricing info.

    e.g., get_products_for_business('Cinema') -> [
        {'name': 'Cinema Ticket', 'wholesale': 0.0, 'market': 16.0, 'impact': 1.0},
        {'name': 'Popcorn', 'wholesale': 0.1, 'market': 8.5, 'impact': 0.9},
        ...
    ]
    """
    bt = _get_business_type(business_name)
    if bt is None:
        return []

    products = []
    for prod in bt.get('businessProducts', []):
        item = _items_by_id.get(prod['itemName'])
        if item:
            products.append({
                'name': format_item_name(item['m_Name']),
                'internal_name': item['m_Name'],
                'wholesale': item.get('wholesalePrice', 0.0),
                'market': item.get('defaultMarketPrice', 0.0),
                'impact': prod.get('impact', 1.0),
            })

    return products


# ============================================================================
# PUBLIC API - ITEM LOOKUP
# ============================================================================

def get_item_by_id(item_id: str) -> Optional[dict]:
    """Get an item by its id (e.g. 'ba:itemname_cupofcoffee')."""
    return _items_by_id.get(item_id)


def get_item_by_name(item_name: str) -> Optional[dict]:
    """Get an item by its internal name (e.g., 'IndustrialCoffeeMachine')."""
    return _items_by_name.get(item_name)


def get_all_business_types() -> List[dict]:
    """Get all business type definitions (raw data)."""
    return _game_data['business_types']


def get_all_items() -> List[dict]:
    """Get all item definitions (raw data)."""
    return _game_data['items']


# ============================================================================
# PUBLIC API - DEMAND ANALYSIS
# ============================================================================

_DAY_NAMES = {1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat', 7: 'Sun'}


def get_demand_multipliers(business_name: str) -> Optional[dict]:
    """
    Return hourly and daily demand multipliers for a business.

    Returns:
        {
            'hourly': [{'start': 0, 'end': 8, 'multiplier': 0.01}, ...],
            'daily': [{'day': 1, 'name': 'Mon', 'multiplier': 1.0}, ...]
        }
        or None if business not found.
    """
    bt = _get_business_type(business_name)
    if bt is None:
        return None

    hourly = []
    for h in bt.get('hourlyFactorMultipliers', []):
        hourly.append({
            'start': h['startingHour'],
            'end': h['endingHour'],
            'multiplier': round(h['multiplier'], 4),
        })

    daily = []
    for d in bt.get('dayFactorMultipliers', []):
        day_num = d['dayOfWeekOrdered']
        daily.append({
            'day': day_num,
            'name': _DAY_NAMES.get(day_num, f'Day{day_num}'),
            'multiplier': round(d['multiplier'], 4),
        })

    return {'hourly': hourly, 'daily': sorted(daily, key=lambda x: x['day'])}


def get_all_products_with_margins() -> List[dict]:
    """
    Return all sellable products with margin analysis.
    Includes which businesses sell each product and the impact value.
    """
    # Build product -> business mapping
    product_businesses: Dict[int, List[dict]] = {}
    for bt in _game_data['business_types']:
        if bt.get('allowPlayerCreation') != 1:
            continue
        btype_id = bt['suitableBuildingType']
        if btype_id not in PLAYER_BUILDING_TYPES:
            continue
        for prod in bt.get('businessProducts', []):
            pid = prod['itemName']
            if pid not in product_businesses:
                product_businesses[pid] = []
            product_businesses[pid].append({
                'business': format_item_name(bt['m_Name']),
                'impact': round(prod.get('impact', 1.0), 2),
            })

    results = []
    for pid, businesses in product_businesses.items():
        item = _items_by_id.get(pid)
        if item is None:
            continue
        wholesale = item.get('wholesalePrice', 0.0)
        market = item.get('defaultMarketPrice', 0.0)
        margin = market - wholesale
        margin_pct = (margin / wholesale * 100) if wholesale > 0 else 0.0

        results.append({
            'name': format_item_name(item['m_Name']),
            'internal_name': item['m_Name'],
            'wholesale': round(wholesale, 2),
            'market': round(market, 2),
            'margin': round(margin, 2),
            'margin_pct': round(margin_pct, 1),
            'sales_ratio': round(item.get('productSalesRatio', 0.0), 2),
            'businesses': businesses,
            'n_businesses': len(businesses),
        })

    return sorted(results, key=lambda x: -x['margin'])


def get_business_comparison_data() -> List[dict]:
    """
    Return summary data for all player-creatable businesses for comparison.
    """
    results = []
    for bt in _game_data['business_types']:
        if bt.get('allowPlayerCreation') != 1:
            continue
        btype_id = bt['suitableBuildingType']
        if btype_id not in PLAYER_BUILDING_TYPES:
            continue

        name = bt['m_Name']
        category = PLAYER_BUILDING_TYPES[btype_id]

        # Products
        products = get_products_for_business(name)
        margins = [p['market'] - p['wholesale'] for p in products]
        avg_margin = sum(margins) / len(margins) if margins else 0

        # Furniture
        furniture = get_furniture_for_business(name)

        # Skills
        roles = get_employee_roles_for_business(name)

        # Neighbourhood limits
        neigh_limits = set()
        for prod in bt.get('businessProducts', []):
            item = _items_by_id.get(prod['itemName'])
            if item and item.get('limitDemandToNeighbourhoods'):
                neigh_limits.update(item['limitDemandToNeighbourhoods'])

        # Demand multipliers summary
        daily_mults = [d['multiplier'] for d in bt.get('dayFactorMultipliers', [])]
        avg_daily = sum(daily_mults) / len(daily_mults) if daily_mults else 0

        results.append({
            'name': format_item_name(name),
            'internal_name': name,
            'category': category,
            'n_products': len(products),
            'avg_margin': round(avg_margin, 2),
            'n_furniture': len(furniture),
            'roles': roles,
            'n_roles': len(roles),
            'neighbourhood_limits': sorted(neigh_limits) if neigh_limits else None,
            'avg_daily_demand': round(avg_daily, 2),
            'has_entrance_fee': bt.get('hasEntranceFee', 0) == 1,
            'entrance_fee': bt.get('defaultEntranceFee', 0),
        })

    return sorted(results, key=lambda x: (x['category'], x['name']))
