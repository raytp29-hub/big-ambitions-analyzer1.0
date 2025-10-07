"""
Test Revenue Analyzer
"""

from analysis.revenue_analyzer import extract_business_from_revenue
import pandas as pd

def test_revenue_analyzer():
    """Test del revenue analyzer con dati simulati"""
    
    # Dati di test
    test_data = pd.DataFrame({
        'description': [
            "McDonald's Revenue",
            "Tax Payment",
            "Starbucks Revenue",
            "McDonald's Revenue",
            "Wage Payment",
            "Starbucks Revenue"
        ],
        'day': [180, 180, 180, 181, 181, 181],
        'type': ['Revenue', 'Tax', 'Revenue', 'Revenue', 'Wage', 'Revenue'],
        'price': [5000.0, -1000.0, 3000.0, 5200.0, -500.0, 3500.0],
        'balance': [100000, 99000, 102000, 107200, 106700, 110200]
    })
    
    print("🧪 Testing Revenue Analyzer...\n")
    print("📊 Input Data:")
    print(test_data)
    print()
    
    # Esegui la funzione
    business_names, revenue_per_business, revenue_df = extract_business_from_revenue(test_data)
    
    # Risultati
    print("✅ RESULTS:\n")
    
    print("1️⃣ Business Names Found:")
    print(f"   {business_names}")
    print()
    
    print("2️⃣ Revenue Per Business:")
    for business, revenue in revenue_per_business.items():
        print(f"   {business}: ${revenue:,.2f}")
    print()
    
    print("3️⃣ Revenue DataFrame (with business column):")
    print(revenue_df)
    print()
    
    # Verifiche
    print("🔍 VALIDATIONS:")
    
    # Test 1: Numero di business
    expected_businesses = 2
    if len(business_names) == expected_businesses:
        print(f"   ✅ Found {expected_businesses} businesses")
    else:
        print(f"   ❌ Expected {expected_businesses}, got {len(business_names)}")
    
    # Test 2: Revenue totale McDonald's
    expected_mcdonalds = 10200.0
    actual_mcdonalds = revenue_per_business.get("McDonald's", 0)
    if actual_mcdonalds == expected_mcdonalds:
        print(f"   ✅ McDonald's revenue correct: ${expected_mcdonalds:,.2f}")
    else:
        print(f"   ❌ McDonald's: expected ${expected_mcdonalds}, got ${actual_mcdonalds}")
    
    # Test 3: Revenue totale Starbucks
    expected_starbucks = 6500.0
    actual_starbucks = revenue_per_business.get("Starbucks", 0)
    if actual_starbucks == expected_starbucks:
        print(f"   ✅ Starbucks revenue correct: ${expected_starbucks:,.2f}")
    else:
        print(f"   ❌ Starbucks: expected ${expected_starbucks}, got ${actual_starbucks}")
    
    # Test 4: Colonna business esiste
    if "business" in revenue_df.columns:
        print("   ✅ 'business' column created successfully")
    else:
        print("   ❌ 'business' column missing!")
    
    # Test 5: Solo Revenue nel DataFrame
    if len(revenue_df) == 4:  # 4 revenue transactions
        print(f"   ✅ Correctly filtered {len(revenue_df)} revenue transactions")
    else:
        print(f"   ❌ Expected 4 revenue rows, got {len(revenue_df)}")
    
    print("\n🎉 Testing complete!")

if __name__ == "__main__":
    test_revenue_analyzer()