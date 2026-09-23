"""
Revenue Analyzer Module
Extracts and analyzes revenue by business
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd





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

# ============================================================================
# REVENUE GIORNALIERA PER BUSINESS (card e grafico della Home)
# ============================================================================

DELTA_WINDOW = 7   # confronto: ultimi 7 giorni vs i 7 precedenti


def daily_revenue_by_business(
    transactions: pd.DataFrame,
    item_sales: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, str]:
    """Revenue per business e giorno: colonne business, day, revenue.
    Ogni business ha TUTTI i giorni del periodo (0 se quel giorno non ha venduto),
    così medie e sparkline non saltano i giorni vuoti.

    Fonte: item_sales del save HSG se c'è (storico ordini: ~16 giorni completi,
    non tagliato), altrimenti le righe Revenue del ledger (CSV, o HSG senza vendite).
    Restituisce anche la fonte usata: "item_sales" | "ledger"."""
    if item_sales is not None and not item_sales.empty:
        raw = item_sales.rename(columns={"business_name": "business", "total_price": "revenue"})
        source = "item_sales"
    else:
        _, _, rev = extract_business_from_revenue(transactions)
        raw = rev.rename(columns={"price": "revenue"})
        source = "ledger"

    raw = raw[["business", "day", "revenue"]].dropna(subset=["business"])
    raw = raw[raw["business"] != ""]
    if raw.empty:
        return pd.DataFrame({"business": pd.Series(dtype=str), "day": pd.Series(dtype=int),
                             "revenue": pd.Series(dtype=float)}), source

    days = range(int(raw["day"].min()), int(raw["day"].max()) + 1)
    grid = (raw.groupby(["business", "day"])["revenue"].sum()
            .unstack(fill_value=0.0)
            .reindex(columns=days, fill_value=0.0))
    daily = grid.stack().rename("revenue").reset_index()
    daily["revenue"] = daily["revenue"].astype(float)
    return daily, source


@dataclass(frozen=True)
class BusinessRevenue:
    business: str
    total: float                  # somma sul periodo
    share: float                  # quota sul totale di tutti i business (0-1)
    delta_pct: Optional[float]    # ultimi 7 giorni vs 7 precedenti; None se non calcolabile
    daily: list                   # revenue giorno per giorno, in ordine (per la sparkline)


def summarize_revenue(daily: pd.DataFrame, window: int = DELTA_WINDOW) -> list[BusinessRevenue]:
    """Una riga per business, ordinate per totale decrescente.
    delta_pct è None se i giorni sono meno di 2 × window o se i 7 giorni
    precedenti sono a zero (una percentuale su zero non ha senso)."""
    if daily.empty:
        return []
    grand_total = float(daily["revenue"].sum())
    result = []
    for business, group in daily.groupby("business"):
        values = group.sort_values("day")["revenue"].tolist()
        total = float(sum(values))
        delta = None
        if len(values) >= 2 * window:
            last, prev = sum(values[-window:]), sum(values[-2 * window:-window])
            if prev > 0:
                delta = last / prev - 1
        result.append(BusinessRevenue(
            business=str(business),
            total=total,
            share=total / grand_total if grand_total > 0 else 0.0,
            delta_pct=delta,
            daily=values,
        ))
    return sorted(result, key=lambda r: r.total, reverse=True)
