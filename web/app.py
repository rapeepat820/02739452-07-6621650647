"""Dashboard ราคาหนังสือ — อ่านข้อมูลจาก PostgreSQL โดยตรง (ไม่ผ่านไฟล์ใดๆ)"""
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="เปรียบเทียบราคาหนังสือคอมพิวเตอร์", page_icon="📚", layout="wide")

DSN = os.environ["DATA_DB_DSN"].replace("postgresql://", "postgresql+psycopg2://", 1)


@st.cache_resource
def engine():
    return create_engine(DSN, pool_pre_ping=True)


@st.cache_data(ttl=20)
def q(sql: str) -> pd.DataFrame:
    with engine().connect() as conn:
        return pd.read_sql(text(sql), conn)


SOURCE_LABEL = {"b2s": "B2S", "seed": "Se-ed", "naiin": "Naiin"}

try:
    prices = q("SELECT * FROM book_prices")
    unique = q("SELECT * FROM books_unique")
except Exception as e:  # ตารางยังไม่ถูกสร้าง / DB ยังไม่พร้อม
    st.title("📚 เปรียบเทียบราคาหนังสือคอมพิวเตอร์")
    st.warning("ยังอ่านข้อมูลไม่ได้ — เปิด Airflow (พอร์ต 8080) แล้ว Trigger DAG `book_price_pipeline` ก่อน")
    st.caption(f"รายละเอียด: {type(e).__name__}")
    st.stop()

prices["source_name"] = prices["source"].map(SOURCE_LABEL).fillna(prices["source"])

tab_dash, tab_compare, tab_status = st.tabs(["📊 ภาพรวม", "🔍 เปรียบเทียบข้ามร้าน", "🛠 สถานะ pipeline"])

# ------------------------------------------------------------------ ภาพรวม
with tab_dash:
    st.title("📚 ราคาหนังสือคอมพิวเตอร์/โปรแกรมมิ่ง จากหลายร้าน")
    if prices.empty:
        st.info("ยังไม่มีข้อมูลในตาราง book_prices")
        st.stop()

    with st.sidebar:
        st.header("ตัวกรอง")
        sources = st.multiselect("ร้าน", sorted(prices["source_name"].unique()),
                                 default=sorted(prices["source_name"].unique()))
        pubs = st.multiselect("สำนักพิมพ์", sorted(prices["publisher"].dropna().unique()))
        lo, hi = float(prices["price"].min()), float(prices["price"].max())
        price_range = st.slider("ช่วงราคา (บาท)", lo, hi, (lo, hi)) if lo < hi else (lo, hi)
        in_stock_only = st.checkbox("เฉพาะที่มีของ", value=False)
        kw = st.text_input("ค้นหาชื่อหนังสือ / ISBN")

    f = prices[prices["source_name"].isin(sources)]
    f = f[(f["price"] >= price_range[0]) & (f["price"] <= price_range[1])]
    if pubs:
        f = f[f["publisher"].isin(pubs)]
    if in_stock_only:
        f = f[f["in_stock"] == True]  # noqa: E712 (NULL ถือว่าไม่ทราบ จึงไม่นับ)
    if kw:
        f = f[f["title"].str.contains(kw, case=False, na=False) | f["isbn"].str.contains(kw, na=False)]

    discount = (1 - f["price"] / f["list_price"]).where(f["list_price"] > 0)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("รายการ (เล่ม×ร้าน)", f"{len(f):,}")
    c2.metric("ISBN ไม่ซ้ำ", f"{f['isbn'].nunique():,}")
    c3.metric("ราคาเฉลี่ย", f"{f['price'].mean():,.0f} ฿" if len(f) else "-")
    c4.metric("ส่วนลดเฉลี่ย", f"{discount.mean():.0%}" if discount.notna().any() else "-")
    c5.metric("จำนวนร้าน", f"{f['source'].nunique()}")

    left, right = st.columns(2)
    if len(f):
        avg = f.groupby("source_name", as_index=False)["price"].mean().round(2)
        left.plotly_chart(px.bar(avg, x="source_name", y="price", text="price", title="ราคาเฉลี่ยแยกตามร้าน",
                                 labels={"source_name": "ร้าน", "price": "ราคาเฉลี่ย (บาท)"}),
                          width="stretch")
        right.plotly_chart(px.histogram(f, x="price", color="source_name", nbins=25, barmode="overlay",
                                        opacity=0.7, title="การกระจายราคา",
                                        labels={"price": "ราคา (บาท)", "source_name": "ร้าน"}),
                           width="stretch")
    st.subheader("ตารางข้อมูล")
    show = f[["isbn", "title", "publisher", "source_name", "price", "list_price", "in_stock", "url", "scraped_at"]]
    st.dataframe(show.sort_values("title"), width="stretch", hide_index=True,
                 column_config={"url": st.column_config.LinkColumn("ลิงก์", display_text="เปิด"),
                                "price": st.column_config.NumberColumn("ราคา", format="%.2f"),
                                "list_price": st.column_config.NumberColumn("ราคาปก", format="%.2f"),
                                "source_name": "ร้าน"})

