from nav import notes, journal
import os
import pickle
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client, Client
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from scipy.sparse import hstack, csr_matrix
import lightgbm as lgb

# Supabase wiring (uses streamlit secrets)
SUPABASE_URL: str = st.secrets["SUPABASE_URL"]
SUPABASE_KEY: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Persistence paths
STATE_DIR = os.path.dirname(__file__)
STATE_PATH = os.path.join(STATE_DIR, "recommender_state.pkl")
MODEL_PATH = os.path.join(STATE_DIR, "recommender_model.pkl")


# -------------------------
# Data loading / normalization
# -------------------------
def load_items_from_sources() -> pd.DataFrame:
    """
    Load items from notes.get_blocks() and journal.get_entries().
    Normalizes to columns: id, title, text, subject, block_type, created_at, item_type
    """
    note_items = supabase.table("noteblocks").select("*").order("id", desc=False).execute().data or []
    journal_items = journal.get_entries() or []

    # normalize notes
    notes_df = pd.DataFrame(note_items)
    if not notes_df.empty:
        notes_df = notes_df.rename(columns={"content": "text", "name": "title"})
        notes_df["item_type"] = "note"
    else:
        notes_df = pd.DataFrame(columns=["id", "title", "text", "subject", "block_type", "created_at", "item_type"])

    # normalize journal entries
    journal_df = pd.DataFrame(journal_items)
    if not journal_df.empty:
        # journal entries may not have subject/block_type
        journal_df = journal_df.rename(columns={"description": "text", "created_at": "created_at", "title": "title"})
        journal_df["subject"] = journal_df.get("subject", None)
        journal_df["block_type"] = journal_df.get("block_type", "journal")
        journal_df["item_type"] = "journal"
    else:
        journal_df = pd.DataFrame(columns=["id", "title", "text", "subject", "block_type", "created_at", "item_type"])

    df = pd.concat([notes_df, journal_df], ignore_index=True, sort=False)
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    else:
        df["created_at"] = pd.NaT

    # build text column for vectorization
    df["title"] = df.get("title", "").fillna("")
    df["text"] = df.get("text", "").fillna("")
    df["text_full"] = (df["title"].astype(str) + " " + df["text"].astype(str)).str.strip()

    # time features
    df["hour"] = df["created_at"].dt.hour.fillna(-1).astype(int)
    df["weekday"] = df["created_at"].dt.day_name().fillna("Unknown")
    # ensure id column
    if "id" not in df.columns:
        df = df.reset_index().rename(columns={"index": "id"})
    return df


def load_interactions() -> pd.DataFrame:
    """
    Load interactions from Supabase table 'noteblocks'.
    Treat each noteblock as an interaction (creation event).
    Expected columns: id (as item_id), btype (as event_type), created_at (as timestamp), label=1 (creation implies engagement)
    """
    try:
        res = supabase.table("noteblocks").select("*").execute()
        df = pd.DataFrame(res.data or [])
    except Exception as err:
        st.warning("Error reading noteblocks for interactions: %s" % err)
        return pd.DataFrame()

    if df.empty:
        return df
    # Map columns to interaction format
    df = df.rename(columns={"id": "item_id", "btype": "event_type", "created_at": "timestamp"})
    df["event_type"] = df["event_type"].fillna("create")  # default to 'create' if btype missing
    df["label"] = 1  # assume creation is positive engagement
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.NaT
    return df


