# NIMOZINI: Study & Mental Health Buddy

#### Video Demo:  <URL HERE>

#### Description:
NIMOZINI is my private Streamlit app which is a study mental wellness assistant designed to hold learning content, journal reflections, studying and emotional trends analytics, and ML-powered recommendations. The application integrates a Supabase backend for data persistence and includes modular features across Home, Dashboard, Notes, and Journal pages.

---

## 1. Project Overview

I made NIMOZINI since I wanted single interface for organization, self-reflection, and evidence-based study planning, similar to Notion's but with my own philosophy. It combines:

- hierarchical note management (subject → unit → topic → subtopic → notes)
- diverse block types for content (text, links, files, drawings, Anki imports)
- journal entries with sentiment analysis
- analytics dashboards for study and mood tracking
- automated recommendation engine using LightGBM
- simple password-based private access via Streamlit session state

The source code is contained in `app/main.py`, `app/nav/*`, and utility modules under `app/utils`. Secret management and keys are expected in `secrets.toml` as `SUPABASE_URL`, `SUPABASE_KEY`, and `PASSWORD`.

---

## 2. File and Module Breakdown

### 2.1 `app/main.py`

`main.py` is the entry point for Streamlit. It:

- checks `st.session_state["is_auth"]`
- prompts for password if not authenticated
- validates password against `st.secrets.get("PASSWORD")`
- displays a sidebar radio menu that routes to pages in `pages = {"Home": home, "Dashboard": dashboard, "Notes": notes, "Journal": journal}`

This file defines the app shell and access control, leaving feature implementation to the navigation pages.

### 2.2 `app/nav/home.py`

`home.py` contains the `show_page()` function and acts as the landing page. It shows:

- title: "NIMOZINI: Study & Mental Health Buddy"
- a symbolic image (Mnemosyne, goddess of memory)

### 2.3 `app/nav/dashboard.py`

`dashboard.py` offers the analytics overview and recommendations engine. Key behaviors:

- loads note blocks and journal entries from `noteblocks` and `journal_entries` Supabase tables
- ensures `created_at` exists and casts to datetime
- supports daily/weekly view toggle, with period selectors
- visualizes note behavior with Altair charts: hour-of-day, day-of-week, subjects, block types
- analyzes emotions from journal entries and shows top 3 feelings in a donut chart
- runs `get_recommendations()` by using `app/utils/ml.py`

In recommendation flow:

- removes previous model/state to force retrain (useful in development)
- collects raw items from notes + journals
- loads interactions from noteblock actions
- fallback frequency-based subject/method suggestions when data insufficient
- trains LightGBM with time-aware splitting and persistence in `recommender_model.pkl` / `recommender_state.pkl`
- returns ranked subjects and block-type methods

When recommendations are ready, it writes a short summary.

### 2.4 `app/nav/notes.py`

`notes.py` is the largest module and includes full note management toolbox. It features:

- Supabase configuration and client initialization
- selection CRUD helpers for subjects, units, topics, subtopics
- `get_blocks`, `create_block`, `display_blocks` to render and mutate noteblocks
- support for block types:
  - `text`, `header`, `url`, `internal_link`, `fileupload`, `canvas`, `flashcards`, `feynman`, `interleave`
- custom data serialization into Supabase friendly payloads via `serialize()`
- Anki `.apkg` import parsing (`parse_apkg`) into front/back metadata
- interactive note workflows with Streamlit widgets and state flags
- embedded side panel controls for advanced study modes:
  - `feynman()` session builder
  - `interleave()` subtopic mixing suggestions
  - `pomodoro()` timer with browser notifications

The UI function `show_page()` works in two states:

- first, selection mode (`select_menu()`) where subject/unit/topic/subtopic is chosen
- second, editing mode under `st.session_state["view_notes"]` with `note_editor()` and toolbar

It allows multiple add/update/delete operations and renders existing blocks. Content is live-updated to Supabase.

### 2.5 `app/nav/journal.py`

