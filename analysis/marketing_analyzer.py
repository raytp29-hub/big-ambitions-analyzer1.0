"""
analysis/marketing_analyzer.py
Analyzes the correlation between Marketing Spend and Revenue/Profit.
"""

import pandas as pd
import numpy as np
import statsmodels.api as sm
from scipy import stats as scipy_stats
from typing import Dict, Optional, Tuple

from analysis.temporal_analyzer import TemporalAnalyzer



class MarketingAnalyzer:
    """
    Analyzes the impact of marketing on business performance.
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        
    def prepare_marketing_data(self, business_name: str, granularity: str = 'daily') -> pd.DataFrame:
        """
        Aggregates data to have Marketing Cost vs Revenue/Profit side-by-side.
        """
        # Reuse temporal aggregation to get daily/weekly stats
        
        analyzer = TemporalAnalyzer(self.df)
        
        # Get raw aggregated data
        agg_df = analyzer.aggregate_by_period(granularity)
        
        # Filter by business (if not "All Businesses")
        if business_name != "All Businesses":
            agg_df = agg_df[agg_df['business'] == business_name]

        # Group by period to get single row per period
        data = agg_df.groupby('period')[['marketing', 'revenue', 'profit']].sum().reset_index()
            
        # We only care about periods where we spent SOMETHING on marketing?
        # Or even 0 marketing is a data point (baseline revenue).
        # Let's keep all data points, but maybe filter outliers later.
        
        return data
        
    def calculate_correlation(self, business_name: str, target_metric: str = 'revenue', granularity: str = 'daily') -> Dict:
        """
        Calculates correlation between Marketing and Target Metric (Revenue/Profit).
        Performs Linear Regression: Target = m * Marketing + c
        """
        data = self.prepare_marketing_data(business_name, granularity)
        
        if len(data) < 2:
            return {"error": "Not enough data points"}
            
        x = data['marketing'].values
        y = data[target_metric].values
        
        # 1. Correlation Coefficient (Pearson)
        # If x is constant (e.g. always 0 marketing), correlation is undefined/NaN.
        if np.std(x) == 0:
            correlation = 0.0
            slope = 0.0
            intercept = np.mean(y)
        else:
            correlation = np.corrcoef(x, y)[0, 1]
            if np.isnan(correlation): correlation = 0.0
            
            # 2. Linear Regression (Polyfit degree 1)
            slope, intercept = np.polyfit(x, y, 1)
            
        # Calculate R-squared
        predict_y = slope * x + intercept
        residuals = y - predict_y
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((y - np.mean(y))**2)
        
        if ss_tot == 0:
            r_squared = 0.0
        else:
            r_squared = 1 - (ss_res / ss_tot)
            
        return {
            "business": business_name,
            "metric": target_metric,
            "correlation": correlation,
            "slope": slope,     # ROI (Return on Ad Spend approx)
            "intercept": intercept, # Baseline (Revenue with 0 marketing)
            "r_squared": r_squared,
            "data": data # Return data for plotting
        }
        
    def predict_impact(self, business_name: str, marketing_budget: float, target_metric: str = 'revenue') -> float:
        """
        Predicts the target_metric value for a given marketing_budget.
        """
        stats = self.calculate_correlation(business_name, target_metric)
        
        if "error" in stats:
            return 0.0
            
        slope = stats['slope']
        intercept = stats['intercept']
        
        prediction = slope * marketing_budget + intercept
        return max(0.0, prediction) # No negative revenue


    def difference_in_means(self, business_name:str, granularity: str = 'daily'):
        marketing_df = self.df[
            (self.df['type'] == 'Marketing') &
            (self.df['description'].str.contains(business_name))
        ]


        marketing_days = set(marketing_df['day'].unique())

        data = self.prepare_marketing_data(business_name, granularity)
        min_day = self.df['day'].min()

        # Convert marketing days to the same period space as the aggregated data
        from analysis.temporal_analyzer import PERIOD_DAYS
        if granularity == 'daily':
            marketing_periods = set(d - min_day for d in marketing_days)
        else:
            period_days = PERIOD_DAYS[granularity]
            marketing_periods = set((d - min_day) // period_days for d in marketing_days)

        data['marketing_on'] = data['period'].isin(marketing_periods)
        
        means = data.groupby('marketing_on')['revenue'].mean()
        if False not in means.index or True not in means.index:
            return {"error": "Not enough marketing ON/OFF days to compare"}
        mean_off = means[False]
        mean_on = means[True]

        delta = mean_on - mean_off
        delta_pct = (delta / mean_off) * 100 if mean_off != 0 else 0.0

        # T-test: is the difference statistically significant?
        revenue_on = data[data['marketing_on'] == True]['revenue'].values
        revenue_off = data[data['marketing_on'] == False]['revenue'].values

        if len(revenue_on) >= 2 and len(revenue_off) >= 2:
            t_stat, p_value = scipy_stats.ttest_ind(revenue_on, revenue_off, equal_var=False)
        else:
            t_stat, p_value = 0.0, 1.0

        data['day'] = data['period'] + self.df['day'].min()
        return {
            "business": business_name,
            "mean_revenue_on": mean_on,
            "mean_revenue_off": mean_off,
            "delta": delta,
            "delta_pct": delta_pct,
            "t_stat": t_stat,
            "p_value": p_value,
            "n_on": len(revenue_on),
            "n_off": len(revenue_off),
            "data": data
        }
        
    def regression_with_time_control(self, business_name: str, granularity: str = 'daily') -> Dict:
        
        dim_result = self.difference_in_means(business_name, granularity)
        if "error" in dim_result:
            return {"error": dim_result["error"]}
        data = dim_result['data']
        
        X = data[['marketing_on', 'day']].astype(float)
        Y = data['revenue'].astype(float)
        
        X = sm.add_constant(X)
        model = sm.OLS(Y, X).fit()
        
        
        return {
            "data": dim_result,
            "p_value_marketing": model.pvalues['marketing_on'],
            "r_squared": model.rsquared,
            "beta_marketing": model.params['marketing_on'],
            "beta_time": model.params['day'],
            "beta_const": model.params['const']
        }