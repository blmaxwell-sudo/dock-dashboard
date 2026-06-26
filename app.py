import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO

st.set_page_config(layout="wide")
st.title("🚛 Dock Optimization Dashboard")

# -----------------------------
# FILE UPLOAD
# -----------------------------
book_file = st.file_uploader("Upload Book1.xlsx", type=["xlsx"])
short_file = st.file_uploader("Upload Short Sheet.xlsx", type=["xlsx"])

if book_file and short_file:

    # =============================
    # LOAD BOOK1
    # =============================
    df = pd.read_excel(book_file)
    df = df.iloc[2:].reset_index(drop=True)
    df = df.iloc[:, 4:]

    df.columns = [
        "ColE","ColF","ColG","ColH","ColI",
        "ColJ","ColK","ColL",
        "Date1","Time1","Date2","Time2","User","ExtraDate"
    ]

    df["ColE"] = df["ColE"].astype(str).str.replace("L","",regex=False)
    df["ColE"] = pd.to_numeric(df["ColE"],errors="coerce").fillna(0).astype(int)
    df["ColF"] = pd.to_numeric(df["ColF"],errors="coerce").fillna(0).astype(int)
    df["ColG"] = pd.to_numeric(df["ColG"],errors="coerce").fillna(0).astype(int)

    df["Trailer"] = df["ColE"].astype(str)+df["ColF"].astype(str)+df["ColG"].astype(str)

    df["SKU"] = df["ColJ"].astype(str).str.strip()+df["ColK"].astype(str).str.strip()

    clean_df = df[["Trailer","SKU","ColL"]].copy()
    clean_df.columns = ["Trailer","SKU","Quantity"]
    clean_df["Quantity"] = pd.to_numeric(clean_df["Quantity"],errors="coerce")
    clean_df = clean_df.dropna()

    # =============================
    # LOAD SHORT SHEET
    # =============================
    short_df = pd.read_excel(short_file)
    short_df = short_df.iloc[6:].reset_index(drop=True)

    short_df.columns = [
        "Trip","Destination","Dispatch","Status","Order",
        "Item","Description","Cases","W","ProdETA","Comments"
    ]

    short_clean = short_df[["Trip","Dispatch","Item","Cases"]].copy()
    short_clean["Item"] = short_clean["Item"].astype(str).str.strip()
    short_clean["Cases"] = pd.to_numeric(short_clean["Cases"],errors="coerce")
    short_clean["Dispatch"] = pd.to_numeric(short_clean["Dispatch"],errors="coerce")
    short_clean = short_clean.dropna()

    # =============================
    # MATCH
    # =============================
    match_df = short_clean.merge(clean_df,left_on="Item",right_on="SKU",how="left")

    # =============================
    # TRAILER PRIORITY
    # =============================
    trailer_priority = match_df.groupby("Trailer").agg(
        Demand_Served=("Cases","sum"),
        SKU_Count=("Item","nunique")
    ).reset_index()

    trailer_priority = trailer_priority.sort_values(
        by="Demand_Served",ascending=False
    ).reset_index(drop=True)

    trailer_priority["Wave"] = (trailer_priority.index // 4)+1
    trailer_priority["Priority_Score"] = (
        trailer_priority["Demand_Served"]/trailer_priority["SKU_Count"]
    ).round(0)

    # Move Wave first
    cols = ["Wave"]+[c for c in trailer_priority.columns if c!="Wave"]
    dock_plan = trailer_priority[cols]

    # =============================
    # LOAD COVERAGE
    # =============================
    match_with_wave = match_df.merge(
        dock_plan[["Trailer","Wave"]],
        on="Trailer",how="left"
    )

    load = match_with_wave.groupby(
        ["Wave","Trailer","Trip","Item"]
    ).agg(
        Demand_Cases=("Cases","sum"),
        Available_Cases=("Quantity","sum")
    ).reset_index()

    load["Fill_Rate"] = (
        load["Available_Cases"]/load["Demand_Cases"]
    ).replace([np.inf,-np.inf],0).fillna(0)

    load["Fill_Rate"] = load["Fill_Rate"].round(2)

    # Status
    def status(x):
        if x>=1: return "Full ✅"
        elif x>0: return "Partial ⚠️"
        else: return "Short ❌"

    load["Status"] = load["Fill_Rate"].apply(status)

    # =============================
    # EXCEPTIONS
    # =============================
    exceptions = load[load["Status"]!="Full ✅"]

    # =============================
    # OPTIMIZED TRAILERS
    # =============================
    fix_df = load[load["Status"]!="Full ✅"]

    optimized = fix_df.groupby("Trailer").agg(
        Fix_Cases=("Available_Cases","sum"),
        Loads=("Trip","nunique")
    ).reset_index().sort_values(
        by="Fix_Cases",ascending=False
    )

    top5 = optimized.head(5).copy()

    # =============================
    # DASHBOARD
    # =============================
    st.subheader("🚛 Dock Plan")
    st.dataframe(dock_plan)

    st.subheader("📊 Dashboard")

    col1, col2 = st.columns(2)

    with col1:
        fig1 = px.bar(
            dock_plan.head(15),
            x="Trailer",
            y="Demand_Served",
            color="Wave",
            title="Top Trailers"
        )
        st.plotly_chart(fig1,use_container_width=True)

    with col2:
        status_count = load.groupby("Status").size().reset_index(name="Count")
        fig2 = px.pie(status_count,names="Status",values="Count",title="Load Status")
        st.plotly_chart(fig2,use_container_width=True)

    # =============================
    # TRUE SHORTAGE DRIVERS
    # =============================
    load["Shortage"] = load["Demand_Cases"]-load["Available_Cases"]
    short = load[load["Shortage"]>0]

    sku_short = short.groupby("Item")["Shortage"].sum().reset_index()
    sku_short = sku_short.sort_values(by="Shortage",ascending=False).head(10)

    fig3 = px.bar(sku_short,x="Item",y="Shortage",title="Top Shortages")
    st.plotly_chart(fig3,use_container_width=True)

    st.subheader("🟢 Top 5 Trailers")
    st.dataframe(top5)

    st.subheader("🚨 Exception Report")
    st.dataframe(exceptions)

    # =============================
    # DOWNLOAD EXCEL
    # =============================
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        dock_plan.to_excel(writer, sheet_name="Dock Plan", index=False)
        load.to_excel(writer, sheet_name="Load Coverage", index=False)
        exceptions.to_excel(writer, sheet_name="Exceptions", index=False)
        optimized.to_excel(writer, sheet_name="Optimized", index=False)
        top5.to_excel(writer, sheet_name="Top5", index=False)

    st.download_button(
        label="📥 Download Excel",
        data=output.getvalue(),
        file_name="Dock_Output.xlsx"
    )
``
