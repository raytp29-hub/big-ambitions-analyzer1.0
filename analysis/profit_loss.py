import pandas as pd
from typing import Tuple, List
from .revenue_analyzer import extract_business_from_revenue
from core.transaction_categories import categorize_transaction



def calculate_profit_loss(df):
    # STEP 0: Aggiorna categorizzazione
    # Delivery Contract: 'direct_cost' → 'shared_revenue_based' ⚠️
    
    # STEP 1: Costruisci employee→business mapping da Wage
    employee_map = build_employee_mapping(df)
    
    # STEP 2: Estrai revenue per business
    revenue_per_business = extract_revenue(df)
    
    # STEP 3: Estrai direct costs per business
    direct_costs = extract_direct_costs(df, employee_map)
    
    # === FIX: CREA LISTA COMPLETA DI BUSINESS ===
    # Include business con revenue E business con solo costi
    all_businesses = set()
    
    # Aggiungi business da revenue
    if not revenue_per_business.empty:
        all_businesses.update(revenue_per_business['business'].tolist())
    
    # Aggiungi business da direct costs
    if not direct_costs.empty:
        all_businesses.update(direct_costs['business'].tolist())
    
    # Se non ci sono business, ritorna DataFrame vuoto
    if len(all_businesses) == 0:
        return pd.DataFrame(columns=[
            'business',
            'revenue',
            'shared_revenue_based',
            'shared_equal_split',
            'wages',
            'marketing',
            'health_insurance',
            'hr_training',
            'total_direct_costs',
            'total_shared_costs',
            'total_costs',
            'profit',
            'margin_pct'
        ])
    
    # Crea DataFrame base con tutti i business
    base_df = pd.DataFrame({'business': sorted(list(all_businesses))})
    
    # STEP 4: Merge con revenue (left join, fillna 0)
    if not revenue_per_business.empty:
        base_df = pd.merge(
            base_df,
            revenue_per_business,
            on='business',
            how='left'
        )
    else:
        base_df['revenue'] = 0.0
    
    # Fill NaN revenue con 0
    base_df['revenue'] = base_df['revenue'].fillna(0.0)
    
    # STEP 5: Merge con direct costs (left join, fillna 0)
    if not direct_costs.empty:
        base_df = pd.merge(
            base_df,
            direct_costs,
            on='business',
            how='left'
        )
    else:
        base_df['wages'] = 0.0
        base_df['marketing'] = 0.0
        base_df['health_insurance'] = 0.0
        base_df['hr_training'] = 0.0
        base_df['total_direct_costs'] = 0.0
    
    # Fill NaN costs con 0
    base_df['wages'] = base_df['wages'].fillna(0.0)
    base_df['marketing'] = base_df['marketing'].fillna(0.0)
    base_df['health_insurance'] = base_df['health_insurance'].fillna(0.0)
    base_df['hr_training'] = base_df['hr_training'].fillna(0.0)
    base_df['total_direct_costs'] = base_df['total_direct_costs'].fillna(0.0)
    
    # STEP 6-7: Alloca shared costs
    total_revenue_based, total_equal_split = calculate_shared_costs(df)
    
    total_revenue = base_df["revenue"].sum()
    
    # Allocazione revenue-based (proporzionale al revenue)
    if total_revenue > 0:
        base_df["shared_revenue_based"] = base_df["revenue"].apply(
            lambda rev: total_revenue_based * (rev / total_revenue) if total_revenue > 0 else 0
        )
    else:
        # Se nessun revenue, split equo tra tutti i business
        num_business = len(base_df)
        base_df["shared_revenue_based"] = total_revenue_based / num_business if num_business > 0 else 0.0
    
    # Equal split
    num_business = len(base_df)
    base_df["shared_equal_split"] = total_equal_split / num_business if num_business > 0 else 0.0
    
    # STEP 8: Calcola totali
    base_df["total_shared_costs"] = base_df["shared_revenue_based"] + base_df["shared_equal_split"]
    base_df["total_costs"] = base_df["total_direct_costs"] + base_df["total_shared_costs"]
    base_df["profit"] = base_df["revenue"] - base_df["total_costs"]
    
    # Margin (gestisci divisione per zero)
    base_df["margin_pct"] = base_df.apply(
        lambda row: (row["profit"] / row["revenue"] * 100) if row["revenue"] > 0 else 0.0,
        axis=1
    )
    
    return base_df
    
    
    
    
    
    
    
    
