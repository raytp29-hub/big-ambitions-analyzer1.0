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
        'single_column' - Format like test.csv (needs manual parsing)
        'standard' - Format like Transactions.csv (standard CSV)
    """
    try:
        # Get first line
        first_line = content.split('\n')[0].strip()
        
        # Key distinction:
        # - Single column: Has "" (escaped quotes) 
        # - Standard: Has "," but NOT ""
        
        has_escaped_quotes = '""' in first_line
        has_standard_separator = '","' in first_line
        
        # If has escaped quotes → single column format
        if has_escaped_quotes:
            return 'single_column'
        
        # If has standard separator and no escaped quotes → standard CSV
        if has_standard_separator:
            return 'standard'
        
        # Default to single column for safety
        return 'single_column'
        
    except Exception as e:
        print(f"Format detection error: {e}")
        return 'single_column'


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
        
        # STEP 2: Detect format
        format_type = detect_csv_format(content)
        print(f"🔍 Detected format: {format_type}")
        
        if format_type == 'standard':
            # ============================================================
            # STANDARD CSV FORMAT (Transactions.csv)
            # ============================================================
            df = pd.read_csv(
                io.StringIO(content),
                names=['description', 'day', 'type', 'price', 'balance'],
                header=0  # Skip first row (it becomes column names)
            )
            
            print(f"✅ Parsed as standard CSV: {len(df)} rows")
            
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
                    if char == ',' and not in_quotes:
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
            
            print(f"✅ Parsed as single column: {len(df)} rows")
        
        # ============================================================
        # COMMON CLEANING FOR BOTH FORMATS
        # ============================================================
        
        # Convert data types
        df["day"] = pd.to_numeric(df["day"], errors="coerce")
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df["balance"] = pd.to_numeric(df["balance"], errors="coerce")
        
        # Remove invalid rows
        df = df.dropna(subset=["day", "price"])
        
        # Sort by day and balance (chronological order)
        df = df.sort_values(['day', 'balance']).reset_index(drop=True)
        
        # Validation
        if df.empty:
            return None, "No valid data after cleaning"
        
        # Final stats
        print(f"📊 Final: {len(df)} transactions | Days: {df['day'].min():.0f}-{df['day'].max():.0f} | Types: {df['type'].nunique()}")
        
        return df, None
        
    except Exception as e:
        error_msg = f"Cleaning error: {str(e)}"
        print(f"❌ {error_msg}")
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
            print(f"\n❌ Error: {error}")
        else:
            print(f"\n✅ Success!")
            print(f"\nShape: {df.shape}")
            print(f"Columns: {df.columns.tolist()}")
            print(f"\nFirst 3 rows:")
            print(df.head(3).to_string())
            print(f"\nLast 3 rows:")
            print(df.tail(3).to_string())