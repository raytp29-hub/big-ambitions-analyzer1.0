"""
Centralized Transaction Category Management
"""

import re
from typing import Tuple, Optional
from analysis.revenue_analyzer import extract_business_from_revenue



SHARED_REVENUE_BASED_TYPES = [
    'Rent',
    'Loan Payment',
    'Tax Payment',
    'Bank Negative Interest Rate'
]

def categorize_transaction(row) -> Tuple[str, Optional[str]]:
    """Categorizza una transazione."""
    trans_type = row['type']
    description = row['description']
    price = row['price']
    

    if price > 0:
        return "revenue", None
    elif price < 0:
        business = extract_business_from_description(description, trans_type)
        
        if business:
            return "direct_cost", business
        else:
            if trans_type in SHARED_REVENUE_BASED_TYPES:
                return "shared_revenue_based", None
            else:
                return "personal", None
    
    return "unknown", None
    
            
from analysis.revenue_analyzer import extract_business_from_revenue

def extract_business_from_description(description: str, trans_type: str) -> Optional[str]:
    """
    Estrae business name dalla description.
    Riusa logica esistente + aggiunge nuovi pattern.
    """
    description = description.strip()
    
    # Pattern 1: Revenue (riusa funzione esistente)
    if trans_type == 'Revenue':
        business = description.replace("Revenue", "").strip()
        return business
    
    # Pattern 2: Wage (per HQ Ray, Warehouse, ecc.)
    if trans_type == 'Wage':
        business = description.split("(")[1].split("Daily")[0].strip()
        return business
        
    # Pattern 3: Replacement Wage
    if trans_type == 'Replacement Wage':
        business = description.split("(")[-1].split("Wage")[0].strip()
        return business
    
    # Pattern 4: Marketing
    if trans_type == 'Marketing':
        business = description.split("for")[-1].strip()
        return business
    
    # Pattern 5: Delivery Contract
    if trans_type == 'Delivery Contract':
        # "Business delivery from Supplier" → "Business"
        business = description.split("delivery")[0].strip()
        return business    
    return None
