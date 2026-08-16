import pandas as pd
import numpy as np
from analysis.profit_loss import calculate_profit_loss


PERIOD_DAYS = {
    "daily": 1,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 90
}



class TemporalAnalyzer:
    
    
    def __init__(self, df):
        self.df = df
        self.min_day = df["day"].min()
        self.max_day = df["day"].max()
        self.total_days = self.max_day - self.min_day + 1

    
    def get_recommended_granularity(self):
        """Suggerisce granularità ottimale based on range"""
        if self.total_days <= 30:
            return "daily"
        elif self.total_days <= 90:
            return "weekly"
        elif self.total_days <= 180:
            return "biweekly"
        elif self.total_days <= 365:
            return "monthly"
        else:
            return "quarterly"
        
        
        
        
        
    
    def aggregate_by_period(self, granularity="auto"):
        
        if granularity == "auto":
            granularity = self.get_recommended_granularity()
            
            
        df_copy = self.df.copy()
        
        if granularity == "daily":
            df_copy["period"] = df_copy["day"] - self.min_day
        else:
            period_days = PERIOD_DAYS[granularity]
            df_copy["period"] = (df_copy["day"] - self.min_day) // period_days
            
        periods = sorted(df_copy["period"].unique())
        all_results = []
        
        for period in periods:
            period_df = df_copy[df_copy["period"] == period]
            pl_df = calculate_profit_loss(period_df)

            # Salta i periodi senza business attribuibili: un DataFrame vuoto
            # nel concat forzerebbe le colonne numeriche a dtype 'object'
            if pl_df.empty:
                continue

            pl_df["period"] = period
            all_results.append(pl_df)

        if not all_results:
            # Nessun periodo con dati attribuibili
            empty = calculate_profit_loss(df_copy.iloc[0:0])
            empty["period"] = pd.Series(dtype=int)
            empty["period_label"] = pd.Series(dtype=str)
            return empty

        final_df = pd.concat(all_results, ignore_index=True)
        
        final_df["period_label"] = final_df["period"].apply(lambda d: self._create_period_label(d, granularity))
                
        return final_df
    
    
    
    
    
    
    def _create_period_label(self, period: int, granularity: str) -> str:
        
        if granularity == "daily":
            actual_day = self.min_day + period
            return f"Day {actual_day}"
        
        else: 
            period_days = PERIOD_DAYS[granularity]
            start_day = self.min_day + (period_days * period)
            end_day = min(start_day + period_days - 1, self.max_day)
            
            
            if granularity == "weekly":
                period_name = "Week"
            elif granularity == "biweekly":
                period_name = "Bi-Week"
            elif granularity == "monthly":
                period_name = "Month"
            elif granularity == "quarterly":
                period_name = "Quarter"
                
            return f"{period_name} {period + 1} (Day {start_day}---{end_day})"
        
   
   
   
   
   # ==============================================
   #                ESERCITAZIONE
   #===============================================
        
        
    def calculate_total_revenue_by_period(self, granularity="weekly"):
        # Otteniamo il dataFrame aggregato per colonna period
        aggregated_df = self.aggregate_by_period(granularity)
        
        total_revenue = aggregated_df.groupby("period")["revenue"].sum()
        
        return total_revenue
    
    
    def calculate_average_profit_per_business(self, granularity="weekly"):
        
        aggregated_df = self.aggregate_by_period(granularity)
        
        
        # calcolo della media
        average_profit = aggregated_df.groupby("period")["profit"].mean()
        
        return average_profit
    
    
    
    def calculate_period_metrics(self, business_name=None, granularity= "weekly"):
        
        aggregated_df = self.aggregate_by_period(granularity)
        
        if business_name is not None:
            aggregated_df = aggregated_df[aggregated_df["business"] == business_name]
            
        metrics = aggregated_df.groupby("period").agg({
            "revenue":"sum",
            "total_costs":"sum",
            "profit":"sum",
            "margin_pct": "mean",
            "business": "count"
        })
        
        metrics.columns = [
            "total_revenue",
            "total_costs",
            "total_profit",
            "avg_margin_pct",
            "num_business"
        ]
        
        
        metrics = metrics.reset_index()
        
        metrics["period_label"] = metrics["period"].apply(lambda p: self._create_period_label(p, granularity))
        
        return metrics
    
    
    
    
    
    
    
    
    
    
    # ===============================================
    #           Funzione Comparazione Periodi
    # ===============================================
    
    
    def compare_periods(self, period1: int, period2: int, granularity="weekly", business_name=None):
        """
            Confronta due periodi specifici.
            
            Args:
                period1: Numero primo periodo (es. 0 = Week 1)
                period2: Numero secondo periodo (es. 1 = Week 2)
                granularity: Aggregazione temporale
                business_name: Opzionale, filtra per business specifico
            
            Returns:
                DataFrame con confronto side-by-side
        """
        # Step 1: Ottieni metriche per tutti i periodi
        metrics = self.calculate_period_metrics(business_name, granularity)
            
        
        
        # Step 2: Verifica che i periodi esistano
        available_periods = metrics["period"].unique()
        if period1 not in available_periods:
            raise ValueError(f"Period {period1} not found")
        if period2 not in available_periods:
            raise ValueError(f"Period {period2} not found")
        
        
        # Step 3: Estrai dati Period 1 e Period 2
        period1_data = metrics[metrics["period"] == period1]
        period2_data = metrics[metrics["period"] == period2]
        
        # Step 4: Seleziona solo colonne numeriche rilevanti
        numeric_cols = ["total_revenue", "total_costs", "total_profit", "avg_margin_pct", "num_business"]
        
        
        
        try:
            p1_values = period1_data[numeric_cols].values[0]
            p2_values = period2_data[numeric_cols].values[0]
        except IndexError:
            raise ValueError(f"Date not found for periods {period1}, {period2}")
        # Step 5: Calcola Delta
        delta = p2_values - p1_values
        
        # Step 6: Calcola Growth %
        growth = np.where(
            p1_values == 0,
            np.nan,
            (delta / p1_values) * 100
        )
        
        # Step 7: Costruisci DataFrame risultato
        comparison_df = pd.DataFrame({
            "metric": numeric_cols,
            "period_1": period1_data[numeric_cols].values[0],
            "period_2": period2_data[numeric_cols].values[0],
            "delta": delta,
            "growth_pct": growth
        }) 

        # Step 8: Formatta e ritorna
        return comparison_df