from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from core.data_cleaner import clean_big_ambitions_csv
from core.hsg_reader import load_save, Save, SaveFormatError
from core.localization import display_name
from collections import defaultdict
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
            raise ValueError(f"source must be one of {VALID_SOURCES}, got {self.source!r}")
                
        _validate_df(self.transactions, "transactions", TRANSACTIONS_SCHEMA)
        
        if self.source == "csv" and self.item_sales is not None:
            raise ValueError(f"item_sales must be None when source='csv' "
        f"(got a DataFrame with {len(self.item_sales)} rows)")
        
        if self.item_sales is not None:
            _validate_df(self.item_sales, "item_sales", ITEM_SALES_SCHEMA)
        
        
        
        
def load_data(path: Path | str) -> DataBundle:
    path = Path(path)
    ext = path.suffix.lower()
    
    if ext == ".csv":
        return _load_from_csv(path)
    if ext == ".hsg":
        return _load_from_hsg(path)
    
    
    raise ValueError(f"Unsupported file exention: {ext!r}. Expected '.csv' or '.hsg'")


def _load_from_csv(path: Path) -> DataBundle:
    file_bytes = path.read_bytes()
    df, error = clean_big_ambitions_csv(file_bytes)
    
    
    if error is not None:
        raise ValueError(f"CSV parse error: {error}")
    if df is None:
        raise ValueError(f"CSV parse returned no DataFrame for {path.name}")
    
    df = df.astype(TRANSACTIONS_SCHEMA)
    return DataBundle(transactions=df, source="csv")


def _tx_data_dict(save: Save, tx_data_ref) -> dict[str, str]:
    """
    Appiattisce transactionData (Dictionary<string,string>) in un dict Python.
    Formato di partenza: {"$items": [{"$k": "businessName", "$v": "BurgerJoint"}, ...]}
    Ritorna: {"businessName": "BurgerJoint", ...} — vuoto se il campo manca.
    """
    tx_data = save.deref(tx_data_ref)
    if not tx_data:
        return {}
    result = {}
    for entry in tx_data.get("$items", []):
        entry = save.deref(entry)
        if entry and "$k" in entry:
            result[entry["$k"]] = entry.get("$v") or ""
    return result


def _hsg_to_transactions(save: Save) -> pd.DataFrame:
    """Estrae il ledger transazioni da save.root['Transactions']."""
    rows = []
    for tx in save.items(save.root.get("Transactions")):
        if not tx:
            continue
        
        ts = save.deref(tx.get("timestamp")) or {}
        day = ts.get("Day", 0)
        
        # tutti i valori di transactionData in un colpo solo
        tx_data = _tx_data_dict(save, tx.get("transactionData"))
        description = tx_data.get("businessName", "")
        
        # template dal locale, poi sostituzione con format_map
        tx_type_template = display_name(tx.get("transactionType") or "")
        # defaultdict(str) mette "" per chiavi mancanti, evita KeyError
        tx_type = tx_type_template.format_map(defaultdict(str, tx_data)) if tx_type_template else ""
        
        rows.append({
            "description": description,
            "day":         day,
            "type":        tx_type,
            "price":       tx.get("amount", 0.0),
            "balance":     tx.get("balance", 0.0),
        })
    
    df = pd.DataFrame(rows, columns=list(TRANSACTIONS_SCHEMA))
    return df.astype(TRANSACTIONS_SCHEMA)



def _hsg_to_item_sales(save: Save) -> pd.DataFrame:
    """Estrae per-shop × per-item × per-day sales da BuildingRegistrations."""
    rows = []
    for building in save.items(save.root.get("BuildingRegistrations")):
        if not building or not building.get("RentedByPlayer"):
            continue
        business_name = building.get("BusinessName") or ""
        
        # orderHistory.$items = lista di OrderHistoryEntry per-day
        for order_day in save.items(building.get("orderHistory")):
            if not order_day:
                continue
            day = order_day.get("dayNumber", 0)
            
            # itemSales.$items = lista di ItemReport per-item-di-quel-giorno
            for item in save.items(order_day.get("itemSales")):
                if not item:
                    continue
                rows.append({
                    "business_name":         business_name,
                    "day":                   day,
                    "item_key":              item.get("itemName") or "",
                    "amount_sold":           item.get("amountSold", 0),
                    "total_price":           item.get("totalPrice", 0.0),
                    "total_wholesale_price": item.get("totalWholesalePrice", 0.0),
                })
    
    df = pd.DataFrame(rows, columns=list(ITEM_SALES_SCHEMA))
    return df.astype(ITEM_SALES_SCHEMA)



def _load_from_hsg(path: Path) -> DataBundle:
    """Legge un save .hsg e produce un DataBundle."""
    try:
        save = load_save(str(path))
    except SaveFormatError as e:
        raise ValueError(f"Corrupt .hsg file: {e}") from e
    except OSError as e:
        raise ValueError(f"Cannot read save file: {e}") from e
    
    build = save.root.get("buildNumberAtLastSave")
    if build is None:
        raise ValueError("Save file has no 'buildNumberAtLastSave' field")
    if build < 3540:
        raise ValueError(
            f"Save too old: build {build} < 3540 required. "
            "Load and re-save the file in the current game version."
        )
    
    transactions = _hsg_to_transactions(save)
    item_sales = _hsg_to_item_sales(save)
    
    return DataBundle(
        transactions=transactions,
        source="hsg",
        item_sales=item_sales,
    )
    