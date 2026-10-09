# Smart Supply Chain Control Tower

Live demo: https://smart-supply-chain-rescue-system-p9c2jrymbefzkti5jwkvpi.streamlit.app/


A dashboard that shows which stock will run out before resupply arrives, recommends warehouse-transfer rescues, and emails suppliers automatically when stock gets low.

## What it does
- Stock runway chart and cover heatmap by product and warehouse
- Rescue plan with cost and coverage for each at-risk position
- What-if sliders for demand surge and supplier delay
- Live simulation mode, plus a Google Sheet mode for real data
- Apps Script automation that emails the supplier and writes the order back to the sheet

## Tech
Python, Streamlit, Pandas, Plotly, Google Sheets, Google Apps Script

## How it fits together
Google Sheet (stock data) → Apps Script (low stock → supplier email) → Streamlit dashboard (reads the sheet, shows orders)

## Run locally
pip install -r requirements.txt
streamlit run app.py
