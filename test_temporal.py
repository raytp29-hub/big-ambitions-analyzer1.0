"""
Test script per TemporalAnalyzer
"""

from core.data_cleaner import clean_big_ambitions_csv
from analysis.temporal_analyzer import TemporalAnalyzer

# Carica i dati
print("📂 Caricamento dati...")
with open("Transactions.csv", "rb") as f:
    df, error = clean_big_ambitions_csv(f.read())

if error:
    print(f"❌ Errore: {error}")
    exit(1)

print(f"✅ Dati caricati: {len(df)} transazioni\n")
"""
# Crea analyzer
analyzer = TemporalAnalyzer(df)

# Info base
print("=" * 60)
print("📊 INFORMAZIONI DATASET")
print("=" * 60)
print(f"Range dati: Day {analyzer.min_day} → Day {analyzer.max_day}")
print(f"Total days: {analyzer.total_days}")
print(f"Granularity consigliata: {analyzer.get_recommended_granularity()}\n")

# Test Daily
print("=" * 60)
print("📅 TEST: DAILY AGGREGATION")
print("=" * 60)
try:
    result_daily = analyzer.aggregate_by_period('daily')
    print(f"✅ Successo!")
    print(f"   Numero periodi: {result_daily['period'].nunique()}")
    print(f"   Numero righe totali: {len(result_daily)}")
    print(f"\n   Periods unici:")
    for label in sorted(result_daily['period_label'].unique()):
        print(f"      - {label}")
    
    print(f"\n   Sample data (prime 5 righe):")
    print(result_daily[['period_label', 'business', 'revenue', 'profit']].head())
except Exception as e:
    print(f"❌ Errore: {e}")
    import traceback
    traceback.print_exc()

# Test Weekly
print("\n" + "=" * 60)
print("📅 TEST: WEEKLY AGGREGATION")
print("=" * 60)
try:
    result_weekly = analyzer.aggregate_by_period('weekly')
    print(f"✅ Successo!")
    print(f"   Numero periodi: {result_weekly['period'].nunique()}")
    print(f"   Numero righe totali: {len(result_weekly)}")
    print(f"\n   Periods unici:")
    for label in sorted(result_weekly['period_label'].unique()):
        print(f"      - {label}")
    
    print(f"\n   Sample data (prime 10 righe):")
    print(result_weekly[['period_label', 'business', 'revenue', 'profit']].head(10))
except Exception as e:
    print(f"❌ Errore: {e}")
    import traceback
    traceback.print_exc()

# Test Auto
print("\n" + "=" * 60)
print("📅 TEST: AUTO GRANULARITY")
print("=" * 60)
try:
    result_auto = analyzer.aggregate_by_period('auto')
    print(f"✅ Successo!")
    print(f"   Granularity usata: {analyzer.get_recommended_granularity()}")
    print(f"   Numero periodi: {result_auto['period'].nunique()}")
except Exception as e:
    print(f"❌ Errore: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("✅ Test completati!")
print("=" * 60)

"""



from analysis.temporal_analyzer import TemporalAnalyzer


analyzer = TemporalAnalyzer(df)
total_revenue = analyzer.calculate_period_metrics(None,"weekly")
print(total_revenue)