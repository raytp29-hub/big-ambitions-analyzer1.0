"""
Revenue Analyzer Module
Extracts and analyzes revenue by business
"""

import pandas as pd
from typing import Tuple, List


def extract_business_from_revenue(df: pd.DataFrame) -> Tuple[List[str], pd.Series, pd.DataFrame]:
    """
    Extract business names and calculate revenue totals.
    
    Args:
        df: Cleaned DataFrame with transactions
        
    Returns:
        Tuple containing:
        - business_names: List of unique business names
        - revenue_per_business: Series with total revenue per business
        - revenue_df: DataFrame with revenue transactions including business column
    """
    
    # STEP 1: Filtra solo le righe di tipo "Revenue"
    revenue_df = df[df["type"] == "Revenue"].copy()
    
    # STEP 2: Estrai il nome del business dalla descrizione
    def rimuovi_revenue(descrizione):
        parti = descrizione.split()
        if parti[-1] == "Revenue":
            return " ".join(parti[:-1])
        return descrizione
    
    revenue_df["business"] = revenue_df["description"].apply(rimuovi_revenue)
    
    
    
    # STEP 4: Calcola totale revenue per ogni business

    revenue_per_business = revenue_df.groupby("business")["price"].sum()
    
    # STEP 5: Estrai lista unica di nomi business
    business_names = revenue_df["business"].unique().tolist()
    
    return business_names, revenue_per_business, revenue_df