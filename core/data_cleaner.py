"""
core/data_cleaner.py
Data cleaning module for Big Ambitions CSV files
"""

import pandas as pd
import io
from typing import Tuple, Optional


def clean_big_ambitions_csv(file_content: bytes) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Clean Big Ambitions CSV with nested quotes.
    
    Args:
        file_content: Raw file content as bytes
        
    Returns:
        Tuple[DataFrame or None, error_message or None]
        - If success: (DataFrame, None)
        - If error: (None, "error message")
    """
    
    
    
    
    try:
        # STEP 1: Decodifica bytes → string
        content = file_content.decode("utf-8")
        
        # STEP 2: Splitta in righe
        lines = content.strip().split("\n")
        
        # STEP 3: Per ogni riga, pulisci e parsa
        cleaned_rows = []
        
        for line in lines:
            # STEP 3a: Rimuovi wrapper esterno se presente
            line = line.strip()
            
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            
            # STEP 3b: Sostituisci doppi apici doppi
            line = line.replace('""', '"')
            
            # STEP 3c: Parse manuale (questo è il più complesso!)
            parts = []
            current = ""
            in_quotes = False
            
            for char in line:
                if char == '"':
                    in_quotes = not in_quotes
                    continue
                if char == ',' and not in_quotes:
                    parts.append(current)
                    current = ""
                    continue
                current += char
            if current:
                parts.append(current.strip())
            
            # STEP 3d: Aggiungi a cleaned_rows se valida
            if len(parts) == 5:
                cleaned_rows.append(parts)
        
        # STEP 4: Crea DataFrame
        df = pd.DataFrame(
            cleaned_rows,
            columns=["description", "day", "type", "price", "balance"]
        )
        
        # STEP 5: Converti tipi di dato
        df["day"] = pd.to_numeric(df["day"], errors="coerce")
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df["balance"] = pd.to_numeric(df["balance"], errors="coerce")
        
        
        # STEP 6: Valida (rimuovi righe invalide)
        df = df.dropna(subset=["day", "price"])
        
        if df.empty:
            return None, "No valid data after cleaning"
        
        return df, None
        
    except Exception as e:
        return None, f"Cleaning error: {str(e)}"