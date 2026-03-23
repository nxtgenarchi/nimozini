import streamlit as st
import pandas as pd
import altair as alt
from nav import notes, journal
from utils import ml
from supabase import create_client, Client

# Supabase setup
SUPABASE_URL: str = st.secrets["SUPABASE_URL"]
SUPABASE_KEY: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def show_page():
    st.title("Dashboard")
    def _ensure_created_at(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            df = df.copy()
            df["created_at"] = pd.NaT
            return df
        if "created_at" not in df.columns:
            df = df.copy()
            df["created_at"] = pd.NaT
            return df
        df = df.copy()
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        return df

    view = st.radio("Journal view", ("daily", "weekly"), index=0)

    #Notes
    blocks = supabase.table("noteblocks").select("*").order("id", desc=False).execute().data
    df = pd.DataFrame(blocks)
    df = _ensure_created_at(df)
    df = df[df["created_at"].notna()]
    if df.empty:
        st.warning("No note blocks with valid created_at timestamps were found for dashboard charts.")
    else:
        # Supabase note blocks use `btype` in create_block; dashboard charts expect `block_type`.
        if "block_type" not in df.columns and "btype" in df.columns:
            df["block_type"] = df["btype"]
        df["block_type"] = df.get("block_type", "Unknown").fillna("Unknown")
        df["subject"] = df.get("subject", "Unknown").fillna("Unknown")
        df["hour"] = df["created_at"].dt.hour

        daily_chart = alt.Chart(df).mark_bar().encode(
            x=alt.X('hour:O', title='Hour of Day'),
            y=alt.Y('count():Q', title='Number of Blocks'),
            color=alt.Color('block_type:N', title='Block Type'),
            column=alt.Column('subject:N', title='Subject', spacing=10),
            tooltip=['subject', 'block_type', 'count()']
        ).properties(width=80, height=400, title="Blocks per Subject by Hour (Daily)").interactive()
        st.altair_chart(daily_chart, use_container_width=True)

        df['weekday'] = df['created_at'].dt.day_name()
        days_order = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        df['weekday'] = pd.Categorical(df['weekday'], categories=days_order, ordered=True)

        weekly_chart = alt.Chart(df).mark_bar().encode(
            x=alt.X('weekday:N', sort=days_order, title='Day of Week'),
            y=alt.Y('count():Q', title='Number of Blocks'),
            color=alt.Color('block_type:N', title='Block Type'),
            column=alt.Column('subject:N', title='Subject', spacing=10), 
            tooltip=['subject', 'block_type', 'count()']
        ).properties(width=80, height=400, title="Blocks per Subject by Day (Weekly)").interactive()
        st.altair_chart(weekly_chart, use_container_width=True)
    
    #Journal
    def get_top_emotions(df, time_col):
        emotion_counts = df.groupby([time_col, 'emotion']).size().reset_index(name='count')
        top_emotions = []
        for time_val, group in emotion_counts.groupby(time_col):
            group_sorted = group.sort_values('count', ascending=False)
            top3 = group_sorted.head(3)
            others = group_sorted.iloc[3:]
            for _, row in top3.iterrows():
                top_emotions.append({time_col: time_val, 'emotion': row['emotion'], 'count': row['count']})
            if not others.empty:
                others_count = others['count'].sum()
                top_emotions.append({time_col: time_val, 'emotion': 'Others', 'count': others_count})
        return pd.DataFrame(top_emotions)
    entries = journal.get_entries()
    df = pd.DataFrame(entries)
    df = _ensure_created_at(df)
    df = df[df['created_at'].notna()]
    if df.empty:
        st.warning("No journal entries with valid created_at timestamps were found for emotion analysis.")
        return

    if view == 'daily':
        df['period'] = df['created_at'].dt.date
    else:
        df['period'] = df['created_at'].dt.to_period('W').astype(str)
    period_options = df['period'].unique()
    selected_period = st.selectbox(f"Select {'day' if view=='daily' else 'week'}", period_options)
    period_df = df[df['period'] == selected_period]
    donut_df = get_top_emotions(period_df, 'period')
    if donut_df.empty:
        st.warning("No emotion data for selected period.")
        return
    chart = alt.Chart(donut_df).mark_arc(innerRadius=50).encode(
        theta=alt.Theta(field="count", type="quantitative"),
        color=alt.Color(field="emotion", type="nominal"),
        tooltip=["emotion", "count"]
    ).properties(
        width=400,
        height=400,
        title=f"Top 3 Emotions ({selected_period})"
    )
    st.altair_chart(chart, use_container_width=True)

    #ML Recommender
