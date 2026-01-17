# Big Ambitions Business Analyzer 📊

A free web application for analyzing business performance and optimizing employee schedules in [Big Ambitions](link-al-gioco).

[![Live Demo](https://img.shields.io/badge/demo-live-success)]([your-url](https://big-ambitions-analyzer1-0.onrender.com/))
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.31+-red.svg)](https://streamlit.io/)

**[🚀 Try it Live](your-url)** | **[📸 Screenshots](#screenshots)** | **[🎯 Features](#features)**

---

## Overview

Built to solve the challenge of manually tracking profits and optimizing employee schedules in Big Ambitions. This tool automates business analysis and generates optimal employee schedules using mathematical optimization.

**Received positive feedback from the game's founder** and actively used by the Big Ambitions community.

---

## ✨ Features

### 📈 Profit & Loss Analysis
- Automatic transaction categorization
- Product and category-level profitability tracking
- Interactive filtering and sorting
- Export results to CSV

### 📊 Temporal Trend Analysis
- Revenue, expenses, and profit tracking over time
- Multi-granularity views (daily, weekly, monthly)
- Interactive Plotly visualizations
- Identify patterns and growth trends

### 🧮 Schedule Optimizer
- Automatic generation of optimal employee schedules
- Constraint-based optimization using linear programming
- Respects employee preferences:
  - Part-time vs full-time availability
  - Days off requests
  - Working hour limits
- Accounts for business capacity (furniture/workstations)
- Maximizes employee satisfaction while meeting coverage requirements
- **Solves in under 1 second** for realistic scenarios

### ⚡ Additional Features
- Browser-based processing (no data storage)
- Responsive design for mobile/tablet
- Fast CSV parsing with error handling
- Session state management for smooth navigation

---

## 🚀 Quick Start

### Using the Web App

1. Visit the **[live demo](https://big-ambitions-analyzer1-0.onrender.com/)**
2. Upload your transaction CSV from Big Ambitions
3. Navigate through the analysis modules
4. For schedule optimization: configure your business setup and generate optimal schedules

*Note: Free hosting may take ~30 seconds to wake up after inactivity. Just refresh if it seems stuck.*

### Running Locally
```bash
# Clone the repository
git clone https://github.com/raytp29-hub/big-ambitions-analyzer1.0
cd big-ambitions-analyzer

# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run app.py
```

---

## 📸 Screenshots

### Upload Files
![Upload Files](/big-ambition-analyzer/analysis/data/screeshots/1.png)
*Main interface with transaction upload and navigation*

### Overview
![Overview](/big-ambition-analyzer/analysis/data/screeshots/2.png)
*Main interface with transaction upload and navigation*

### P&L Analysis
![P&L Analysis](/big-ambition-analyzer/analysis/data/screeshots/3.png)
*Detailed profit and loss breakdown by category*

### Business Setup
![Business Setup](big-ambition-analyzer/analysis/data/screeshots/10.png)
*Business Setup*

### Business Category
![Business Category](big-ambition-analyzer/analysis/data/screeshots/11.png)
*Business Category*

### Building Size
![Building Size](big-ambition-analyzer/analysis/data/screeshots/12.png)
*Choose size of building*

### Furniture Selection
![Furniture Selection](big-ambition-analyzer/analysis/data/screeshots/13.png)
*Furniture selection*

### Capacity Analysis
![Capacity Analysis](big-ambition-analyzer/analysis/data/screeshots/14.png)
*Analize your costumer capacity according to your furniture*

### Employee Details
![Employee Details](big-ambition-analyzer/analysis/data/screeshots/16.png)
*Setup your Employees*

### Employees Demands
![Employees Demands](big-ambition-analyzer/analysis/data/screeshots/17.png)
*Select demands of employee*

### Operating Hours
![Operating Hours](big-ambition-analyzer/analysis/data/screeshots/21.png)
*Setup your operating business hours*

### Optimization
![Schedule Optimizer](big-ambition-analyzer/analysis/data/screeshots/25.png)
*Final schedule result*



---

## 🛠️ Tech Stack

- **Python 3.11+** - Core language
- **Streamlit** - Web framework and UI
- **Pandas** - Data processing and analysis
- **Plotly** - Interactive visualizations
- **PuLP** - Linear programming for schedule optimization
- **Render.com** - Deployment platform

---

## 📊 How It Works

### Transaction Analysis
1. Parse CSV transaction data with malformed record handling
2. Categorize transactions using pattern matching
3. Aggregate data by product, category, and time period
4. Generate interactive visualizations

### Schedule Optimization
Uses **linear programming** to solve a constraint satisfaction problem:

- **Variables:** Employee shift assignments (binary: working or not)
- **Objective:** Maximize employee satisfaction score
- **Constraints:**
  - Business capacity (workstation limits)
  - Employee availability and preferences
  - Operating hours coverage
  - Part-time hour limits
  - Consecutive day work rules

The optimizer uses the PuLP library with CBC solver to generate optimal schedules in milliseconds.

---

## 🎯 Use Cases

- **Profit Analysis:** Identify which products/categories drive revenue
- **Trend Tracking:** Monitor business growth over time
- **Schedule Planning:** Automatically generate fair, efficient employee schedules
- **Data-Driven Decisions:** Base in-game business strategies on real data

---

## 🤝 Contributing

This is a personal portfolio project, but feedback and suggestions are welcome!

- Found a bug? [Open an issue](https://github.com/raytp29-hub/big-ambitions-analyzer1.0/issues)
- Have a feature idea? [Start a discussion](https://github.com/raytp29-hub/big-ambitions-analyzer1.0/issues/new)
- Want to contribute? [Submit a PR](https://github.com/raytp29-hub/big-ambitions-analyzer1.0/pulls)

---

## 📝 License

MIT License - feel free to use this for your own projects!

---

## 🙏 Acknowledgments

- Big Ambitions community for testing and feedback
- Game creator for the positive response and encouragement
- Built as a portfolio project during transition to Data Analytics

---

## 📫 Connect

- **GitHub:** [raytp29-hub](https://github.com/raytp29-hub)


---

**⭐ If you find this useful, consider starring the repo!**