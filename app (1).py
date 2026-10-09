import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------- setup
st.set_page_config(page_title="Supply Chain Control Tower", page_icon="📦", layout="wide")

INK, TEAL, AMBER, RED = "#12343B", "#1F7A6D", "#D99A1E", "#C23B32"
MUTED, LINE, BG = "#5B7075", "#D5DEE0", "#EDF1F2"
FONT = "Public Sans, sans-serif"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;700&family=Public+Sans:wght@400;500;600&display=swap');
html, body, .stApp, [class*="css"] {{ font-family: {FONT}; }}
.stApp {{ background: {BG}; }}
.block-container {{ padding-top: 2.2rem; max-width: 1280px; }}
h1, h2, h3 {{ font-family: 'Bricolage Grotesque', sans-serif !important; color: {INK}; letter-spacing: -0.01em; }}
[data-testid="stSidebar"] {{ background: {INK}; }}
[data-testid="stSidebar"] * {{ color: #E6EEEF !important; }}
[data-testid="stSidebar"] [data-baseweb="tag"] {{ background: {TEAL} !important; }}
.brand {{ font-family: 'Bricolage Grotesque'; font-size: 1.5rem; font-weight: 700; color: {INK}; margin: 0; }}
.brand small {{ display:block; font-family:{FONT}; font-weight:400; font-size:.9rem; color:{MUTED}; margin-top:2px; }}
.status {{ background:#fff; border-left:6px solid var(--c); padding:18px 24px; margin:18px 0 22px; border-radius:4px; }}
.status h2 {{ margin:0 0 4px; font-size:1.65rem; }}
.status p {{ margin:0; color:{MUTED}; }}
.band {{ display:flex; background:#fff; border:1px solid {LINE}; border-radius:4px; margin-bottom:26px; }}
.band div {{ flex:1; padding:16px 22px; border-right:1px solid {LINE}; }}
.band div:last-child {{ border-right:none; }}
.band span {{ display:block; font-size:.82rem; color:{MUTED}; }}
.band b {{ display:block; font-family:'Bricolage Grotesque'; font-size:1.7rem; color:{INK}; font-variant-numeric:tabular-nums; }}
.band em {{ font-style:normal; font-size:.8rem; color:{MUTED}; }}
.plan {{ background:#fff; border:1px solid {LINE}; border-radius:4px; padding:18px 22px; margin-bottom:14px; }}
.plan h4 {{ margin:0; font-family:'Bricolage Grotesque'; font-size:1.15rem; color:{INK}; }}
.plan .meta {{ color:{MUTED}; font-size:.88rem; margin:2px 0 12px; }}
.track {{ height:10px; background:#F3D9D6; border-radius:5px; overflow:hidden; }}
.track i {{ display:block; height:100%; background:{TEAL}; }}
.plan .row {{ display:flex; gap:36px; margin-top:12px; flex-wrap:wrap; }}
.plan .row div span {{ display:block; font-size:.78rem; color:{MUTED}; }}
.plan .row div b {{ font-variant-numeric:tabular-nums; color:{INK}; }}
.stTabs [data-baseweb="tab"] {{ font-weight:600; }}
</style>
""", unsafe_allow_html=True)


def inr(x):
    s = f"{int(round(x))}"
    if len(s) <= 3:
        return f"₹{s}"
    return "₹" + re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", s[:-3]) + "," + s[-3:]


# ---------------------------------------------------------------- data
@st.cache_data
def load_data():
    d = pd.read_csv("powerbi_final.csv")
    num = [c for c in d.columns if c not in ("Product", "Warehouse", "Recommended_Action", "Decision_Status")]
    d[num] = d[num].apply(pd.to_numeric, errors="coerce")
    return d


try:
    raw = load_data()
except FileNotFoundError:
    st.error("powerbi_final.csv not found. Place it in the same folder as app.py and rerun.")
    st.stop()


def simulate(d, surge, delay):
    """Recompute risk from first principles. surge=0, delay=0 reproduces the file."""
    d = d.copy()
    f = 1 + surge / 100
    d["Demand"] = d["Daily_Demand"] * f
    d["Lead"] = d["Lead_Time_Days"] + delay
    d["Days"] = d["Current_Stock"] / d["Demand"]
    d["Cover"] = d["Days"] / d["Lead"]
    d["Short"] = np.ceil((d["Demand"] * d["Lead"] - d["Current_Stock"]).clip(lower=0))
    d["Spare"] = np.floor((d["Current_Stock"] - d["Safety_Stock"] * f).clip(lower=0))
    d["Covered"] = 0.0
    for _, g in d.groupby("Product"):
        pool = g.loc[g["Short"] == 0, "Spare"].sum()
        for i in g[g["Short"] > 0].sort_values("Short", ascending=False).index:
            take = min(d.at[i, "Short"], pool)
            d.at[i, "Covered"], pool = take, pool - take
    d["Exposed"] = d["Short"] - d["Covered"]
    d["Site"] = d["Product"] + ", " + d["Warehouse"]
    return d


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### Filters")
    prods = sorted(raw["Product"].dropna().unique())
    whs = sorted(raw["Warehouse"].dropna().unique())
    sel_p = st.multiselect("Products", prods, default=prods)
    sel_w = st.multiselect("Warehouses", whs, default=whs)
    st.markdown("### What-if scenario")
    surge = st.slider("Demand change (%)", -30, 100, 0, 5)
    delay = st.slider("Supplier delay (days)", 0, 10, 0)
    if surge or delay:
        st.caption("Risk and transfer cover are recalculated. Costs come from the baseline plan only.")

sim = simulate(raw, surge, delay)
baseline = surge == 0 and delay == 0
df = sim[sim["Product"].isin(sel_p) & sim["Warehouse"].isin(sel_w)]

st.markdown('<p class="brand">Supply Chain Control Tower<small>Which stock runs out before resupply arrives, and what rescues it</small></p>', unsafe_allow_html=True)

if df.empty:
    st.warning("No stock positions match these filters. Select at least one product and one warehouse.")
    st.stop()

# ---------------------------------------------------------------- status
at_risk = df[df["Short"] > 0]
short, covered, exposed = df["Short"].sum(), df["Covered"].sum(), df["Exposed"].sum()
if len(at_risk) == 0:
    colour, head, sub = TEAL, "Every position lasts until resupply arrives.", "No rescue action is needed at these settings."
else:
    colour = RED if exposed > 0 else AMBER
    head = f"{len(at_risk)} of {len(df)} stock positions run out before resupply arrives."
    sub = f"Rescue covers {covered:,.0f} of {short:,.0f} short units. " + (
        f"{exposed:,.0f} units stay exposed." if exposed else "Nothing stays exposed.")
st.markdown(f'<div class="status" style="--c:{colour}"><h2>{head}</h2><p>{sub}</p></div>', unsafe_allow_html=True)

cost = df["Estimated_Cost"].sum() if baseline else None
st.markdown(f"""<div class="band">
<div><span>Inventory value</span><b>{inr(df['Inventory_Value'].sum())}</b><em>{df['Current_Stock'].sum():,.0f} units on hand</em></div>
<div><span>Positions at risk</span><b>{len(at_risk)} / {len(df)}</b><em>cover below 1.0x lead time</em></div>
<div><span>Units short</span><b>{short:,.0f}</b><em>before any rescue</em></div>
<div><span>Covered by transfer</span><b>{(covered / short * 100 if short else 100):.0f}%</b><em>{exposed:,.0f} units exposed</em></div>
<div><span>Rescue cost</span><b>{inr(cost) if cost is not None else "n/a"}</b><em>{"baseline plan" if baseline else "reset scenario to see"}</em></div>
</div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- tabs
tab1, tab2, tab3 = st.tabs(["Stock runway", "Rescue plan", "Data"])


def style(fig, h):
    fig.update_layout(height=h, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT, color=INK))
    return fig


with tab1:
    a, b = st.columns([3, 2], gap="large")
    with a:
        st.subheader("Days of stock against resupply time")
        st.caption("Each bar is how long stock lasts. The black tick is when resupply arrives. Bars that stop short of the tick run out.")
        r = df.sort_values("Cover", ascending=False)
        cols = [RED if c < 1 else AMBER if c < 1.25 else TEAL for c in r["Cover"]]
        fig = go.Figure()
        fig.add_bar(y=r["Site"], x=r["Days"], orientation="h", marker_color=cols, name="Days of stock",
                    hovertemplate="%{y}<br>%{x:.1f} days of stock<extra></extra>")
        fig.add_scatter(y=r["Site"], x=r["Lead"], mode="markers", name="Resupply arrives",
                        marker=dict(symbol="line-ns", size=26, line=dict(width=3, color=INK)),
                        hovertemplate="%{y}<br>resupply in %{x:.0f} days<extra></extra>")
        fig.update_xaxes(title="Days", gridcolor=LINE, zeroline=False)
        fig.update_yaxes(title=None)
        fig.update_layout(legend=dict(orientation="h", y=1.1, x=0), bargap=0.45)
        st.plotly_chart(style(fig, 90 + 56 * len(r)), use_container_width=True)
    with b:
        st.subheader("Cover by site")
        st.caption("Days of stock divided by resupply time. Below 1.0 means a stock-out.")
        piv = df.pivot_table(index="Product", columns="Warehouse", values="Cover", aggfunc="min")
        hm = go.Figure(go.Heatmap(
            z=piv.values, x=piv.columns, y=piv.index, zmin=0, zmax=2, xgap=4, ygap=4,
            colorscale=[[0, RED], [0.5, AMBER], [1, TEAL]], showscale=False,
            text=np.round(piv.values, 2), texttemplate="%{text}x", textfont=dict(color="white", size=15),
            hovertemplate="%{y}, %{x}<br>%{z:.2f}x<extra></extra>"))
        st.plotly_chart(style(hm, 90 + 70 * len(piv)), use_container_width=True)

with tab2:
    if at_risk.empty:
        st.info("Nothing to rescue at these settings. Raise demand or supplier delay in the sidebar to test the network.")
    for _, x in at_risk.sort_values("Exposed", ascending=False).iterrows():
        pct = x["Covered"] / x["Short"] * 100
        action = (x["Recommended_Action"] if baseline and pd.notna(x["Recommended_Action"])
                  else "Warehouse transfer" if x["Covered"] > 0 else "No spare stock to transfer")
        dd = f"{x['Delivery_Days']:.0f} day" if baseline and pd.notna(x["Delivery_Days"]) else "n/a"
        ec = inr(x["Estimated_Cost"]) if baseline and pd.notna(x["Estimated_Cost"]) else "n/a"
        bc = inr(x["Business_Cost"]) if baseline and pd.notna(x["Business_Cost"]) else "n/a"
        st.markdown(f"""<div class="plan">
<h4>{x['Product']}, {x['Warehouse']}</h4>
<p class="meta">Stock lasts {x['Days']:.1f} days. Resupply takes {x['Lead']:.0f}.</p>
<div class="track"><i style="width:{pct:.0f}%"></i></div>
<div class="row">
<div><span>Short</span><b>{x['Short']:,.0f} units</b></div>
<div><span>Covered</span><b>{x['Covered']:,.0f} units ({pct:.0f}%)</b></div>
<div><span>Still exposed</span><b>{x['Exposed']:,.0f} units</b></div>
<div><span>Action</span><b>{action}</b></div>
<div><span>Delivery</span><b>{dd}</b></div>
<div><span>Rescue cost</span><b>{ec}</b></div>
<div><span>Business cost</span><b>{bc}</b></div>
</div></div>""", unsafe_allow_html=True)

with tab3:
    show = df[["Product", "Warehouse", "Current_Stock", "Days", "Lead", "Cover", "Short", "Covered", "Exposed", "Inventory_Value"]]
    st.dataframe(
        show, use_container_width=True, hide_index=True,
        column_config={
            "Current_Stock": "Stock", "Days": st.column_config.NumberColumn("Days of stock", format="%.1f"),
            "Lead": st.column_config.NumberColumn("Resupply days", format="%.0f"),
            "Cover": st.column_config.ProgressColumn("Cover (x lead time)", min_value=0, max_value=2, format="%.2f"),
            "Short": "Units short", "Covered": "Units covered", "Exposed": "Units exposed",
            "Inventory_Value": st.column_config.NumberColumn("Inventory value", format="₹%d"),
        })
    st.download_button("Download this view (CSV)", show.to_csv(index=False).encode("utf-8"),
                       "supply_chain_view.csv", "text/csv")

st.caption("Prototype decision support. Figures come from the exported dataset, not live ERP data.")