# ------------------------------------------------------------------ เปรียบเทียบ
with tab_compare:
    st.subheader("หนังสือเล่มเดียวกันที่ขายหลายร้าน (จับคู่ด้วย ISBN)")
    multi = unique[unique["n_sources"] >= 2].sort_values("price_spread", ascending=False)
    a, b, c = st.columns(3)
    a.metric("ISBN ที่ขายอย่างน้อย 2 ร้าน", f"{len(multi):,}")
    b.metric("ส่วนต่างราคาเฉลี่ย", f"{multi['price_spread'].mean():,.0f} ฿" if len(multi) else "-")
    if len(multi):
        win = multi["cheapest_source"].map(SOURCE_LABEL).fillna(multi["cheapest_source"]).value_counts()
        c.metric("ร้านที่ถูกสุดบ่อยที่สุด", f"{win.index[0]} ({win.iloc[0]} เล่ม)")
        top = multi.head(15).copy()
        top["label"] = top["title"].str.slice(0, 40)
        st.plotly_chart(px.bar(top, x="price_spread", y="label", orientation="h",
                               title="15 เล่มที่ราคาต่างกันมากที่สุดระหว่างร้าน",
                               labels={"price_spread": "ส่วนต่าง (บาท)", "label": ""}).update_yaxes(autorange="reversed"),
                        width="stretch")
        pivot = prices.pivot_table(index=["isbn", "title"], columns="source_name", values="price", aggfunc="min").reset_index()
        pivot = pivot[pivot["isbn"].isin(multi["isbn"])]
        st.dataframe(pivot, width="stretch", hide_index=True)
    else:
        st.info("ยังไม่มี ISBN ที่ซ้ำข้ามร้าน (ต้องมีข้อมูลอย่างน้อย 2 แหล่ง)")

# ------------------------------------------------------------------ สถานะ pipeline (โบนัส)
with tab_status:
    st.subheader("สถานะ pipeline")
    runs = q("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 20")
    if runs.empty:
        st.info("ยังไม่เคยรัน")
    else:
        last = runs.iloc[0]
        n = lambda v: 0 if pd.isna(v) else int(v)  # noqa: E731  (pandas แปลงจำนวนเต็มที่มี NULL เป็น float)
        icon = {"success": "✅", "partial_success": "⚠️", "quarantined": "🚧", "failed": "❌", "running": "⏳"}.get(last["status"], "•")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("รอบล่าสุด", f"{icon} {last['status']}")
        c2.metric("แหล่งที่สำเร็จ", ", ".join(last["sources_ok"] or []) or "-")
        c3.metric("แหล่งที่ล่ม", ", ".join(last["sources_failed"] or []) or "ไม่มี")
        c4.metric("แถวเข้าตารางหลัก / ถูกปฏิเสธ", f"{n(last['rows_loaded'])} / {n(last['rows_rejected'])}")
        if last["note"]:
            st.caption(last["note"])
        st.dataframe(runs, width="stretch", hide_index=True)
    st.subheader("แถวที่ไม่ผ่านการตรวจคุณภาพ (ล่าสุด 50 แถว)")
    st.dataframe(q("SELECT run_id, source, isbn_raw, title, price, reason, rejected_at FROM rejected_rows "
                   "ORDER BY id DESC LIMIT 50"), width="stretch", hide_index=True)
