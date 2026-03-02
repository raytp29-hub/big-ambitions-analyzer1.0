"""
analysis/forecasting.py
Forecasting module for Big Ambitions Analyzer.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, List, Dict

class ForecastingAnalyzer:
    """
    Handles forecasting logic for business metrics.
    Uses linear regression (Polyfit) to determine trends and predict future values.
    """
    
    def __init__(self, df: pd.DataFrame):
        """
        Initialize with the main transactions DataFrame.
        """
        self.df = df
        
    def prepare_data(self, business_name: str, metric: str = 'profit', granularity: str = 'daily') -> pd.DataFrame:
        """
        Prepares time-series data for a specific business and metric.
        """
        # Use TemporalAnalyzer to reuse aggregation logic
        from analysis.temporal_analyzer import TemporalAnalyzer
        analyzer = TemporalAnalyzer(self.df)
        
        # Get aggregated data (contains profit, revenue, etc. per business per period)
        agg_df = analyzer.aggregate_by_period(granularity)
        
        # Filter by business
        if business_name != "All Businesses":
            agg_df = agg_df[agg_df['business'] == business_name]
            
            # If after filtering we have multiple rows per period (unlikely for 1 business, but safety),
            # we group by period.
            ts_df = agg_df.groupby('period')[metric].sum().reset_index()
        else:
            # For "All Businesses", sum the metric across all businesses for each period
            ts_df = agg_df.groupby('period')[metric].sum().reset_index()
            
        # Rename columns for consistency
        ts_df.rename(columns={'period': 'x', metric: 'y'}, inplace=True)
        return ts_df.sort_values('x')

    def calculate_trend(self, x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
        """
        Calculates the linear trend line: y = mx + c
        """
        # We use numpy's polyfit for a 1st degree polynomial (linear line)
        if len(x) < 2:
            return 0.0, 0.0, 0.0
            
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
            
        return slope, intercept, r_squared

    def forecast(self, business_name: str, metric: str = 'profit', days_ahead: int = 7, granularity: str = 'daily', method: str = 'linear') -> Dict:
        """
        Generates a complete forecast report.
        
        Returns:
            Dictionary containing:
            - historical: DataFrame {x, y}
            - forecast: DataFrame {x, y, type='forecast'}
            - trend: {slope, intercept, r_squared}
        """
        # 1. Prepare Data
        df = self.prepare_data(business_name, metric, granularity)
    
        if df.empty or len(df) < 2:
            return {"error": "Not enough data to forecast"}
    
        # 2. Route to correct method
        if method == 'moving_average':
            return self.moving_average(df, days_ahead)
    
        # 3. Linear regression (existing code)
        x = df['x'].values
        y = df['y'].values
        
        # 2. Calculate Trend
        slope, intercept, r_squared = self.calculate_trend(x, y)
        
        # 3. Generate Forecast
        last_x = x[-1]
        
        # If daily, we want next 7 days. If weekly, we want next X weeks?
        # Let's assume input 'days_ahead' implies periods ahead if granularity != daily?
        # Actually, for simplicity, let's treat 'days_ahead' as number of *periods* to forecast
        # or we calculate how many periods fit in days_ahead.
        # Let's stick to "periods ahead" logic for the math, 
        # but the UI might say "7 days" which equals 1 week if weekly.
        # For now, let's assume forecast_horizon is in *periods*.
        
        forecast_horizon = days_ahead if granularity == 'daily' else (days_ahead // 7 + 1)
        
        future_x = np.arange(last_x + 1, last_x + 1 + forecast_horizon)
        future_y = slope * future_x + intercept
        
        forecast_df = pd.DataFrame({'x': future_x, 'y': future_y})
        
        return {
            "historical": df,
            "forecast": forecast_df,
            "trend": {
                "slope": slope,
                "intercept": intercept,
                "r_squared": r_squared
            },
            "metric": metric,
            "granularity": granularity
        }


    def moving_average(self, df: pd.DataFrame, days_ahead: int, window: int = 7) -> Dict:
        """
        Forecast using simple moving average.
        """

        if len(df) < window:
            return {"error": "Not enough data for moving average"}
        
        
        x = df['x'].values
        y = df['y'].values

        y_series = pd.Series(y)
        rolling_avg = y_series.rolling(window=window).mean()

        last_avg = rolling_avg.iloc[-1]

        last_x = x[-1]
        future_x = np.arange(last_x + 1, last_x + 1 + days_ahead)
        future_y = np.full(days_ahead, last_avg)

        forecast_df = pd.DataFrame({'x': future_x, 'y': future_y})

        smoothed_df = df.copy()
        smoothed_df["y_smotheed"] = rolling_avg.values

        return {
            "historical": df,
            "forecast": forecast_df,
            "smoothed": smoothed_df.dropna(),
            "trend": {
                "slope": 0.0,
                "intercept": last_avg,
                "r_squared": None
            },
            "last_avg": last_avg,
            "window": window
        }