# -------------------------
# Feature engineerng
# -------------------------
def build_feature_matrices(items_df: pd.DataFrame,
                           text_col: str = "text_full",
                           cat_cols: List[str] = ("subject", "block_type", "item_type", "weekday"),
                           num_cols: List[str] = ("hour",),
                           state: Optional[Dict[str, Any]] = None):
    """
    Returns:
      X_items (sparse matrix), tfidf_vectorizer, cat_encoder, num_scaler, items_df (index aligned)
    If state is provided, uses pre-fitted transformers from state to transform data.
    Otherwise, fits new transformers.
    """
    items_df = items_df.reset_index(drop=True).copy()
    if state is not None:
        # Use pre-fitted transformers
        tf = state["tf"]
        enc = state["enc"]
        scaler = state["scaler"]
        cat_cols = state["cat_cols"]
        num_cols = state["num_cols"]
        # text
        text_mat = tf.transform(items_df[text_col].fillna(""))
        # categorical
        cat_mat = enc.transform(items_df[list(cat_cols)].fillna(""))
        # numerics
        if num_cols:
            num_arr = scaler.transform(items_df[list(num_cols)].fillna(-1).astype(float))
            num_mat = csr_matrix(num_arr)
        else:
            num_mat = csr_matrix((len(items_df), 0))
    else:
        # Fit new transformers
        # text
        tf = TfidfVectorizer(max_features=5000, stop_words="english")
        text_mat = tf.fit_transform(items_df[text_col].fillna(""))
        # categorical
        enc = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
        cat_mat = enc.fit_transform(items_df[list(cat_cols)].fillna(""))
        # numerics
        if num_cols:
            scaler = StandardScaler()
            num_arr = scaler.fit_transform(items_df[list(num_cols)].fillna(-1).astype(float))
            num_mat = csr_matrix(num_arr)
        else:
            scaler = None
            num_mat = csr_matrix((len(items_df), 0))

    X = hstack([text_mat, cat_mat, num_mat], format="csr")
    if state is None:
        state = {"tf": tf, "enc": enc, "scaler": scaler, "cat_cols": cat_cols, "num_cols": num_cols}
    return X, state, items_df


# -------------------------
# Build training dataset (join interactions -> item features)
# -------------------------
def build_interaction_dataset(items_df: pd.DataFrame, interactions_df: pd.DataFrame, X_items):
    """
    Merge interactions with items and produce X (sparse), y (labels), timestamps, item_idx list.
    Only interactions with item_id present in items_df are kept.
    """
    if interactions_df.empty or items_df.empty:
        return None, None, None, None

    items_lookup = items_df[["id"]].reset_index().set_index("id")  # mapping id -> index
    merged = interactions_df.merge(items_lookup.reset_index(), left_on="item_id", right_on="id", how="inner")
    if merged.empty:
        return None, None, None, None
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    # map to X rows via the index in items_lookup
    merged["item_idx"] = merged["id"].map(items_lookup["index"])
    # build X rows by selecting rows from X_items
    from scipy import sparse
    row_mats = []
    for idx in merged["item_idx"].tolist():
        row_mats.append(X_items[idx])
    X = sparse.vstack(row_mats, format="csr")
    y = merged["label"].astype(int).values
    timestamps = merged["timestamp"].values
    return X, y, timestamps, merged


# -------------------------
# Training with LightGBM
# -------------------------
def train_lightgbm_classifier(X, y, timestamps, n_splits: int = 3, params: dict = None):
    """
    Time-aware CV with TimeSeriesSplit; returns trained model and cv metrics.
    Uses LGBMClassifier to predict positive label (completion/engagement).
    """
    if X is None or y is None or len(y) == 0:
        return None, {"error": "no data"}

    if params is None:
        params = {"n_estimators": 200, "learning_rate": 0.05, "num_leaves": 31, "random_state": 42}

    tss = TimeSeriesSplit(n_splits=n_splits)
    aucs = []
    models = []
    from sklearn.metrics import roc_auc_score
    for train_idx, test_idx in tss.split(X):
        X_train = X[train_idx].toarray()
        X_test = X[test_idx].toarray()
        y_train = y[train_idx]
        y_test = y[test_idx]
        model = lgb.LGBMClassifier(**params)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], callbacks=[lgb.early_stopping(20), lgb.log_evaluation(0)])
        preds = model.predict_proba(X_test)[:, 1]
        try:
            auc = roc_auc_score(y_test, preds)
        except Exception:
            auc = float("nan")
        aucs.append(auc)
        models.append(model)
    # final model trained on all data
    final_model = lgb.LGBMClassifier(**params)
    final_model.fit(X.toarray(), y)
    return final_model, {"cv_auc_mean": float(np.nanmean(aucs)), "cv_auc": aucs, "n_samples": len(y)}


