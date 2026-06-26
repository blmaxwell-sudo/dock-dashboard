import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🚛 Dock Door Optimization Dashboard")

# -----------------------------
# FILE UPLOAD
# -----------------------------
book_file = st.file_uploader("Upload Book1.xlsx", type=["xlsx"])
short_file = st.file_uploader("Upload Short Sheet.xlsx", type=["xlsx"])

if book_file and short_file:

    # =============================
    # LOAD & CLEAN BOOK1
    # =============================
    df = pd.read_excel(book_file)

    df = df.iloc[2:].reset_index(drop=True)
    df = df.iloc[:, 4:]

    df.columns = [
        "ColE","ColF","ColG","ColH","ColI",
        "ColJ","ColK","ColL",
        "Date1","Time1","Date2","Time2","User","ExtraDate"
    ]

    # Fix trailer number
    df["ColE"] = df["ColE"].astype(str).str.replace("L", "", regex=False)
    df["ColE"] = pd.to_numeric(df["ColE"], errors="coerce").fillna(0).astype(int)
    df["ColF"] = pd.to_numeric(df["ColF"], errors="coerce").fillna(0).astype(int)
    df["ColG"] = pd.to_numeric(df["ColG"], errors="coerce").fillna(0).astype(int)

    df["Trailer"] = (
        df["ColE"].astype(str) +
        df["ColF"].astype(str) +
        df["ColG"].astype(str)
    )

    # SKU (KEEP COMBINED)
    df["SKU"] = df["ColJ"].astype(str).str.strip() + df["ColK"].astype(str).str.strip()

    clean_df = df[["Trailer","ColH","ColI","SKU","ColL"]].copy()
    clean_df.columns = ["Trailer","LPN","Description","SKU","Quantity"]

    clean_df["Quantity"] = pd.to_numeric(clean_df["Quantity"], errors="coerce")
    clean_df = clean_df.dropna(subset=["SKU","Quantity"])

    # =============================
    # LOAD & CLEAN SHORT SHEET
    # =============================
    short_df = pd.read_excel(short_file)
    short_df = short_df.iloc[6:].reset_index(drop=True)

    short_df.columns = [
        "Trip","Destination","Dispatch","Status","Order",
        "Item","Description","Cases","W","ProdETA","Comments"
    ]

    short_clean = short_df[["Dispatch","Item","Cases"]].copy()

    short_clean["Item"] = short_clean["Item"].astype(str).str.strip()
    short_clean["Cases"] = pd.to_numeric(short_clean["Cases"], errors="coerce")
    short_clean["Dispatch"] = pd.to_numeric(short_clean["Dispatch"], errors="coerce")

    short_clean = short_clean.dropna(subset=["Item","Cases"])

    # =============================
    # MATCH ITEMS TO TRAILERS
    # =============================
    match_df = short_clean.merge(
        clean_df,
        left_on="Item",
        right_on="SKU",
        how="left"
    )

    item_trailer = match_df.groupby(["Item","Trailer"]).agg(
        Demand_Cases=("Cases","sum"),
        Available_Cases=("Quantity","sum")
    ).reset_index()

    # =============================
    # TRAILER PRIORITY LOGIC
    # =============================
    dispatch_lookup = short_clean.groupby("Item", as_index=False)["Dispatch"].min()
    dispatch_lookup = dispatch_lookup.rename(columns={"Dispatch": "Item_Dispatch"})

    match_with_dispatch = match_df.merge(dispatch_lookup, on="Item", how="left")

    trailer_priority = match_with_dispatch.groupby("Trailer").agg(
        Urgency=("Item_Dispatch","min"),
        Demand_Served=("Cases","sum"),
        SKU_Count=("Item","nunique")
    ).reset_index()

    # Score
    trailer_priority["Priority_Score"] = (
        trailer_priority["Demand_Served"] / trailer_priority["SKU_Count"]
    )

    # Sort (MOST IMPORTANT LOGIC)
    trailer_priority = trailer_priority.sort_values(
        by=["Urgency","Priority_Score"],
        ascending=[True, False]
    ).reset_index(drop=True)

    # Dock waves (4 trailers/hour)
    trailer_priority["Wave"] = (trailer_priority.index // 4) + 1

    # =============================
    # DASHBOARD DISPLAY
    # =============================
    st.subheader("🚛 Trailer Priority (Dock Plan)")
    st.dataframe(trailer_priority, use_container_width=True)

    # -----------------------------
    # BAR CHART
    # -----------------------------
    fig = px.bar(
        trailer_priority.head(15),
        x="Trailer",
        y="Demand_Served",
        color="Urgency",
        title="Top Trailers by Demand",
        text="Demand_Served"
    )
    st.plotly_chart(fig, use_container_width=True)

    # -----------------------------
    # WAVE CHART
    # -----------------------------
    fig2 = px.scatter(
        trailer_priority,
        x="Urgency",
        y="Demand_Served",
        size="SKU_Count",
        color="Wave",
        hover_data=["Trailer"],
        title="Dock Wave Plan (4 Trailers Per Hour)"
    )
    st.plotly_chart(fig2, use_container_width=True)

    # =============================
    # ITEM COVERAGE
    # =============================
    st.subheader("📦 Item → Trailer Coverage")
    st.dataframe(
        item_trailer.sort_values(by="Demand_Cases", ascending=False),
        use_container_width=True
    )

    # =============================
    # PRINTABLE DOCK PLAN
    # =============================
    st.subheader("🖨️ Printable Dock Plan")

    printable = trailer_priority[[
        "Trailer","Wave","Urgency","Demand_Served","SKU_Count"
    ]].copy()

    st.dataframe(printable, use_container_width=True)

    # Download
    file_name = "Dock_Plan.xlsx"
    printable.to_excel(file_name, index=False)

    with open(file_name, "rb") as f:
        st.download_button(
            label="📥 Download Dock Plan",
            data=f,
            file_name="Dock_Plan.xlsx"
        )