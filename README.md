# 🎮 Big Ambitions Business Analyzer

> Professional analytics dashboard for Big Ambitions game data

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.28+-red.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🚀 Current Status

**✅ Version 1.0 - Core Features Complete**

- ✅ **Data cleaning module** - Handles nested quotes and malformed CSV
- ✅ **File upload & processing** - CSV/XLSM support
- ✅ **Interactive dashboard** - Metrics, statistics, and data preview
- ✅ **Data filtering** - Filter by transaction type and date range
- ✅ **Export functionality** - Download cleaned data
- 🟡 Revenue analysis (in development)
- 🟡 P&L calculator (in development)

## 📋 About

Big Ambitions Business Analyzer is a tool for analyzing business performance data from the game "Big Ambitions". It automatically cleans malformed CSV exports and provides interactive visualizations.

### ✨ Key Features

- 🔧 **Robust Data Cleaning**: Handles nested quotes, commas in descriptions, automatic type conversion
- 📊 **Interactive Dashboard**: Real-time metrics, multi-tab interface, transaction breakdown
- 💾 **Data Export**: Download cleaned data ready for further analysis

## 🛠️ Tech Stack

- **Python 3.10+** - Core language
- **Streamlit** - Web framework
- **Pandas** - Data manipulation
- **Plotly** - Visualizations (coming soon)

## 📦 Installation
```bash
# Clone
git clone https://github.com/raytp29-hub/big-ambitions-analyzer1.0.git
cd big-ambition-analyzer

# Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install
pip install -r requirements.txt

# Run
streamlit run app.py