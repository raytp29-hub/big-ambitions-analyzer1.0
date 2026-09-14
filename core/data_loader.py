from dataclasses import dataclass, field
from typing import Optional
import pandas as pd





TRANSACTIONS_SCHEMA: dict[str, str] = {
    "description": "string",
    "day":         "int32",
    "type":        "string",
    "price":       "float64",
    "balance":     "float64",
    }

ITEM_SALES_SCHEMA: dict[str, str] = {
        "business_name":         "string",
        "day":                   "int32",
        "item_key":              "string",     # ba:itemname_*
        "amount_sold":           "int32",
        "total_price":           "float64",
        "total_wholesale_price": "float64",    # bonus scoperta ieri: sblocca margine
    }

VALID_SOURCES = {"hsg", "csv"}




def _validate_df(df, name, schema):
    got = set(df.columns)
    want = set(schema)
    if got != want:
        extra = got - want    
        missing = want - got
        raise ValueError(f"{name}: missing {missing}, extra {extra}")
    
    for col, want_dtype in schema.items():
        got_dtype = str(df[col].dtype)
        if got_dtype != want_dtype:
            raise ValueError(f"{name}.{col}: expected dtype {want_dtype!r}, got {got_dtype!r}")


@dataclass(frozen=True)
class DataBundle:
    transactions: pd.DataFrame
    source: str
    item_sales: Optional[pd.DataFrame] = field(default=None)
    hour_reports: Optional[pd.DataFrame] = field(default=None)
    stock: Optional[pd.DataFrame] = field(default=None)
    
    

    
    def __post_init__(self) -> None:  
        if self.source not in VALID_SOURCES:
            raise ValueError("source must be one of {VALID_SOURCES}, got {self.source!r}")
                
        _validate_df(self.transactions, "transactions", TRANSACTIONS_SCHEMA)
        
        if self.source == "csv" and self.item_sales is not None:
            raise ValueError(f"item_sales must be None when source='csv' "
        f"(got a DataFrame with {len(self.item_sales)} rows)")
        
        if self.item_sales is not None:
            _validate_df(self.item_sales, "item_sales", ITEM_SALES_SCHEMA)
        
        