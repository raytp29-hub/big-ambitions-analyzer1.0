"""
test_parser.py
Quick test del parsing logic
"""

def test_parse():
    """Test del parse manuale"""
    
    # Test cases
    test_cases = [
        # (input, expected_output)
        (
            'Tax Payment,"180","Tax Payment","-284156.2","2049546"',
            ["Tax Payment", "180", "Tax Payment", "-284156.2", "2049546"]
        ),
        (
            'Silver Health Insurance (John, Doe),"179","Insurance","-128.35","1000"',
            ["Silver Health Insurance (John, Doe)", "179", "Insurance", "-128.35", "1000"]
        ),
        (
            'Simple,"100","Type","-50","500"',
            ["Simple", "100", "Type", "-50", "500"]
        ),
        (
            'Kathleen Hinds (HQ Ray Daily Wage),"179","Wage","-325.8668","2134567"',
            ["Kathleen Hinds (HQ Ray Daily Wage)", "179", "Wage", "-325.8668", "2134567"]
        )
    ]
    
    print("🧪 Testing parser logic...\n")
    
    for i, (line, expected) in enumerate(test_cases, 1):
        print(f"Test {i}:")
        print(f"Input:    {line}")
        
        # Parse logic (copiato dal tuo codice)
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
            parts.append(current)
        
        # Risultato
        print(f"Output:   {parts}")
        print(f"Expected: {expected}")
        
        # Verifica
        if parts == expected:
            print("✅ PASS\n")
        else:
            print("❌ FAIL")
            print(f"   Difference: Got {len(parts)} parts, expected {len(expected)}")
            for j, (got, exp) in enumerate(zip(parts, expected)):
                if got != exp:
                    print(f"   Part {j}: '{got}' != '{exp}'")
            print()

if __name__ == "__main__":
    test_parse()