
import pandas as pd
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
            return "quaterly"
        
        
        
        
        
    
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
            pl_df["period"] = period       
            all_results.append(pl_df)
        
        
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
        
        
        

        