def build_employee_mapping(df: pd.DataFrame) -> dict:
    employee_map = {}
    
    wage_df = df[df['type'].isin(['Wage', 'Replacement Wage'])].copy()
    
    for _, row in wage_df.iterrows():
        description = row['description']
        wage_type = row['type']
        

        
        if wage_type == 'Replacement Wage':
            employee_name = description.split("for")[-1].split("(")[0].strip()
            business_name = description.split("(")[-1].split("Wage")[0].strip()
        else:  # Wage normale
            employee_name = description.split("(")[0].strip()
            business_name = description.split("(")[1].split("Daily")[0].strip()
        
        if employee_name and business_name:
            employee_map[employee_name] = business_name
    
    return employee_map




def extract_direct_costs(df: pd.DataFrame, employee_map: dict) -> pd.DataFrame:
    business_costs = {}
    
    
    
    # Loop su TUTTO il DataFrame (non più filtrato!)
    for _, row in df.iterrows():
        category, business = categorize_transaction(row)
        description = row["description"]
        
        
        if category != "direct_cost":
            continue  # Salta se non è direct cost
        
        cost_type = row["type"]
        price = abs(row["price"])
        
        if business is None:
            if cost_type in ["Health Insurance", "HR Training"]:
                if cost_type == "Health Insurance":
                    # "Silver Health Insurance (James Rodriguez) - 20 Employees,"
                    employee_name = description.split("(")[1].split(")")[0].strip()
                else:
                    employee_name = description.split("training")[0].strip()
                    
                business = employee_map.get(employee_name)
        
        if business is None:
            continue
    
        if business  not in business_costs:
            business_costs[business] = {
                'wages': 0,
                'marketing':0,
                'health_insurance':0,
                'hr_training':0
            }
            
        if cost_type in ["Wage", "Replacement Wage"]:
            business_costs[business]['wages'] += price
        elif cost_type == 'Marketing':
            business_costs[business]['marketing'] += price
        elif cost_type == 'Health Insurance':
            business_costs[business]["health_insurance"] += price 
        elif cost_type == 'HR Training':
            business_costs[business]["hr_training"] += price 
            
    if not business_costs:
        return pd.DataFrame(columns=[
            "business",
            "wages",
            "marketing",
            "health_insurance",
            "hr_training",
            "total_direct_costs"
        ])
    
    costs_df = pd.DataFrame.from_dict(business_costs, orient="index")
    costs_df.reset_index(inplace=True)
    costs_df.rename(columns={"index":"business"}, inplace=True)
    
    costs_df["total_direct_costs"] = (
        costs_df["wages"] +
        costs_df["marketing"] +
        costs_df["health_insurance"] + 
        costs_df["hr_training"]
    )

    return costs_df
        



def extract_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estrae revenue totale per ogni business.
    
    Returns:
        DataFrame con colonne: business, revenue
    """
    _, revenue_per_business, _ = extract_business_from_revenue(df)
    
    # Converti Series in DataFrame
    revenue_df = revenue_per_business.reset_index()
    revenue_df.columns = ['business', 'revenue']
    
    return revenue_df





def calculate_shared_costs(df: pd.DataFrame) -> Tuple[float, float]:
    
    total_revenue_based = 0
    total_equal_split = 0
    
    for _, row in df.iterrows():
        category, _ = categorize_transaction(row)
        price = abs(row["price"])
        
        if category == "shared_revenue_based":
            total_revenue_based += price
        elif category == "shared_equal_split":
            total_equal_split += price
    
    return total_revenue_based, total_equal_split