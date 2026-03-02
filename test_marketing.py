"""
test_marketing.py
Tests for the MarketingAnalyzer class.
"""

import pandas as pd
import pytest
from analysis.marketing_analyzer import MarketingAnalyzer

def create_mock_data():
    """
    Creates a mock DataFrame where Revenue = 10 * Marketing + 1000 (roughly)
    """
    data = {
        'day': list(range(1, 11)),
        'business': ['Test Business'] * 10,
        'type': [],
        'description': [],
        'price': [],
        'balance': [0] * 10 # Irrelevant
    }
    
    # Generate rows
    rows = []
    
    for i in range(10):
        marketing_spend = (i + 1) * 100  # 100, 200, ... 1000
        revenue = (marketing_spend * 10) + 1000 # Perfect correlation
        
        # Marketing transaction
        rows.append({
            'day': i + 1,
            'description': 'Marketing for Test Business', # Fixed format
            'type': 'Marketing',
            'price': -marketing_spend, # Negative price
            'balance': 0
        })
        
        # Revenue transaction
        rows.append({
            'day': i + 1,
            'description': 'Test Business Revenue',
            'type': 'Revenue',
            'price': revenue,
            'balance': 0
        })
        
    return pd.DataFrame(rows)

def test_marketing_correlation():
    df = create_mock_data()
    analyzer = MarketingAnalyzer(df)
    
    # Run analysis
    result = analyzer.calculate_correlation("Test Business", "revenue", "daily")
    
    print(f"DEBUG: Slope={result['slope']}, R2={result['r_squared']}")
    
    # Assertions
    assert result['business'] == "Test Business"
    assert result['r_squared'] > 0.99  # Should be practically perfect
    assert 9.9 < result['slope'] < 10.1 # Should be close to 10
    
    # Test Prediction
    # If we spend 500, we expect 500 * 10 + 1000 = 6000
    prediction = analyzer.predict_impact("Test Business", 500, "revenue")
    
    print(f"DEBUG: Predicted revenue for $500 marketing: ${prediction}")
    
    # DEBUG: Print data
    print("DEBUG DATA:")
    print(result['data'])
    
    assert 5900 < prediction < 6100

if __name__ == "__main__":
    test_marketing_correlation()
    print("Test passed!")
