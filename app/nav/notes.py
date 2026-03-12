from re import sub
import re
import sqlite3
import zipfile
import os
import tempfile
import random
import time
import datetime
import json
import pandas as pd
from PIL import Image
from io import BytesIO
import base64
import numpy as np
import streamlit as st
from streamlit_drawable_canvas import st_canvas
import streamlit.components.v1 as components
from supabase import create_client, Client

# Supabase setup
SUPABASE_URL: str = st.secrets["SUPABASE_URL"]
SUPABASE_KEY: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Helper functions
# Subjects
def select_subject(sidebar: bool = False):
    subjects_names = supabase.table("subjects").select("name").execute().data
    if not subjects_names:
        return {"id": None, "name": None}
    
    chosen_subject_name = st.selectbox("Subjects:", [s["name"] for s in subjects_names]) if not sidebar else st.sidebar.selectbox("Subjects:", [s["name"] for s in subjects_names])
    if chosen_subject_name:
        chosen_subject_id = supabase.table("subjects").select("id").eq("name", chosen_subject_name).execute().data[0]["id"]
        return {"id": chosen_subject_id, "name": chosen_subject_name}
    return {"id": None, "name": None}

# Units
def select_unit(subject_id: str, sidebar: bool = False):
    units_names = supabase.table("units").select("name").eq("subject_id", subject_id).execute().data
    if not units_names:
        return {"id": None, "name": None}
    chosen_unit_name = st.selectbox("Units:", [u["name"] for u in units_names]) if not sidebar else st.sidebar.selectbox("Units:", [u["name"] for u in units_names])
    if chosen_unit_name:
        try:
            chosen_unit_id = supabase.table("units").select("id").eq("name", chosen_unit_name).execute().data[0]["id"]
        except IndexError:
            chosen_unit_id = None
        return {"id": chosen_unit_id, "name": chosen_unit_name}
    return {"id": None, "name": None}

def create_unit(subject_id: str, name: str):
    return supabase.table("units").insert({"subject_id": subject_id, "name": name}).execute()

def update_unit(unit_id: str, new_name: str):
    return supabase.table("units").update({"name": new_name}).eq("id", unit_id).execute()

def delete_unit(unit_id: str):
    return supabase.table("units").delete().eq("id", unit_id).execute()

# Topics
def select_topic(unit_id: str, sidebar: bool = False):
    topics_names = supabase.table("topics").select("name").eq("unit_id", unit_id).execute().data
    if not topics_names:
        return {"id": None, "name": None}
    chosen_topic_name = st.selectbox("Topics:", [t["name"] for t in topics_names]) if not sidebar else st.sidebar.selectbox("Topics:", [t["name"] for t in topics_names])
    if chosen_topic_name:
        try: 
            chosen_topic_id = supabase.table("topics").select("id").eq("name", chosen_topic_name).execute().data[0]["id"]
        except IndexError:
            chosen_topic_id = None
        return {"id": chosen_topic_id, "name": chosen_topic_name}
    return {"id": None, "name": None}

def create_topic(unit_id: str, name: str):
    return supabase.table("topics").insert({"unit_id": unit_id, "name": name}).execute()

def update_topic(topic_id: str, new_name: str):
    return supabase.table("topics").update({"name": new_name}).eq("id", topic_id).execute()

def delete_topic(topic_id: str):
    return supabase.table("topics").delete().eq("id", topic_id).execute()

# Subtopics
def select_subtopic(topic_id: str, sidebar: bool = False):
    subtopics_names = supabase.table("subtopics").select("name").eq("topic_id", topic_id).execute().data
    if not subtopics_names:
        return {"id": None, "name": None}
    chosen_subtopic_name = st.selectbox("Subtopics:", [s["name"] for s in subtopics_names]) if not sidebar else st.sidebar.selectbox("Subtopics:", [s["name"] for s in subtopics_names])
    if chosen_subtopic_name:
        try:
            chosen_subtopic_id = supabase.table("subtopics").select("id").eq("name", chosen_subtopic_name).execute().data[0]["id"]
        except IndexError:                  
            chosen_subtopic_id = None
        return {"id": chosen_subtopic_id, "name": chosen_subtopic_name}
    return {"id": None, "name": None}