# -------------------------
# Recommendation / aggregation to categories
# -------------------------
def recommend_categories_from_model(model,
                                    X_items,
                                    items_df: pd.DataFrame,
                                    state: Dict[str, Any],
                                    user_context_texts: List[str],
                                    top_k_subjects: int = 5,
                                    top_k_methods: int = 3,
                                    current_hour: Optional[int] = None,
                                    current_weekday: Optional[str] = None,
                                    time_alpha: float = 0.5):
    """
    Use the trained classifier to predict probability of positive engagement for items given a user context.
    Aggregate probabilities by subject and (subject, block_type) returning top subjects and their methods.
    """
    if model is None:
        return {"subjects": [], "methods": {}}
    # build a user-item vector: transform user text into text space then pad zeros for remaining features
    tf = state["tf"]
    enc = state["enc"]
    scaler = state["scaler"]
    cat_cols = state["cat_cols"]
    num_cols = state["num_cols"]

    # text vector
    text_vec = tf.transform([" ".join(user_context_texts or [""])])
    # build zero cat and num matrices with correct feature dims
    cat_n_cols = enc.transform(pd.DataFrame([[""] * len(cat_cols)], columns=cat_cols)).shape[1]
    num_n_cols = len(num_cols) if num_cols else 0
    from scipy import sparse
    zero_cat = sparse.csr_matrix((1, cat_n_cols))
    zero_num = sparse.csr_matrix((1, num_n_cols))
    user_vec = hstack([text_vec, zero_cat, zero_num], format="csr")

    probs = model.predict_proba(user_vec.toarray())[:, 1]
    # model returns single row; expand to items count by repeating prob adjusted per-item using item features context
    # Instead, compute model probabilities per item by running model on X_items
    item_probs = model.predict_proba(X_items.toarray())[:, 1]
    items_df = items_df.copy().reset_index(drop=True)
    items_df["pred_prob"] = item_probs

    # time boost
    if current_hour is None or current_weekday is None:
        now = pd.Timestamp.now()
        current_hour = now.hour if current_hour is None else current_hour
        current_weekday = now.day_name() if current_weekday is None else current_weekday

    boost = ((items_df["hour"] == current_hour).astype(float) * time_alpha) + ((items_df["weekday"] == current_weekday).astype(float) * (time_alpha / 2))
    items_df["final_score"] = items_df["pred_prob"] * (1 + boost)

    # aggregate by subject (mean of final_score)
    subj = items_df.groupby("subject")["final_score"].mean().sort_values(ascending=False)
    subj = subj.dropna()
    top_subjects = list(zip(subj.index.tolist()[:top_k_subjects], subj.values.tolist()[:top_k_subjects]))

    methods = {}
    for subject, _ in top_subjects:
        subset = items_df[items_df["subject"] == subject]
        if subset.empty:
            methods[subject] = []
            continue
        m = subset.groupby("block_type")["final_score"].mean().sort_values(ascending=False)
        methods[subject] = list(zip(m.index.tolist()[:top_k_methods], m.values.tolist()[:top_k_methods]))
    return {"subjects": top_subjects, "methods": methods}


# -------------------------
# Helpers: save / load state & model
# -------------------------
def save_state(state: Dict[str, Any], path: str = STATE_PATH):
    with open(path, "wb") as f:
        pickle.dump(state, f)


def load_state(path: str = STATE_PATH) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def save_model(model, path: str = MODEL_PATH):
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load_model(path: str = MODEL_PATH):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)
        sparse