"""
Test con dati reali dal CSV di Big Ambitions
"""

from core.data_cleaner import clean_big_ambitions_csv

def test_with_real_csv():
    """Test con file CSV reale"""
    
    # Simula alcune righe del CSV reale
    sample_data = b'''"Tax Payment,""180"",""Tax Payment"",""-284156.2"",""2049546"""\r
"Taxi Ride,""180"",""Taxi Ride"",""-32.77972"",""2333702"""\r
"Silver Health Insurance (Joseph Halliday) - 10 Employees,""179"",""Health Insurance"",""-128.3533"",""2333735"""\r
"Kathleen Hinds (HQ Ray Daily Wage),""179"",""Wage"",""-325.8668"",""2134567"""'''
    
    print("🧪 Testing with REAL CSV format...\n")
    
    df, error = clean_big_ambitions_csv(sample_data)
    
    if error:
        print(f"❌ ERROR: {error}")
        return
    
    print("✅ SUCCESS! DataFrame created:")
    print(f"   Rows: {len(df)}")
    print(f"   Columns: {list(df.columns)}")
    print("\n📊 Data preview:")
    print(df)
    print("\n📈 Data types:")
    print(df.dtypes)
    print("\n✨ Sample values:")
    print(f"   First description: {df['description'].iloc[0]}")
    print(f"   First day (numeric): {df['day'].iloc[0]}")
    print(f"   First price (numeric): {df['price'].iloc[0]}")

if __name__ == "__main__":
    test_with_real_csv()