`journal.py` provides journaling plus sentiment analysis.

- `create_entry()`: inserts a journal row with title, description, emotion, created_at
- `get_entries()`: fetches history sorted descending by creation date
- `analyze_sentiment(text)`: uses `transformers.pipeline` with `SamLowe/roberta-base-go_emotions` to compute emotional score and map to custom weights

`journal_editor()` page has:

- listing in [expanders] for each entry
- sidebar form for adding new entries (title + description)
- on submit, calls `create_entry()` and reruns

### 2.6 `app/utils/helpers.py`

Currently a placeholder (marked `#spare file`) and can host shared utility functions in future.

### 2.7 `app/utils/ml.py`

`ml.py` contains the machine learning pipeline for recommendations:

- Supabase client, same config as other modules
- paths for persisted model/state inside `app/utils`
- `load_items_from_sources()`: consolidates notes and journals into uniform item dataframe
- `load_interactions()`: interprets `noteblocks` as interaction history with label=1
- `build_feature_matrices()`: TF-IDF on full text, one-hot categorical (subject, block_type, item_type, weekday), numerical scaling (hour)
- `build_interaction_dataset()`: joins interactions to item features for supervised training
- `train_lightgbm_classifier()`: semi-time-aware training and cross-validation with `TimeSeriesSplit` and `lgb.LGBMClassifier`
- `recommend_categories_from_model()`: produces subject/method scores from model predictions plus small time boosting
- save/load utilities for model and preprocessing state

This module enables the Dashboard's “Show Recommendations” behavior.

---

## 3. Data Model and Backend

### 3.1 Supabase Tables involved
- `subjects` (id, name)
- `units` (id, subject_id, name)
- `topics` (id, unit_id, name)
- `subtopics` (id, topic_id, name)
- `noteblocks` (id, subtopic_id, subject, btype, content, created_at) plus optional metadata fields
- `journal_entries` (id, title, description, emotion, created_at)

### 3.2 Secret configuration
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `PASSWORD` (app unlock key)

---

## 4. User Experience

### Authentication
- matrix simple text password prompt
- prevents unauthorized access with stateful lock

### Navigation
- sidebar radio on home page selects: `Home`, `Dashboard`, `Notes`, `Journal`
- each page module has `show_page()` for composition

### Notes workflow
- building curriculum-level structure then adding blocks.
- blocks support rich content, media, and learning methods.
- editing is immediate for text blocks; file/canvas uploads are stored and rendered.

### Journal workflow
- submit description to log mood and reflection
- sentiment analytic model provides emotion vector and numeric score for dashboard trends

### Dashboard workflow
- daily/weekly analytics of note/journal activity
- interactive charts with Altair
- top-3 emotions chart for current day/week
- ML-driven recommender encouraging focused subject/method selection

---

## 5. Setup and Run Instructions

1. clone repo
2. configure `secrets.toml` or environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `PASSWORD`
3. install dependencies:
   - `pip install -r requirements.txt`
4. run:
   - `streamlit run app/main.py --server.enableCORS false --server.enableXsrfProtection false`

Notes:
- `Supabase` database schema must include the table names and columns referenced above.
- `transformers` model downloads require internet access for sentiment labeling.

---

## 6. Extension Ideas

- Add `app/utils/helpers.py` helper functions and service layer centralization
- Add automated metadata versioning / schema migration with Supabase functions
- Add user accounts and multi-user profiles (instead of one shared password)
- Add natural language input, note summarization, and cross-note linking search
- add export/import of notes to Markdown/JSON

---

## 7. Support & Contribution

- The project is open for improvement. Raise issues if tables or model behavior are inconsistent.
- Add tests in a dedicated `tests/` folder to validate data flows for notes, journals, and recommender models.

---

## 8. Notes

- `README` here is based on current `app` folder state (March 2026 snapshot)
- Certain UX areas may be refactored to avoid blocking `st.button` loops (e.g., Pomodoro and interleave state logic) if locking is needed for production.


