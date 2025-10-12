"""
Revenue Analyzer Module
Extracts and analyzes revenue by business
"""

import pandas as pd
from typing import Tuple, List





def extract_business_name_from_string(description:str) -> str:
    """
    Helper per estrarre business name da descrizione revenue.
    Rimuove la parola "Revenue" dalla fine della stringa.
    
    Args:
        description: Es. "Tech & Gift Revenue"
        
    Returns:
        Business name, es. "Tech & Gift"
        
    Examples:
        >>> extract_business_name_from_revenue_string("Tech & Gift Revenue")
        "Tech & Gift"
        >>> extract_business_name_from_revenue_string("G&J Revenue")
        "G&J"
    """

    parti = description.split()
    if parti[-1] == "Revenue":
        return " ".join(parti[:-1])
    return description




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
    
    
    revenue_df["business"] = revenue_df["description"].apply(extract_business_name_from_string)
    
    
    
    # STEP 4: Calcola totale revenue per ogni business

    revenue_per_business = revenue_df.groupby("business")["price"].sum()
    
    # STEP 5: Estrai lista unica di nomi business
    business_names = revenue_df["business"].unique().tolist()
    
    return business_names, revenue_per_business, revenue_df