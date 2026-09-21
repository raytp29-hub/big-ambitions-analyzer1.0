import pandas as pd
import numpy as np
from typing import Tuple, List, Optional
from .revenue_analyzer import extract_business_from_revenue
from core.transaction_categories import categorize_transaction
from core.localization import display_name



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
    # NB: dtypes espliciti! Un DataFrame vuoto con colonne 'object' contamina
    # i pd.concat a valle (aggregate_by_period) rendendo object anche le
    # colonne numeriche degli altri periodi → np.polyfit fallisce.
    if len(all_businesses) == 0:
        return pd.DataFrame({
            'business': pd.Series(dtype=str),
            'revenue': pd.Series(dtype=float),
            'shared_revenue_based': pd.Series(dtype=float),
            'shared_equal_split': pd.Series(dtype=float),
            'wages': pd.Series(dtype=float),
            'marketing': pd.Series(dtype=float),
            'health_insurance': pd.Series(dtype=float),
            'hr_training': pd.Series(dtype=float),
            'total_direct_costs': pd.Series(dtype=float),
            'total_shared_costs': pd.Series(dtype=float),
            'total_costs': pd.Series(dtype=float),
            'profit': pd.Series(dtype=float),
            'margin_pct': pd.Series(dtype=float)
        })
    
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
    
    
    
    
    
def calculate_item_margin(item_sales: pd.DataFrame, business_filter: Optional[str] = None) -> pd.DataFrame:
    """
    Aggrega item_sales per (business, item_key) e ritorna un DataFrame con
    revenue/cost/margin/margin_pct/units/avg_price_per_unit.
    ...
    """
    
    if business_filter is not None:
        item_sales = item_sales[item_sales['business_name'] == business_filter]
            
    
    
    if item_sales.empty:
        return pd.DataFrame({
            'business_name': pd.Series(dtype=str),
            'item_key': pd.Series(dtype=str),
            'item_display': pd.Series(dtype=str),
            'units_sold': pd.Series(dtype=int),
            'revenue': pd.Series(dtype=float),
            'cost': pd.Series(dtype=float),
            'margin': pd.Series(dtype=float),
            'margin_pct': pd.Series(dtype=float),
            'avg_price_per_unit': pd.Series(dtype=float)            
        })
    
    
    agg = item_sales.groupby(['business_name', 'item_key'], as_index=False).agg(
        units_sold=('amount_sold', 'sum'),
        revenue=('total_price', 'sum'),
        cost=('total_wholesale_price', 'sum'),
    )
        
    agg['margin'] = agg['revenue'] - agg['cost']
    
    agg['margin_pct'] = np.where(
        agg['revenue'] > 0,
        agg['margin'] / agg['revenue'] * 100,
        np.nan
    )
    
    agg['avg_price_per_unit'] = np.where(
    agg['units_sold'] > 0,
    agg['revenue'] / agg['units_sold'],
    np.nan
    )
    
    
    agg['item_display'] = agg['item_key'].apply(lambda k: display_name(k, 'en'))
    
    agg = agg.sort_values('margin', ascending=False).reset_index(drop=True)
    
    
    return agg[[
    'business_name', 'item_key', 'item_display',
    'units_sold', 'revenue', 'cost',
    'margin', 'margin_pct', 'avg_price_per_unit',
    ]]
    
    
    
    
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

# ============================================================================
# ITEM-LEVEL MARGIN (Fase 5 di Track 1 — vedi claude/feature-item-margin-plan.md)
# ----------------------------------------------------------------------------
# Aggrega bundle.item_sales (disponibile solo da save .hsg) per (business, item)
# e calcola margine assoluto e percentuale sfruttando total_wholesale_price
# gia' presente nello schema HSG — nessun cross-join con game_data.json.
# ============================================================================


def calculate_item_margin(
    item_sales: pd.DataFrame,
    business_filter: Optional[str] = None,
) -> pd.DataFrame:
    """Aggrega item_sales per (business, item_key) e calcola margine.

    Args:
        item_sales: DataFrame conforme a core.data_loader.ITEM_SALES_SCHEMA
            (business_name, day, item_key, amount_sold, total_price,
            total_wholesale_price). Tipicamente `bundle.item_sales`.
        business_filter: se passato, restringe l'aggregazione a quel business.
            Passare None (default) per includere tutti i business.

    Returns:
        DataFrame ordinato per margin discendente, colonne:
            business_name, item_key, item_display,
            units_sold, revenue, cost, margin,
            margin_pct (NaN se revenue == 0),
            avg_price_per_unit (NaN se units_sold == 0)

        DataFrame vuoto (schema esplicito dtype-safe) se item_sales e' vuoto
        o se il filtro non matcha nessuna riga.

    Note:
        - margin_pct e avg_price_per_unit usano NaN come marker "non definito"
          quando denom == 0; la UI mostra "-" (Streamlit rende NaN cosi').
        - item_display viene risolto via core.localization.display_name che ha
          @lru_cache: nessun I/O ripetuto anche su tabelle lunghe.
        - Item promozionali (total_price=0, es. paperbag in fast food) entrano
          normalmente nell'aggregato: la loro presenza e' un fatto del gioco.
    """
    empty_schema = {
        "business_name":      pd.Series(dtype="string"),
        "item_key":           pd.Series(dtype="string"),
        "item_display":       pd.Series(dtype="string"),
        "units_sold":         pd.Series(dtype="int64"),
        "revenue":            pd.Series(dtype="float64"),
        "cost":               pd.Series(dtype="float64"),
        "margin":             pd.Series(dtype="float64"),
        "margin_pct":         pd.Series(dtype="float64"),
        "avg_price_per_unit": pd.Series(dtype="float64"),
    }

    if item_sales.empty:
        return pd.DataFrame(empty_schema)

    df = item_sales
    if business_filter is not None:
        df = df[df["business_name"] == business_filter]

    if df.empty:
        return pd.DataFrame(empty_schema)

    agg = df.groupby(["business_name", "item_key"], as_index=False).agg(
        units_sold=("amount_sold", "sum"),
        revenue=("total_price", "sum"),
        cost=("total_wholesale_price", "sum"),
    )

    # Cast dtype coerenti (groupby su int32 puo' promuovere a int64;
    # esplicitiamo per contract stabile in tabella e test).
    agg["units_sold"] = agg["units_sold"].astype("int64")
    agg["revenue"] = agg["revenue"].astype("float64")
    agg["cost"] = agg["cost"].astype("float64")

    agg["margin"] = agg["revenue"] - agg["cost"]

    # Divisione condizionale vettoriale: NaN dove il denominatore e' 0.
    agg["margin_pct"] = np.where(
        agg["revenue"] > 0,
        agg["margin"] / agg["revenue"] * 100.0,
        np.nan,
    )
    agg["avg_price_per_unit"] = np.where(
        agg["units_sold"] > 0,
        agg["revenue"] / agg["units_sold"],
        np.nan,
    )

    # Display leggibile via en.json. Se la chiave manca, display_name torna
    # la chiave stessa (default) — signal visivo di "manca dal locale file".
    agg["item_display"] = agg["item_key"].apply(lambda k: display_name(k, "en"))

    # Colonna business_name/item_key/item_display come StringDtype coerente.
    for col in ("business_name", "item_key", "item_display"):
        agg[col] = agg[col].astype("string")

    agg = agg[[
        "business_name", "item_key", "item_display",
        "units_sold", "revenue", "cost", "margin",
        "margin_pct", "avg_price_per_unit",
    ]]

    return agg.sort_values("margin", ascending=False).reset_index(drop=True)
