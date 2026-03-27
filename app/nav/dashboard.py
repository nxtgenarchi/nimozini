import streamlit as st
import pandas as pd
import altair as alt
from nav import notes, journal
from utils import ml
from supabase import create_client, Client
import os

# Supabase setup
SUPABASE_URL: str = st.secrets["SUPABASE_URL"]
SUPABASE_KEY: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def show_page():
    st.title("Dashboard")
    st.header("Overview")
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

    view = st.radio("View", ("daily", "weekly"), index=0)

    #Notes and Journal
    blocks = supabase.table("noteblocks").select("*").order("id", desc=False).execute().data
    df = pd.DataFrame(blocks)
    df = _ensure_created_at(df)
    df = df[df["created_at"].notna()]
    
    if "block_type" not in df.columns and "btype" in df.columns:
        df["block_type"] = df["btype"]
    df["block_type"] = df["block_type"].fillna("Unknown").astype(str)
    df["subject"] = df["subject"].fillna("Unknown").astype(str)
    df["hour"] = df["created_at"].dt.hour
    
    if view == "daily":
        daily_chart = alt.Chart(df).mark_bar().encode(
            x=alt.X('hour:O', title='Hour of Day'),
            y=alt.Y('count():Q', title='Number of Blocks'),
            color=alt.Color('block_type:N', title='Block Type'),
            column=alt.Column('subject:N', title='Subject', spacing=10),
            tooltip=['subject', 'block_type', 'count()']
        ).properties(width=80, height=400, title="Blocks per Subject by Hour (Daily)").interactive()
        st.altair_chart(daily_chart, use_container_width=True)

        df['period'] = df['created_at'].dt.date
    else:
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

        df['period'] = df['created_at'].dt.to_period('W').astype(str)
    
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
    
    if view == "daily":
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

    # ML Recommender
    st.header("Recommendations")
    def get_recommendations():
        # Force retrain by deleting old files
        if os.path.exists(ml.MODEL_PATH):
            os.remove(ml.MODEL_PATH)
        if os.path.exists(ml.STATE_PATH):
            os.remove(ml.STATE_PATH)
        items = ml.load_items_from_sources()
        if items.empty:
            return {"subjects": [], "methods": {}, "message": "No note or journal items found."}

        interactions = ml.load_interactions()
        if interactions.empty or len(interactions) < 5:
            subject_counts = items["subject"].fillna("Unknown").astype(str).value_counts()
            top_subjects = list(subject_counts.head(3).items())
            methods = {}
            for subj in [s for s, _ in top_subjects]:
                block_types = items[items["subject"].fillna("Unknown").astype(str) == subj]["block_type"].fillna("Unknown").astype(str).value_counts()
                methods[subj] = list(zip(block_types.index.tolist()[:3], block_types.values.tolist()[:3]))
            return {"subjects": top_subjects, "methods": methods, "message": "Not enough interaction data: fallback to frequency-based recommendations."}

        # Load saved state for consistent feature transformation
        saved_state = ml.load_state()
        if saved_state is not None:
            X_items, _, items_df = ml.build_feature_matrices(items, state=saved_state)
            state = saved_state  # Use saved state for recommendations
        else:
            X_items, state, items_df = ml.build_feature_matrices(items)
            ml.save_state(state)  # Save for future use
        X, y, timestamps, merged = ml.build_interaction_dataset(items_df, interactions, X_items)
        model = ml.load_model()

        if model is None and X is not None and y is not None and len(y) > 0:
            model, stats = ml.train_lightgbm_classifier(X, y, timestamps)
            if model is not None:
                ml.save_model(model)

        if model is None:
            return {"subjects": [], "methods": {}, "message": "Model unavailable; try collecting more interactions."}

        recs = ml.recommend_categories_from_model(model, X_items, items_df, state, user_context_texts=[])
        recs["message"] = "Model-based recommendations"
        return recs

    if st.button("Show Recommendations"):
        st.session_state["rec"] = True

    if st.session_state.get("rec"):
        recs = get_recommendations()
        if not recs or not recs.get("subjects"):
            st.info("No recommendations available right now. Add more notes/journal entries and interactions first.")
        else:
            subjects_list = [f"{subj} ({score:.2f})" if isinstance(score, (int, float)) else str(subj) for subj, score in recs["subjects"]]
            methods_list = []
            for subj, methods in recs.get("methods", {}).items():
                for method, mscore in methods:
                    methods_list.append(f"{method} ({mscore:.2f})")

            st.write(f"You should probably study: {', '.join([s.split(' (')[0] for s in subjects_list])}.")
            if methods_list:
                st.write(f"Suggested study methods: {', '.join([m.split(' (')[0] for m in methods_list])}.")

            st.subheader("Subject ranking")
            for subject, score in recs["subjects"]:
                st.write(f"• {subject}: {score:.2f}" if isinstance(score, (int, float)) else f"• {subject}")

            st.subheader("Method ranking by subject")
            for subject, methods in recs.get("methods", {}).items():
                if not methods:
                    continue
                with st.expander(subject):
                    for method, mscore in methods:
                        st.write(f"• {method}: {mscore:.2f}")

            st.caption(recs.get("message", ""))