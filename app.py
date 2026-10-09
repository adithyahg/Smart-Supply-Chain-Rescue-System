import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="Smart Supply Chain Control Tower",
    page_icon="📦",
    layout="wide"
)

# Enterprise navy theme
st.markdown("""
<style>
.stApp { background-color: #F4F7FB; }
[data-testid="stMetric"] {
    background: white;
    padding: 18px;
    border-radius: 12px;
    border: 1px solid #E2E8F0;
}
h1, h2, h3 { color: #17365D; }
</style>
""", unsafe_allow_html=True)

st.title("📦 Smart Supply Chain Control Tower")
st.caption(
    "Inventory intelligence | Rescue decisions | "
    "Operational risk management"
)

@st.cache_data
def load_data():
    return pd.read_csv("powerbi_final.csv")

try:
    df = load_data()
except FileNotFoundError:
    st.error(
        "powerbi_final.csv is missing. "
        "Upload it beside app.py in your project repository."
    )
    st.stop()

# Ensure numeric columns are usable
numeric_cols = [
    "Current_Stock", "Daily_Demand", "Unit_Cost",
    "Potential_Shortage", "Inventory_Value",
    "Estimated_Cost", "Remaining_Shortage",
    "Recommended_Units", "Days_of_Stock",
    "Business_Cost"
]

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# Sidebar filters
st.sidebar.header("Dashboard Filters")

products = sorted(df["Product"].dropna().unique())
warehouses = sorted(df["Warehouse"].dropna().unique())

selected_products = st.sidebar.multiselect(
    "Select products", products, default=products
)
selected_warehouses = st.sidebar.multiselect(
    "Select warehouses", warehouses, default=warehouses
)

filtered = df[
    df["Product"].isin(selected_products)
    & df["Warehouse"].isin(selected_warehouses)
].copy()

if filtered.empty:
    st.warning("No records match these filters. Select another option.")
    st.stop()

def total(col):
    return filtered[col].sum() if col in filtered.columns else 0

# KPI cards
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Inventory Value", f"₹{total('Inventory_Value'):,.0f}")
with c2:
    st.metric("Potential Shortage", f"{total('Potential_Shortage'):,.0f} units")
with c3:
    st.metric("Estimated Rescue Cost", f"₹{total('Estimated_Cost'):,.0f}")
with c4:
    st.metric("Remaining Shortage", f"{total('Remaining_Shortage'):,.0f} units")

st.divider()

# Charts
left, right = st.columns(2)

with left:
    st.subheader("Shortage by Product")
    chart_data = (
        filtered.groupby("Product", as_index=False)["Potential_Shortage"]
        .sum()
    )
    fig = px.bar(
        chart_data,
        x="Product",
        y="Potential_Shortage",
        color_discrete_sequence=["#2878B5"],
        template="plotly_white"
    )
    fig.update_layout(
        xaxis_title="Product",
        yaxis_title="Shortage (units)",
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Rescue Cost by Action")
    if "Recommended_Action" in filtered.columns:
        cost_data = (
            filtered.groupby("Recommended_Action", as_index=False)
            ["Estimated_Cost"].sum()
        )
        fig2 = px.bar(
            cost_data,
            x="Recommended_Action",
            y="Estimated_Cost",
            color_discrete_sequence=["#17365D"],
            template="plotly_white"
        )
        fig2.update_layout(
            xaxis_title="Rescue action",
            yaxis_title="Estimated cost (₹)",
            showlegend=False
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Rescue action data is not available.")

# Rescue decision table
st.divider()
st.subheader("🚨 Rescue Recommendation Register")

preferred_cols = [
    "Product", "Warehouse", "Potential_Shortage",
    "Recommended_Action", "Recommended_Units",
    "Delivery_Days", "Estimated_Cost",
    "Remaining_Shortage", "Decision_Status"
]

display_cols = [c for c in preferred_cols if c in filtered.columns]

if display_cols:
    table = filtered[display_cols].copy()
    if "Potential_Shortage" in table.columns:
        table = table.sort_values(
            "Potential_Shortage", ascending=False
        )
    st.dataframe(table, use_container_width=True, hide_index=True)

# Download current filtered results
st.download_button(
    "Download filtered decisions (CSV)",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name="supply_chain_decisions.csv",
    mime="text/csv"
)

st.caption(
    "Prototype decision-support system. "
    "Recommendations use the current exported dataset; "
    "they are not live ERP data."
)
