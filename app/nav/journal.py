from datetime import datetime, timedelta
import streamlit as st
from supabase import create_client, Client
from transformers import pipeline
import torch


# Initialize Supabase client (you may already have this in a shared file)
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CREATE ---
def create_entry(title: str, description: str, emotion: str, created_at: datetime):
    return supabase.table("journal_entries").insert({"title": title, "description": description, "emotion": emotion, "created_at": created_at}).execute().data

# --- READ ---
def get_entries():
    return supabase.table("journal_entries").select("*").order("created_at", desc=True).execute().data

#Sentiment Analysis
def analyze_sentiment(text):
    LABELS = {'admiration': 0.6, 'amusement': 0.7, 'anger': -0.8, 'annoyance': -0.5, 
              'approval': 0.2, 'caring': 0.3, 'confusion': -0.3, 'curiosity': 0.8, 
              'desire': 0.5, 'disappointment': -0.5, 'disapproval': -0.2, 'disgust': -0.4, 
              'embarrassment': -0.6, 'excitement': 0.8, 'fear': -0.8, 'gratitude': 0.6, 
              'grief': -0.9, 'joy': 0.9, 'love': 0.9, 'nervousness': -1, 'optimism': 1, 
              'pride': 1, 'realization': 0.5, 'relief': 0.8, 'remorse': -0.7, 'sadness': -1, 
              'surprise': 0.3, 'neutral': 0.0}
    classifier = pipeline("text-classification", model="SamLowe/roberta-base-go_emotions")
    result = classifier(text)
    score = LABELS[result[0]['label']] * result[0]['score']
    return {result[0]['label']: score}

# Streamlit Page
def journal_editor():
    st.title("Journal")
    entries = get_entries()
    if not entries:
        st.info("No journal entries found.")
    else:
        for entry in entries:
            with st.expander(f"**{entry['title']}** at {entry['created_at'][:10]} - {entry['created_at'][11:16]}"):
                st.write(entry["description"])
    
    st.sidebar.header("Add Journal Entry")
    with st.sidebar.form("add_entry_form", clear_on_submit=True):
        title = st.text_input("Title")
        description = st.text_area("Description")
        submitted = st.form_submit_button("Add Entry")
        if submitted and title and description:
            create_entry(title, description, analyze_sentiment(description), datetime.utcnow().isoformat())
            st.success(f"Added entry: {title}")
            st.rerun()
            
def show_page():
    journal_editor()
   