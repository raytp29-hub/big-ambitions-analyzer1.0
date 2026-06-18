"""
core/data_cleaner.py
Data cleaning module for Big Ambitions CSV files
Supports both formats:
- Format 1: Single column with escaped quotes (test.csv style)  
- Format 2: Standard 5-column CSV (Transactions.csv style)
"""

import pandas as pd
import io
from typing import Tuple, Optional


def detect_csv_format(content: str) -> str:
    """
    Detect which CSV format we're dealing with.

    Args:
        content: Decoded CSV content as string

    Returns:
        'single_column' - Format like test.csv (whole row wrapped in quotes
                           with "" escaped quotes inside; needs manual parsing)
        'standard' - Format like Transactions.csv (standard CSV)
    """
    try:
        first_line = content.split('\n')[0].strip()
        # The only format that needs manual parsing is the one where each row is
        # a single quoted field containing "" escaped quotes. Everything else
        # (comma- or semicolon-delimited) is handled by the standard pandas path.
        return 'single_column' if '""' in first_line else 'standard'
    except Exception as e:
        print(f"Format detection error: {e}")
        return 'standard'


def detect_delimiter(content: str) -> str:
    """
    Detect the field delimiter. Non-English game exports (German, Italian,
    French, ...) use ';' because ',' is the decimal separator in those locales.

    Returns ';' or ',' (defaults to ',').
    """
    try:
        # Use the first non-empty line as the sample
        sample = next((ln for ln in content.split('\n') if ln.strip()), '')
        semicolons = sample.count(';')
        commas = sample.count(',')
        return ';' if semicolons > commas else ','
    except Exception:
        return ','


def _to_number(series: pd.Series, decimal: str) -> pd.Series:
    """
    Convert a string column to numeric, honoring the locale's decimal separator.

    For decimal=',' (e.g. "1.234,56"): strip '.' thousands separators, then turn
    the decimal ',' into '.'. For decimal='.' (e.g. "1,234.56"): strip ','
    thousands separators.
    """
    s = series.astype(str).str.strip()
    if decimal == ',':
        s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    else:
        s = s.str.replace(',', '', regex=False)
    return pd.to_numeric(s, errors='coerce')


import streamlit as st

@st.cache_data(show_spinner=False)
def clean_big_ambitions_csv(file_content: bytes) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Clean Big Ambitions CSV with automatic format detection.
    
    Args:
        file_content: Raw file content as bytes
        
    Returns:
        Tuple[DataFrame or None, error_message or None]
        - If success: (DataFrame, None)
        - If error: (None, "error message")
    """
    try:
        # STEP 1: Decode bytes → string (handle BOM)
        try:
            content = file_content.decode("utf-8-sig")  # Removes BOM if present
        except:
            content = file_content.decode("utf-8")
        
        # STEP 2: Detect format and delimiter
        format_type = detect_csv_format(content)
        delimiter = detect_delimiter(content)
        # In ';'-delimited (non-English) exports the decimal separator is ','
        decimal_sep = ',' if delimiter == ';' else '.'
        print(f"Detected format: {format_type} | delimiter: '{delimiter}' | decimal: '{decimal_sep}'")

        if format_type == 'standard':
            # ============================================================
            # STANDARD CSV FORMAT (Transactions.csv)
            # ============================================================
            # header=None: real game exports have NO header row, so the first
            # transaction must be kept. If an export *does* include a header, its
            # non-numeric day/price cells become NaN and get dropped below.
            df = pd.read_csv(
                io.StringIO(content),
                names=['description', 'day', 'type', 'price', 'balance'],
                sep=delimiter,
                header=None
            )

            print(f"Parsed as standard CSV: {len(df)} rows")

        else:
            # ============================================================
            # SINGLE COLUMN FORMAT (test.csv) - Manual parsing
            # ============================================================
            lines = content.strip().split("\n")
            cleaned_rows = []
            
            for line in lines:
                # Remove wrapper if present
                line = line.strip()
                
                if line.startswith('"') and line.endswith('"'):
                    line = line[1:-1]
                
                # Replace escaped quotes
                line = line.replace('""', '"')
                
                # Manual parsing
                parts = []
                current = ""
                in_quotes = False
                
                for char in line:
                    if char == '"':
                        in_quotes = not in_quotes
                        continue
                    if char == delimiter and not in_quotes:
                        parts.append(current)
                        current = ""
                        continue
                    current += char
                
                if current:
                    parts.append(current.strip())
                
                # Add if valid
                if len(parts) == 5:
                    cleaned_rows.append(parts)
            
            # Create DataFrame
            df = pd.DataFrame(
                cleaned_rows,
                columns=["description", "day", "type", "price", "balance"]
            )
            
            print(f"Parsed as single column: {len(df)} rows")
        
        # ============================================================
        # COMMON CLEANING FOR BOTH FORMATS
        # ============================================================
        
        # Convert data types (locale-aware: handles ',' decimal separators)
        df["day"] = _to_number(df["day"], decimal_sep)
        df["price"] = _to_number(df["price"], decimal_sep)
        df["balance"] = _to_number(df["balance"], decimal_sep)
        
        # Remove invalid rows
        df = df.dropna(subset=["day", "price"])
        
        # Sort by day and balance (chronological order)
        df = df.sort_values(['day', 'balance']).reset_index(drop=True)
        
        # Validation
        if df.empty:
            return None, "No valid data after cleaning"
        
        # Final stats
        print(f"Final: {len(df)} transactions | Days: {df['day'].min():.0f}-{df['day'].max():.0f} | Types: {df['type'].nunique()}")
        
        return df, None
        
    except Exception as e:
        error_msg = f"Cleaning error: {str(e)}"
        print(f"ERROR: {error_msg}")
        return None, error_msg


# Test function
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"\n{'='*60}")
        print(f"Testing with: {filepath}")
        print(f"{'='*60}\n")
        
        with open(filepath, 'rb') as f:
            content = f.read()
        
        df, error = clean_big_ambitions_csv(content)
        
        if error:
            print(f"\nError: {error}")
        else:
            print(f"\nSuccess!")
            print(f"\nShape: {df.shape}")
            print(f"Columns: {df.columns.tolist()}")
            print(f"\nFirst 3 rows:")
            print(df.head(3).to_string())
            print(f"\nLast 3 rows:")
            print(df.tail(3).to_string())