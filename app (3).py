import re
import time
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Supply Chain Control Tower", page_icon="📦", layout="wide")

INK, TEAL, AMBER, RED = "#12343B", "#1F7A6D", "#D99A1E", "#C23B32"
MUTED, LINE, BG = "#5B7075", "#D5DEE0", "#EDF1F2"
FONT = "Public Sans, sans-serif"
# Cost model. These constants reproduce the figures in powerbi_final.csv
# (30 units moved = Rs 340, 10 exposed units of a Rs 120 item = Rs 840). Adjust to match your policy.
TRANSFER_BASE, TRANSFER_PER_UNIT, TRANSFER_DAYS, EXPOSED_RATE = 40, 10, 1, 0.7
REQUIRED = ["Product", "Warehouse", "Current_Stock", "Daily_Demand", "Lead_Time_Days", "Unit_Cost"]

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
.live {{ display:inline-block; font-size:.82rem; color:{INK}; background:#fff; border:1px solid {LINE}; border-radius:20px; padding:4px 12px; margin-top:10px; }}
.live::before {{ content:""; display:inline-block; width:8px; height:8px; border-radius:50%; background:{TEAL}; margin-right:8px; }}
.status {{ background:#fff; border-left:6px solid var(--c); padding:18px 24px; margin:14px 0 22px; border-radius:4px; }}
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
.feed {{ background:#fff; border:1px solid {LINE}; border-radius:4px; padding:6px 18px; font-size:.9rem; }}
.feed p {{ margin:0; padding:9px 0; border-bottom:1px solid {LINE}; color:{INK}; }}
.feed p:last-child {{ border-bottom:none; }}
.stTabs [data-baseweb="tab"] {{ font-weight:600; }}
</style>
""", unsafe_allow_html=True)


def inr(x):
    s = f"{int(round(x))}"
    if len(s) <= 3:
        return f"₹{s}"
    return "₹" + re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", s[:-3]) + "," + s[-3:]


# ------------------------------------------------------------ data sources
@st.cache_data(ttl=10)
def load_source(url):
    d = pd.read_csv(url or "powerbi_final.csv")
    missing = [c for c in REQUIRED if c not in d.columns]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    extra = [c for c in ["Safety_Stock", "Order_Status", "Order_Qty", "Order_Time"] if c in d.columns]
    d = d[REQUIRED + extra].dropna(subset=["Product", "Warehouse"]).copy()
    for c in REQUIRED[2:] + [c for c in extra if c in ("Safety_Stock", "Order_Qty")]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    for c in ("Order_Status", "Order_Time"):
        if c in d.columns:
            d[c] = d[c].fillna("").astype(str)
    if "Safety_Stock" not in d.columns:
        d["Safety_Stock"] = 2 * d["Daily_Demand"]
    return d.reset_index(drop=True)


def init_sim(base):
    st.session_state.sim = dict(stock=base["Current_Stock"].astype(float).values.copy(),
                                orders={}, day=0, spike=0, last=0.0, log=[])
    st.session_state.hist = []


def tick(base, sim):
    rng = np.random.default_rng()
    sim["day"] += 1
    day, mult = sim["day"], (2.0 if sim["spike"] > 0 else 1.0)
    sim["spike"] = max(0, sim["spike"] - 1)
    for i, r in enumerate(base.itertuples()):
        site = f"{r.Product}, {r.Warehouse}"
        sim["stock"][i] = max(0, sim["stock"][i] - round(r.Daily_Demand * mult * rng.uniform(0.6, 1.4)))
        if i in sim["orders"]:
            sim["orders"][i][0] -= 1
            if sim["orders"][i][0] <= 0:
                qty = sim["orders"].pop(i)[1]
                sim["stock"][i] += qty
                sim["log"].insert(0, f"Day {day}: {site} received {qty} units from resupply.")
        if i not in sim["orders"] and sim["stock"][i] < r.Daily_Demand * r.Lead_Time_Days:
            qty = int(r.Daily_Demand * r.Lead_Time_Days * 2)
            sim["orders"][i] = [int(r.Lead_Time_Days), qty]
            sim["log"].insert(0, f"Day {day}: {site} ordered {qty} units, arriving in {int(r.Lead_Time_Days)} days.")
    del sim["log"][40:]


def simulate(d, surge, delay):
    d = d.copy()
    f = 1 + surge / 100
    d["Demand"] = d["Daily_Demand"] * f
    d["Lead"] = d["Lead_Time_Days"] + delay
    d["Days"] = d["Current_Stock"] / d["Demand"].replace(0, np.nan)
    d["Days"] = d["Days"].fillna(999)
    d["Cover"] = d["Days"] / d["Lead"].replace(0, np.nan)
    d["Cover"] = d["Cover"].fillna(9)
    d["Short"] = np.ceil((d["Demand"] * d["Lead"] - d["Current_Stock"]).clip(lower=0))
    d["Spare"] = np.floor((d["Current_Stock"] - d["Safety_Stock"] * f).clip(lower=0))
    d["Covered"] = 0.0
    for _, g in d.groupby("Product"):
        pool = g.loc[g["Short"] == 0, "Spare"].sum()
        for i in g[g["Short"] > 0].sort_values("Short", ascending=False).index:
            take = min(d.at[i, "Short"], pool)
            d.at[i, "Covered"], pool = take, pool - take
    d["Exposed"] = d["Short"] - d["Covered"]
    d["Inventory_Value"] = d["Current_Stock"] * d["Unit_Cost"]
    d["Rescue_Cost"] = np.where(d["Covered"] > 0, TRANSFER_BASE + TRANSFER_PER_UNIT * d["Covered"], 0)
    d["Business_Cost"] = d["Exposed"] * EXPOSED_RATE * d["Unit_Cost"]
    d["Site"] = d["Product"] + ", " + d["Warehouse"]
    return d


# ------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### Data source")
    mode = st.radio("Mode", ["Live simulation", "Google Sheet or CSV"], label_visibility="collapsed")
    url, interval, paused = "", 5, False
    if mode == "Live simulation":
        interval = st.select_slider("Seconds per simulated day", [3, 5, 10, 20], value=5)
        paused = st.checkbox("Pause")
        c1, c2 = st.columns(2)
        spike = c1.button("Demand spike")
        reset = c2.button("Reset")
    else:
        try:
            default_url = st.secrets.get("SHEET_CSV_URL", "")
        except Exception:
            default_url = ""
        url = st.text_input("CSV link", default_url, help="Google Sheets: File, Share, Publish to web, choose CSV.")
        interval = st.select_slider("Refresh every (seconds)", [10, 15, 30, 60], value=15)
        spike = reset = False

try:
    base = load_source(url)
except Exception as e:
    st.error(f"Could not load data. {e}")
    st.stop()

if mode == "Live simulation" and ("sim" not in st.session_state or reset or len(st.session_state.sim["stock"]) != len(base)):
    init_sim(base)
if mode == "Live simulation" and spike:
    st.session_state.sim["spike"] = 3
    st.session_state.sim["log"].insert(0, "Demand spike: demand doubles for the next 3 days.")
if "hist" not in st.session_state:
    st.session_state.hist = []

with st.sidebar:
    st.markdown("### Filters")
    prods, whs = sorted(base["Product"].unique()), sorted(base["Warehouse"].unique())
    sel_p = st.multiselect("Products", prods, default=prods)
    sel_w = st.multiselect("Warehouses", whs, default=whs)
    st.markdown("### What-if scenario")
    surge = st.slider("Demand change (%)", -30, 100, 0, 5)
    delay = st.slider("Supplier delay (days)", 0, 10, 0)


def style(fig, h):
    fig.update_layout(height=h, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT, color=INK))
    return fig


# ------------------------------------------------------------ dashboard
def dashboard():
    d = base.copy()
    stamp = datetime.now().strftime("%H:%M:%S")
    if mode == "Live simulation":
        sim = st.session_state.sim
        if not paused and time.time() - sim["last"] >= interval * 0.9:
            tick(base, sim)
            sim["last"] = time.time()
        d["Current_Stock"] = sim["stock"]
        badge = f"Live simulation, day {sim['day']}, updated {stamp}"
    else:
        badge = f"Connected to {'your sheet' if url else 'powerbi_final.csv'}, refreshed {stamp}"

    full = simulate(d, surge, delay)
    snap = (int(full["Short"].sum()), int((full["Short"] > 0).sum()))
    label = f"Day {st.session_state.sim['day']}" if mode == "Live simulation" else stamp
    if not st.session_state.hist or st.session_state.hist[-1][1:] != snap:
        st.session_state.hist.append((label, *snap))
    del st.session_state.hist[:-60]

    df = full[full["Product"].isin(sel_p) & full["Warehouse"].isin(sel_w)]
    st.markdown(f'<p class="brand">Supply Chain Control Tower<small>Which stock runs out before resupply arrives, and what rescues it</small></p>'
                f'<span class="live">{badge}</span>', unsafe_allow_html=True)
    if df.empty:
        st.warning("No stock positions match these filters. Select at least one product and one warehouse.")
        return

    at_risk = df[df["Short"] > 0]
    short, covered, exposed = df["Short"].sum(), df["Covered"].sum(), df["Exposed"].sum()
    if at_risk.empty:
        colour, head, sub = TEAL, "Every position lasts until resupply arrives.", "No rescue action is needed right now."
    else:
        colour = RED if exposed > 0 else AMBER
        head = f"{len(at_risk)} of {len(df)} stock positions run out before resupply arrives."
        sub = f"Rescue covers {covered:,.0f} of {short:,.0f} short units. " + (
            f"{exposed:,.0f} units stay exposed." if exposed else "Nothing stays exposed.")
    st.markdown(f'<div class="status" style="--c:{colour}"><h2>{head}</h2><p>{sub}</p></div>', unsafe_allow_html=True)
    st.markdown(f"""<div class="band">
<div><span>Inventory value</span><b>{inr(df['Inventory_Value'].sum())}</b><em>{df['Current_Stock'].sum():,.0f} units on hand</em></div>
<div><span>Positions at risk</span><b>{len(at_risk)} / {len(df)}</b><em>cover below 1.0x lead time</em></div>
<div><span>Units short</span><b>{short:,.0f}</b><em>before any rescue</em></div>
<div><span>Covered by transfer</span><b>{(covered / short * 100 if short else 100):.0f}%</b><em>{exposed:,.0f} units exposed</em></div>
<div><span>Rescue cost</span><b>{inr(df['Rescue_Cost'].sum())}</b><em>{inr(df['Business_Cost'].sum())} business cost</em></div>
</div>""", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["Stock runway", "Rescue plan", "Activity", "Data"])

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
            st.info("Nothing to rescue right now. Use the demand spike or the what-if sliders to test the network.")
        for _, x in at_risk.sort_values("Exposed", ascending=False).iterrows():
            pct = x["Covered"] / x["Short"] * 100
            action = "Warehouse transfer" if x["Covered"] > 0 else "No spare stock to transfer"
            st.markdown(f"""<div class="plan">
<h4>{x['Product']}, {x['Warehouse']}</h4>
<p class="meta">Stock lasts {x['Days']:.1f} days. Resupply takes {x['Lead']:.0f}.</p>
<div class="track"><i style="width:{pct:.0f}%"></i></div>
<div class="row">
<div><span>Short</span><b>{x['Short']:,.0f} units</b></div>
<div><span>Covered</span><b>{x['Covered']:,.0f} units ({pct:.0f}%)</b></div>
<div><span>Still exposed</span><b>{x['Exposed']:,.0f} units</b></div>
<div><span>Action</span><b>{action}</b></div>
<div><span>Delivery</span><b>{f"{TRANSFER_DAYS} day" if x['Covered'] > 0 else "n/a"}</b></div>
<div><span>Rescue cost</span><b>{inr(x['Rescue_Cost'])}</b></div>
<div><span>Business cost</span><b>{inr(x['Business_Cost'])}</b></div>
</div></div>""", unsafe_allow_html=True)

    with tab3:
        a, b = st.columns([3, 2], gap="large")
        with a:
            st.subheader("Units short over time")
            h = pd.DataFrame(st.session_state.hist, columns=["t", "short", "risk"])
            lf = go.Figure(go.Scatter(x=h["t"], y=h["short"], mode="lines+markers", line=dict(color=RED, width=3, shape="hv"),
                                      marker=dict(size=6), hovertemplate="%{x}<br>%{y} units short<extra></extra>"))
            lf.update_yaxes(title="Units short", gridcolor=LINE, rangemode="tozero")
            st.plotly_chart(style(lf, 300), use_container_width=True)
        with b:
            st.subheader("Supplier orders" if mode != "Live simulation" else "Activity feed")
            if mode == "Live simulation":
                events = st.session_state.sim["log"][:8]
            elif "Order_Status" in df.columns:
                sent = df[df["Order_Status"].str.upper() == "ORDERED"]
                events = [f"{x.Site}: ordered {x.Order_Qty:,.0f} units, sent {x.Order_Time[:16]}." for x in sent.itertuples()]
            else:
                events = []
            if events:
                st.markdown('<div class="feed">' + "".join(f"<p>{e}</p>" for e in events) + "</div>", unsafe_allow_html=True)
            else:
                st.caption("Orders and deliveries appear here in simulation mode." if mode == "Live simulation"
                           else "No open supplier orders. When stock drops below demand during lead time, the sheet script emails the supplier and the order appears here.")

    with tab4:
        show = df[["Product", "Warehouse", "Current_Stock", "Days", "Lead", "Cover", "Short", "Covered", "Exposed", "Inventory_Value", "Rescue_Cost"]]
        st.dataframe(show, use_container_width=True, hide_index=True, column_config={
            "Current_Stock": "Stock", "Days": st.column_config.NumberColumn("Days of stock", format="%.1f"),
            "Lead": st.column_config.NumberColumn("Resupply days", format="%.0f"),
            "Cover": st.column_config.ProgressColumn("Cover (x lead time)", min_value=0, max_value=2, format="%.2f"),
            "Short": "Units short", "Covered": "Units covered", "Exposed": "Units exposed",
            "Inventory_Value": st.column_config.NumberColumn("Inventory value", format="₹%d"),
            "Rescue_Cost": st.column_config.NumberColumn("Rescue cost", format="₹%d")})
        st.download_button("Download this view (CSV)", show.to_csv(index=False).encode("utf-8"), "supply_chain_view.csv", "text/csv")

    st.caption("Prototype decision support. Simulation mode generates synthetic movements. Sheet mode shows whatever the linked sheet contains.")


auto = None if (mode == "Live simulation" and paused) else interval
st.fragment(run_every=auto)(dashboard)()