def create_subtopic(topic_id: str, name: str):
    return supabase.table("subtopics").insert({"topic_id": topic_id, "name": name}).execute()

def update_subtopic(subtopic_id: str, new_name: str):
    return supabase.table("subtopics").update({"name": new_name}).eq("id", subtopic_id).execute()

def delete_subtopic(subtopic_id: str):
    return supabase.table("subtopics").delete().eq("id", subtopic_id).execute()

# Note-blocks
def get_blocks(subtopic_id: str):
    return (
        supabase.table("noteblocks")
        .select("*")
        .eq("subtopic_id", subtopic_id)
        .order("order_index")
        .execute()
        .data
    )

def create_block(subtopic_id: str, subject: str, btype: str, content, order_index: int, created_at: datetime):
    return supabase.table("noteblocks").insert({
        "subtopic_id": subtopic_id,
        "subject": subject,
        "btype": btype,
        "content": content,
        "order_index": order_index,
        "created_at": created_at
    }).execute().data

def update_blocks_order(subtopic_id: str, newadded_block_id: str, newadded_block_order_index: int):
    return supabase.rpc("increment_order_index", {
    "subtopic_id": subtopic_id,
    "new_block_id": newadded_block_id,
    "min_order": newadded_block_order_index
}).execute()

def delete_block(block_id: str):
    return supabase.table("noteblocks").delete().eq("id", block_id).execute()

def display_blocks(subtopic_id: str):
    blocks = get_blocks(subtopic_id)
    for block in blocks:
        with st.container():
            match block["btype"]:
                case "text":
                    text = st.text_area("", value=block["content"], key=f"block_{block['id']}", height=100)
                    if text:
                        supabase.table("noteblocks").update({"content": text}).eq("id", block["id"]).execute()
                case "header":
                    st.subheader(block["content"])
                case "url":
                    st.markdown(block["content"], unsafe_allow_html=True)
                case "internal_link":
                    linked_subtopic_id = block["content"]
                    linked_subtopic_name = supabase.table("subtopics").select("name").eq("id", linked_subtopic_id).execute().data[0]["name"]
                    if st.button(f"Go to {linked_subtopic_name}", key=f"link_{block['id']}"):
                        st.session_state["view_notes"] = linked_subtopic_id
                        st.rerun()
                case "fileupload":
                    match block["content"].type.split("/")[0]:
                        case "image":
                            st.image(block["content"], caption=block["content"].name)
                        case "video":
                            st.video(block["content"])
                        case "audio":
                            st.audio(block["content"])
                        case _:
                            st.write(f"Uploaded File: {block['content'].name}")
                case "canvas":
                    st.image(block["content"])
                case "flashcards":
                    st.expander("Flashcards Session:").write(block["content"])
                case "feynman":
                    st.expander("Feynman Session:").write(block["content"])
                case "interleave":
                    st.expander("Interleaving Session:").write(block["content"])

