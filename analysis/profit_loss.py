import pandas as pd
from typing import Tuple, List
from .revenue_analyzer import extract_business_from_revenue




def calculate_profit_loss(df):
    # STEP 0: Aggiorna categorizzazione
    # Delivery Contract: 'direct_cost' → 'shared_revenue_based' ⚠️
    
    # STEP 1: Costruisci employee→business mapping da Wage
    employee_map = build_employee_mapping(df)
    
    # STEP 2: Estrai revenue per business
    revenue_per_business = extract_revenue(df)
    
    # STEP 3: Estrai direct costs per business
    direct_costs = extract_direct_costs(df, employee_map)
    
    # STEP 4-5: Alloca shared costs e calcola P&L
    total_revenue_based, total_equal_split = calculate_shared_costs(df)
    
    total_revenue = revenue_per_business["revenue"].sum()
    
    # allocazione revenue-based
    revenue_per_business["shared_revenue_based"] = revenue_per_business["revenue"].apply(
        lambda rev: total_revenue_based * (rev/total_revenue)
    )
    
    # Equal split
    num_business = len(revenue_per_business)
    revenue_per_business["shared_equal_split"] = total_equal_split / num_business
    
    # STEP 6: Merge revenue e direct costs
    pl_df = pd.merge(revenue_per_business, direct_costs, on='business')
    
    # Total shared costs
    pl_df["total_shared_costs"] = pl_df["shared_revenue_based"] + pl_df["shared_equal_split"]
    
    # Total Costs
    pl_df["total_costs"] = pl_df["total_direct_costs"] + pl_df["total_shared_costs"]
    
    # Total profit
    pl_df["profit"] = pl_df["revenue"] - pl_df["total_costs"]
    
    # Margin
    pl_df["margin_pct"] = (pl_df["profit"] / pl_df["revenue"]) * 100
    
    
    
    return pl_df
    
    
    
    
    
    
    
    
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
    """
    Estrae i costi diretti per ogni business.
    
    Args:
        df: DataFrame pulito
        employee_map: {'Kathleen Hinds': 'HQ Ray', ...}
    
    Returns:
        DataFrame con:
        - business: Nome del business
        - wages: Totale stipendi
        - marketing: Totale marketing
        - health_insurance: Totale assicurazioni
        - hr_training: Totale training
        - total_direct_costs: Somma di tutto
    """
    
    
    business_costs = {}
    
    direct_cost_types = ['Wage', 'Replacement Wage', 'Marketing', 'Health Insurance', 'HR Training']
    
    direct_df = df[df["type"].isin(direct_cost_types)].copy()
    
    
    # Loop su ogni transazione
    
    for _, row in direct_df.iterrows():
        description = row["description"]
        cost_type = row["type"]
        price = abs(row["price"])
        
        
        if cost_type in ['Wage', 'Replacement Wage']:
            # Usa la stessa logica di build_employee_mapping
            if cost_type == 'Replacement Wage':
                employee_name = description.split("for")[-1].split("(")[0].strip()  # ✅
            else:
                employee_name = description.split("(")[0].strip()  # ✅
            
            business_name = employee_map[employee_name]
            
        elif cost_type == 'Marketing':
            business_name = description.split("for")[-1].strip()
            
        elif cost_type in ['Health Insurance', 'HR Training']:
            if cost_type == 'Health Insurance':
                employee_name = description.split("(")[1].split(")")[0].strip()
            else:
                employee_name = description.split("training")[0].strip()
                
            business_name = employee_map[employee_name]
        # Aggiungere feature per salvare il tipo di insurance (gold,silver,bronze)
    
        if business_name  not in business_costs:
            business_costs[business_name] = {
                'wages': 0,
                'marketing':0,
                'health_insurance':0,
                'hr_training':0
            }
            
        if cost_type in ["Wage", "Replacement Wage"]:
            business_costs[business_name]['wages'] += price
        elif cost_type == 'Marketing':
            business_costs[business_name]['marketing'] += price
        elif cost_type == 'Health Insurance':
            business_costs[business_name]["health_insurance"] += price 
        elif cost_type == 'HR Training':
            business_costs[business_name]["hr_training"] += price 
            
            
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
    """
    Calcola i totali dei costi condivisi.
    
    Returns:
        Tuple: (total_revenue_based, total_equal_split)
    """
    # Costi condivisi revenue-based
    revenue_based_types = ['Rent', 'Loan Payment', 'Tax Payment', 
                           'Bank Negative Interest Rate', 'Delivery Contract']
    
    # Costi condivisi equal-split
    equal_split_types = ['Item Purchase', 'Import Delivery', 'Interior Designer']
    
    # Filtra DataFrame
    revenue_based_df = df[df['type'].isin(revenue_based_types)]
    equal_split_df = df[df['type'].isin(equal_split_types)]
    
    # Calcola totali
    total_revenue_based = abs(revenue_based_df["price"].sum())
    total_equal_split = abs(equal_split_df["price"].sum())
    
    return total_revenue_based, total_equal_split