#Anki .apkg parser  
def parse_apkg(apkg_path):
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(apkg_path, 'r') as zf:
            zf.extractall(tmpdir)
        db_path = os.path.join(tmpdir, "collection.anki2")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT cards.id, notes.flds, cards.due, cards.ivl, cards.reps, cards.lapses
            FROM cards
            JOIN notes ON cards.nid = notes.id
        """)
        cards = []
        for row in cur.fetchall():
            card_id, fields, due, interval, reps, lapses = row
            # fields are stored as a single string, separated by \x1f
            split_fields = fields.split("\x1f")
            front = split_fields[0] if len(split_fields) > 0 else ""
            back = split_fields[1] if len(split_fields) > 1 else ""
            cards.append({
                "id": card_id,
                "front": front,
                "back": back,
                "due": due,
                "interval": interval,
                "reviews": reps,
                "lapses": lapses
            })
        conn.close()
        return cards

def _serialize_block_content(btype: str, raw):
    if raw is None:
        return None
    match btype:
        case "fileupload":
            try:
                data = raw.getbuffer() if hasattr(raw, "getbuffer") else raw.read()
                fname = getattr(raw, "name", f"upload_{int(time.time())}")
                path = f"uploads/{int(time.time())}_{fname}"
                supabase.storage.from_("uploads").upload(path, data)
                url = supabase.storage.from_("uploads").get_public_url(path)["publicURL"]
                return {"type": "file", "name": fname, "url": url}
            except Exception:
                return {"type": "file", "name": getattr(raw, "name", str(raw))}
            
        case "canvas":
            try:
                from PIL import Image
                arr = raw
                if isinstance(arr, np.ndarray):
                    img = Image.fromarray(arr.astype("uint8"))
                else:
                    img = arr  # assume PIL Image
                buf = BytesIO()
                img.save(buf, format="PNG")
                data = buf.getvalue()
                path = f"uploads/canvas_{int(time.time())}.png"
                supabase.storage.from_("uploads").upload(path, data)
                url = supabase.storage.from_("uploads").get_public_url(path)["publicURL"]
                return {"type": "image", "url": url}
            except Exception:
                return {"type": "image", "fallback": str(raw)}

        case "flashcards" | "feynman" | "interleave":
            try:
                json.dumps(raw)  # test serializability
                return raw
            except Exception:
                return {"type": btype, "repr": str(raw)}

        case _:
            try:
                json.dumps(raw)
                return raw
            except Exception:
                return str(raw)

# Streamlit Page
def select_menu():
    st.title("Notes")

    #Subject
    chosen_subject = select_subject()
    if not chosen_subject:
        st.info("Please select a subject first")
        return
    
    if st.button("Select Subject"):
        st.session_state["subject_sel_btn"] = True
    if st.session_state.get("subject_sel_btn"):
        #Unit
        st.subheader(f"Units in {chosen_subject['name']}")

        # Add new unit
        if st.button("Add New Unit"):
            st.session_state["unit_add_btn"] = True
        if st.session_state.get("unit_add_btn"):
            new_unit = st.text_input("Unit Name", key="new_unit")
            if st.button("Confirm Unit", key="confirm_unit"):
                st.session_state["unit_confadd_btn"] = True
            if st.session_state.get("unit_confadd_btn"):
                if new_unit.strip():
                    create_unit(chosen_subject["id"], new_unit)
                    st.success("Unit added!")
                else:
                    st.error("Unit name cannot be empty")
                st.session_state["unit_add_btn"] = False
                st.session_state["unit_confadd_btn"] = False
                st.rerun()

        chosen_unit = select_unit(chosen_subject["id"])
        if chosen_unit["id"]:
            col1, col2, col3 = st.columns(3)
            with col1:
                unit_sel_btn = st.button("Select Unit", key=f"select_unit_{chosen_unit['id']}")
            with col2:
                if st.button("Update Unit", key=f"update_unit_{chosen_unit['id']}"):
                    st.session_state["unit_update_btn"] = True
                if st.session_state.get("unit_update_btn"):
                    new_unit_name = st.text_input("Rename unit", value=chosen_unit["name"], key=f"unit_name_{chosen_unit['id']}")
                    if st.button("Confirm Update", key=f"confirm_update_{chosen_unit['id']}"):
                        st.session_state["unit_confupdate_btn"] = True
                    if st.session_state.get("unit_confupdate_btn"):
                        if new_unit_name.strip():
                            update_unit(chosen_unit["id"], new_unit_name)
                            st.success("Unit updated!")
                        else:
                            st.error("Unit name cannot be empty")
                        st.session_state["unit_update_btn"] = False
                        st.session_state["unit_confupdate_btn"] = False
                        st.rerun()
            with col3:
                if st.button("Delete Unit", key=f"delete_unit_{chosen_unit['id']}"):
                    st.session_state["unit_delete_btn"] = True
                if st.session_state.get("unit_delete_btn"):
                    if st.button("Confirm Delete", key=f"confirm_delete_{chosen_unit['id']}"):
                        st.session_state["unit_confdelete_btn"] = True
                    if st.session_state.get("unit_confdelete_btn"):
                        delete_unit(chosen_unit["id"])
                        st.warning("Unit deleted!")
                        st.session_state["unit_delete_btn"] = False
                        st.session_state["unit_confdelete_btn"] = False
                        st.rerun()
            if unit_sel_btn:
                st.session_state["unit_sel_btn"] = True

                #Topic
                st.subheader(f"Topics in {chosen_unit['name']}")

                # Add new topic
                if st.button("Add New Topic"):
                    st.session_state["topic_add_btn"] = True
                if st.session_state.get("topic_add_btn"):
                    new_topic = st.text_input("Topic Name", key="new_topic")
                    if st.button("Confirm Topic", key="confirm_topic"):
                        st.session_state["topic_confadd_btn"] = True
                    if st.session_state.get("topic_confadd_btn"):
                        if new_topic.strip():
                            create_topic(chosen_unit_id, new_topic)
                            st.success("Topic added!")
                        else:
                            st.error("Topic name cannot be empty")
                        st.session_state["topic_add_btn"] = False
                        st.session_state["topic_confadd_btn"] = False
                        st.rerun()

                chosen_topic = select_topic(chosen_unit["id"])
                if chosen_topic["id"]:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        topic_sel_btn = st.button("Select Topic", key=f"select_topic_{chosen_topic['id']}")
                    with col2:
                        if st.button("Update Topic", key=f"update_topic_{chosen_topic['id']}"):
                            st.session_state["topic_update_btn"] = True
                        if st.session_state.get("topic_update_btn"):
                            new_topic_name = st.text_input("Rename topic", value=chosen_topic["name"], key=f"topic_name_{chosen_topic['id']}")
                            if st.button("Confirm Update", key=f"confirm_update_{chosen_topic['id']}"):
                                st.session_state["topic_confupdate_btn"] = True
                            if st.session_state.get("topic_confupdate_btn"):
                                if new_topic_name.strip():
                                    update_topic(chosen_topic["id"], new_topic_name)
                                    st.success("Topic updated!")
                                else:
                                    st.error("Topic name cannot be empty")
                                st.session_state["topic_update_btn"] = False
                                st.session_state["topic_confupdate_btn"] = False
                                st.rerun()
                    with col3:
                        if st.button("Delete Topic", key=f"delete_topic_{chosen_topic_['id']}"):
                            st.session_state["topic_delete_btn"] = True
                        if st.session_state.get("topic_delete_btn"):
                            if st.button("Confirm Delete", key=f"confirm_delete_{chosen_topic['id']}"):
                                st.session_state["topic_confdelete_btn"] = True
                            if st.session_state.get("topic_confdelete_btn"):
                                delete_topic(chosen_topic["id"])
                                st.warning("Topic deleted!")
                                st.session_state["topic_delete_btn"] = False
                                st.session_state["topic_confdelete_btn"] = False
                                st.rerun()
                    if topic_sel_btn:
                        st.session_state["topic_sel_btn"] = True

                        #Subtopic
                        st.subheader(f"Subtopics in {chosen_topic_name}")

                        # Add new subtopic
                        if st.button("Add New Subtopic"):
                            st.session_state["subtopic_add_btn"] = True
                        if st.session_state.get("subtopic_add_btn"):
                            new_subtopic = st.text_input("Subtopic Name", key="new_subtopic")
                            if st.button("Confirm Subtopic", key="confirm_subtopic"):
                                st.session_state["subtopic_confadd_btn"] = True
                            if st.session_state.get("subtopic_confadd_btn"):
                                if new_subtopic.strip():
                                    create_subtopic(chosen_topic_id, new_subtopic)
                                    st.success("Subtopic added!")
                                else:
                                    st.error("Subtopic name cannot be empty")
                                st.session_state["subtopic_add_btn"] = False
                                st.session_state["subtopic_confadd_btn"] = False
                                st.rerun()

                        chosen_subtopic = select_subtopic(chosen_topic["id"])
                        if chosen_subtopic["id"]:
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                subtopic_sel_btn = st.button("View Notes", key=f"select_subtopic_{chosen_subtopic['id']}")
                            with col2:
                                if st.button("Update Subtopic", key=f"update_subtopic_{chosen_subtopic['id']}"):
                                    st.session_state["subtopic_update_btn"] = True
                                if st.session_state.get("subtopic_update_btn"):
                                    new_subtopic_name = st.text_input("Rename subtopic", value=chosen_subtopic["name"], key=f"subtopic_name_{chosen_subtopic['id']}")
                                    if st.button("Confirm Update", key=f"confirm_update_{chosen_subtopic['id']}"):
                                        st.session_state["subtopic_confupdate_btn"] = True
                                    if st.session_state.get("subtopic_confupdate_btn"):
                                        if new_subtopic_name.strip():
                                            update_subtopic(chosen_subtopic["id"], new_subtopic_name)
                                            st.success("Subtopic updated!")
                                        else:
                                            st.error("Subtopic name cannot be empty")
                                        st.session_state["subtopic_update_btn"] = False
                                        st.session_state["subtopic_confupdate_btn"] = False
                                        st.rerun()
                            with col3:
                                if st.button("Delete Subtopic", key=f"delete_subtopic_{chosen_subtopic['id']}"):
                                    st.session_state["subtopic_delete_btn"] = True
                                if st.session_state.get("subtopic_delete_btn"):
                                    if st.button("Confirm Delete", key=f"confirm_delete_{chosen_subtopic['id']}"):
                                        st.session_state["subtopic_confdelete_btn"] = True
                                    if st.session_state.get("subtopic_confdelete_btn"):
                                        delete_subtopic(chosen_subtopic["id"])
                                        st.warning("Subtopic deleted!")
                                        st.session_state["subtopic_delete_btn"] = False
                                        st.session_state["subtopic_confdelete_btn"] = False
                                        st.rerun()
                            if subtopic_sel_btn:
                                st.session_state["view_notes"] = {"subtopic": chosen_subtopic["id"], "subject": chosen_subject['name']}
                                st.rerun()
                                return

def text():
    return st.text_area("", height=100)

def header():
    st.sidebar.divider()
    return st.sidebar.text_input("header")

def url():
    st.sidebar.divider()
    link_text = st.sidebar.text_input("Link text")
    link_url = st.sidebar.text_input("Link URL")
    if link_text and link_url:
        return f"[{link_text}]({link_url})"

def internal_link():
    st.sidebar.divider()
    subject_id = select_subject(True)["id"]
    unit_id = select_unit(subject_id, True)["id"]
    topic_id = select_topic(unit_id, True)["id"]
    subtopic_id = select_subtopic(topic_id, True)["id"]
    return subtopic_id


def fileupload():
    st.sidebar.divider()
    return st.sidebar.file_uploader("Upload a file", type=["pdf", "doc", "docx", "odt", "txt", "md", "ppt", "pptx", "odp", "xls", "xlsx", "ods", "png", "jpg", "jpeg", "gif", "mp3", "wav", "mp4", "mov", "avi", "mkv", "zip", "rar", "7z"])

def canvas():
    st.sidebar.divider()
    drawing_mode = st.sidebar.selectbox("Drawing tool:", ("freedraw", "line", "rect", "circle", "polygon", "point", "transform"))
    stroke_width = st.sidebar.slider("Stroke width: ", 1, 25, 3)
    if drawing_mode == 'point':
        point_display_radius = st.sidebar.slider("Point display radius: ", 1, 25, 3)
    stroke_base = st.sidebar.color_picker("Stroke color hex: ")
    stroke_opacity = st.sidebar.number_input("Stroke opacity (%)", min_value=0.0, max_value=100.0, value=100.0, step=0.1)
    fill_base = st.sidebar.color_picker("Fill color hex:")
    fill_opacity = st.sidebar.number_input("Fill opacity (%)", min_value=0.0, max_value=100.0, value=30.0, step=0.1)
    stroke_color = f"rgba({int(stroke_base[1:3], 16)}, {int(stroke_base[3:5], 16)}, {int(stroke_base[5:7], 16)}, {stroke_opacity/100.0})"
    fill_color = f"rgba({int(fill_base[1:3], 16)}, {int(fill_base[3:5], 16)}, {int(fill_base[5:7], 16)}, {fill_opacity/100.0})"
    bg_color = st.sidebar.color_picker("Background color hex: ", "#eeeeee")
    bg_image = st.sidebar.file_uploader("Background image:", type=["png", "jpg"])
    height = st.sidebar.number_input("Canvas height: ", value=400)
    width = st.sidebar.number_input("Canvas width: ", value=700)
    realtime_update = st.sidebar.checkbox("Update in realtime", True)

    canvas_result = st_canvas(
        fill_color=fill_color,  # Fixed fill color with some opacity
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        background_color=bg_color,
        background_image=Image.open(bg_image) if bg_image else None,
        update_streamlit=realtime_update,
        height=height,
        width=width,
        drawing_mode=drawing_mode,
        point_display_radius=point_display_radius if drawing_mode == 'point' else 0,
        key="canvas",
    )

    if canvas_result.image_data is not None:
        return canvas_result.image_data
    #if canvas_result.json_data is not None:
        #objects = pd.json_normalize(canvas_result.json_data["objects"])
        #for col in objects.select_dtypes(include=['object']).columns:
            #objects[col] = objects[col].astype("str")
        #st.dataframe(objects)

def flashcards():
    st.sidebar.divider()
    uploaded_apkg = st.sidebar.file_uploader("Upload Anki .apkg file", type=["apkg"])
    if uploaded_apkg:
        with open("temp.apkg", "wb") as f:
            f.write(uploaded_apkg.getbuffer())
        return parse_apkg("temp.apkg")
        
def feynman():
    if "lap" not in st.session_state:
        st.session_state["lap"] = 0
    if "gaps_num_list" not in st.session_state:
        st.session_state["gaps_num_list"] = []
    if "feynman_end" not in st.session_state:
        st.session_state["feynman_end"] = False
    st.sidebar.divider()
    if st.session_state.get("feynman_end") == False:
        st.session_state["concepts"] = st.sidebar.number_input("Number of concepts", min_value=1, value=5, key="feynman_concepts")
        st.session_state["concepts_summary"] = st.sidebar.text_area("Concepts summary", key="feynman_concepts_summary")
        if st.session_state["concepts"] > 0 and st.session_state["concepts_summary"].strip():
            if st.sidebar.button("Add New Lap", key="feynman_add_lap"):
                st.session_state["lap"] += 1
                st.session_state[f"feynman_lap_{st.session_state['lap']}"] = True
            if st.session_state.get(f"feynman_lap_{st.session_state['lap']}"):
                st.sidebar.write(f"lap {st.session_state['lap']}")
                gaps_num = st.sidebar.number_input("Number of gaps to fill", min_value=0, max_value=concepts, value=concepts, key=f"feynman_gaps_num_{st.session_state['lap']}")
                st.session_state["gaps_num_list"].append(gaps_num)
                gaps_summary = st.sidebar.text_area("Gaps summary", key=f"feynman_gaps_summary_{st.session_state['lap']}")
                if gaps_num >= 0 and gaps_summary.strip():
                    st.sidebar.write("try filling in the gaps...")
            if st.sidebar.button("Finish Session", key="feynman_end"):
                st.session_state["feynman_end"] = True
                st.rerun()
    else:
        st.sidebar.write("Session over.")
        return {"concepts": st.session_state["concepts"], "concepts_summary": st.session_state["concepts_summary"], "laps": st.session_state["lap"], "gaps_num_list": st.session_state["gaps_num_list"]}


def interleave():
    if "interleaved_list" not in st.session_state:
        st.session_state["interleaved_list"] = []
    if "interleave_end" not in st.session_state:
        st.session_state["feynman_end"] = False
    st.sidebar.divider()
    if st.session_state.get("interleave_end") == False:
        topic_id = supabase.table("subtopics").select("topic_id").eq("id", st.session_state.get("view_notes")).execute().data[0]["topic_id"]
        unit_id = supabase.table("topics").select("unit_id").eq("id", topic_id).execute().data[0]["unit_id"]
        subject_id = supabase.table("units").select("subject_id").eq("id", unit_id).execute().data[0]["subject_id"]
        st.session_state["method"] = st.sidebar.selectbox("Interleave by:", ["Subtopics in two subjects", "Subtopics in current subject", "Subtopics in current unit", "Subtopics in current topic"])
        add_ons_form = st.sidebar.text_area("Add other elements (Optional)", key="interleave_other_elements")
        if add_ons_form and add_ons_form.strip():
            st.session_state["add_ons"] = add_ons_form.split("\n")
        else:
            st.session_state["add_ons"] = []
        if st.button("Suggest Interleaving"):
            st.session_state["interleave"] = True
        if st.session_state.get("interleave"):
            match st.session_state["method"]:
                case "Subtopics in two subjects":
                    subject2 = select_subject(True)["id"]
                    subtopics_in_current_subject = list(s["name"] for s in supabase.table("subtopics").select("name").in_("topic_id", supabase.table("topics").select("id").in_("unit_id", supabase.table("units").select("id").eq("subject_id", subject_id).execute().data).execute().data).execute().data)
                    subtopics_in_subject2 = list(s["name"] for s in supabase.table("subtopics").select("name").in_("topic_id", supabase.table("topics").select("id").in_("unit_id", supabase.table("units").select("id").eq("subject_id", subject2).execute().data).execute().data).execute().data)
                    interleaved_subtopics = random.sample(subtopics_in_current_subject, min(3, len(subtopics_in_current_subject))) + random.sample(subtopics_in_subject2, min(3, len(subtopics_in_subject2))) + random.sample(st.session_state["add_ons"], min(2, len(st.session_state["add_ons"])))
                case "Subtopics in current subject":
                    subtopics_in_current_subject = list(s["name"] for s in supabase.table("subtopics").select("name").in_("topic_id", supabase.table("topics").select("id").in_("unit_id", supabase.table("units").select("id").eq("subject_id", subject_id).execute().data).execute().data).execute().data)
                    interleaved_subtopics = random.sample(subtopics_in_current_subject, min(5, len(subtopics_in_current_subject))) + random.sample(st.session_state["add_ons"], min(2, len(st.session_state["add_ons"])))
                case "Subtopics in current unit":
                    subtopics_in_current_unit = list(s["name"] for s in supabase.table("subtopics").select("name").in_("topic_id", supabase.table("topics").select("id").eq("unit_id", unit_id).execute().data).execute().data)
                    interleaved_subtopics = random.sample(subtopics_in_current_unit, min(5, len(subtopics_in_current_unit))) + random.sample(st.session_state["add_ons"], min(2, len(st.session_state["add_ons"])))
                case "Subtopics in current topic":
                    subtopics_in_current_topic = list(s["name"] for s in supabase.table("subtopics").select("name").eq("topic_id", topic_id).execute().data)
                    interleaved_subtopics = random.sample(subtopics_in_current_topic, min(5, len(subtopics_in_current_topic))) + random.sample(st.session_state["add_ons"], min(2, len(st.session_state["add_ons"])))
            st.session_state["interleave"] = False
            if st.button("Pin"):
                st.session_state["pin"] = True
            if st.session_state.get("pin"):
                st.session_state["interleaved_list"] = st.session_state["interleaved_list"].append(interleaved_subtopics)
                st.session_state["pin"] = False
            if st.button("Finish Session", key="interleave_end"):
                st.session_state["interleave_finish_session"] = True
                st.rerun()
    else:
        st.sidebar.write("Session over.")
        return {"method": st.session_state["method"], "add_ons": st.session_state["add_ons"], "interleaved_list": st.session_state["interleaved_list"]}

def pomodoro():
    st.sidebar.divider()
    study_time = st.sidebar.slider("Work Time", 1, 90, 25, step=5)
    break_time = st.sidebar.slider("Break Time", 1, 30, 5, step=1)
    if st.sidebar.button("Start/Restart Timer", key="start_pomodoro"):
        while True:
            if st.sidebar.button("Kill Timer", key=f"kill_pomodoro_{laps}"):
                break
            for i in range(study_time * 60):
                time.sleep(1)
                minutes = (study_time * 60 - i) // 60
                seconds = (study_time * 60 - i) % 60
                st.session_state["timer"] = f"**Study Timer:** {minutes:02}:{seconds:02}"
                st.sidebar.header(st.session_state["timer"])
            break_notif = f"""
            <script>
            if (Notification.permission === "granted") {{
                new Notification("Break!");
            }} else if (Notification.permission !== "denied") {{
                Notification.requestPermission().then(permission => {{
                    if (permission === "granted") {{
                        new Notification("Break!");
                    }}
                }});
            }}
            </script>
            """
            components.html(break_notif, height=150)
            for i in range(break_time * 60):
                time.sleep(1)
                minutes = (break_time * 60 - i) // 60
                seconds = (break_time * 60 - i) % 60
                st.sidebar.header(f"**Break Timer:** {minutes:02}:{seconds:02}")
            study_notif = f"""
            <script>
            if (Notification.permission === "granted") {{
                new Notification("Back to Studying!");
            }} else if (Notification.permission !== "denied") {{
                Notification.requestPermission().then(permission => {{
                    if (permission === "granted") {{
                        new Notification("Back to Studying!");
                    }}
                }});
            }}
            </script>
            """
            components.html(study_notif, height=150)

TYPES = {"Text": "text", "Header": "header", "URL": "url", "Internal Link": "internal_link", "File": "fileupload", "Canvas": "canvas", "Flashcards Session": "flashcards", "Feynman Session": "feynman", "Interleaving Session": "interleave"}

def note_editor():
    display_blocks()
    st.sidebar.divider()
    pomodoro_timer()
    st.sidebar.divider()
    st.sidebar.title("Notes Toolbar")
    chosen_type = st.sidebar.selectbox("Add Block", list(["-"] + list(TYPES.keys())), key="chosen_type")
    if chosen_type and chosen_type != "-":
        chosen_placement = st.sidebar.selectbox("Choose Placement", ["At End"] + [f"Before Block {i+1}" for i in range(len(get_blocks(st.session_state["view_notes"]))) + 1], key="placement")
        if chosen_placement == "At End":
            order = len(get_blocks(st.session_state["view_notes"])) + 1
        else:
            order = int(chosen_placement.split(" ")[2])
        content = json.dumps(eval(TYPES[chosen_type])())
        if st.sidebar.checkbox("Confirm Block Addition", key="add_block"):
            st.session_state["add_block"] = True
        if st.session_state.get("add_block"):
            new_added_block = create_block(st.session_state["view_notes"]["subtopic"], st.session_state["view_notes"]["subject"], TYPES[chosen_type], content, order, datetime.now().isoformat())
            update_blocks_order(st.session_state["view_notes"], new_added_block[0]["id"], new_added_block[0]["order_index"])
            st.sidebar.success("Block added!")
            st.session_state["add_block"] = False
            st.rerun()
    chosen_block_delete = st.sidebar.selectbox("Delete Block", ["-"] + [f"Block {i+1}" for i in range(len(get_blocks(st.session_state["view_notes"])) + 1)], key="chosen_block_delete")
    if chosen_block_delete and chosen_block_delete != "-":
        if st.sidebar.checkbox("Confirm Deletion", key="delete_block"):
            st.session_state["delete_block"] = True
        if st.session_state.get("delete_block"):
            block_id = get_blocks(st.session_state["view_notes"])[int(chosen_block_delete.split(" ")[1]) - 1]["id"]
            delete_block(block_id)
            st.sidebar.warning("Block deleted!")
            st.session_state["delete_block"] = False
            st.rerun()

def show_page():
    if "view_notes" not in st.session_state:
        st.session_state["view_notes"] = None
    if st.session_state["view_notes"]:
        note_editor()
    else:
        select_menu()
