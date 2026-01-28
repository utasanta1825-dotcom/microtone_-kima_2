# app.py
# Streamlit microtonal rating app (SEQ/SIM)
# - Plays an audio stimulus
# - Collects valence/arousal/difficulty (+ optional notes)
# - Saves to local CSV (Streamlit Cloud: saved in app storage during runtime)

import os
import csv
import time
import uuid
import random
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# -------------------------
# Config
# -------------------------
APP_TITLE = "Microtonal Scale Rating"
ASSETS_DIR = Path("assets")
SEQ_DIR = ASSETS_DIR / "sequential"
SIM_DIR = ASSETS_DIR / "simultaneous"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
CSV_PATH = DATA_DIR / "evaluation_results.csv"

# If you want a simple admin view
ADMIN_PIN = st.secrets.get("ADMIN_PIN", "0000")

# -------------------------
# Helpers
# -------------------------
def list_audio_files(folder: Path):
    if not folder.exists():
        return []
    exts = {".wav", ".mp3", ".m4a", ".ogg"}
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]
    return sorted(files)

def init_session():
    if "participant_id" not in st.session_state:
        st.session_state.participant_id = str(uuid.uuid4())[:8]
    if "mode" not in st.session_state:
        st.session_state.mode = "sequential"  # or "simultaneous"
    if "queue" not in st.session_state:
        st.session_state.queue = []
    if "current" not in st.session_state:
        st.session_state.current = None
    if "history" not in st.session_state:
        st.session_state.history = []
    if "started_at" not in st.session_state:
        st.session_state.started_at = dt.datetime.now().isoformat(timespec="seconds")

def build_queue(mode: str, seed: int | None = None):
    rng = random.Random(seed)
    folder = SEQ_DIR if mode == "sequential" else SIM_DIR
    files = list_audio_files(folder)
    rng.shuffle(files)
    return files

def next_item():
    if not st.session_state.queue:
        st.session_state.current = None
        return
    st.session_state.current = st.session_state.queue.pop(0)

def ensure_csv_header():
    if CSV_PATH.exists():
        return
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "timestamp",
            "participant_id",
            "mode",
            "filename",
            "valence",
            "arousal",
            "difficulty",
            "notes",
            "replays",
            "session_started_at",
        ])

def append_result(row: dict):
    ensure_csv_header()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            row["timestamp"],
            row["participant_id"],
            row["mode"],
            row["filename"],
            row["valence"],
            row["arousal"],
            row["difficulty"],
            row["notes"],
            row["replays"],
            row["session_started_at"],
        ])

def parse_scale_name(filename: str):
    # Optional: infer scale from filename prefix before first "_" (e.g., "D_control_xxx.wav")
    base = Path(filename).stem
    return base.split("_")[0] if "_" in base else base

# -------------------------
# UI
# -------------------------
st.set_page_config(page_title=APP_TITLE, layout="centered")
init_session()

st.title(APP_TITLE)
st.caption("SEQ/SIM 音源を聴いて、Valence / Arousal / Difficulty を評価してください。")

with st.sidebar:
    st.subheader("Settings")
    st.text_input("Participant ID", key="participant_id")
    st.selectbox("Mode", ["sequential", "simultaneous"], key="mode")
    seed = st.number_input("Random seed (optional)", min_value=0, value=0, step=1)
    if st.button("Start / Reset queue"):
        st.session_state.queue = build_queue(st.session_state.mode, seed if seed != 0 else None)
        st.session_state.history = []
        st.session_state.started_at = dt.datetime.now().isoformat(timespec="seconds")
        next_item()

    st.divider()
    st.subheader("Admin")
    pin = st.text_input("Admin PIN", type="password")
    if pin == ADMIN_PIN:
        if CSV_PATH.exists():
            df = pd.read_csv(CSV_PATH)
            st.write(df.tail(20))
            st.download_button(
                "Download CSV",
                data=CSV_PATH.read_bytes(),
                file_name="evaluation_results.csv",
                mime="text/csv",
            )
        else:
            st.info("No data yet.")

# Ensure we have something loaded
if st.session_state.current is None:
    # auto-init queue if empty
    if not st.session_state.queue:
        st.session_state.queue = build_queue(st.session_state.mode, None)
    next_item()

current = st.session_state.current
if current is None:
    st.success("All done! 🎉 ありがとうございました。")
    st.stop()

# Audio section
st.subheader("Now playing")
st.write(f"**File:** `{current.name}`")
st.write(f"**Scale guess:** `{parse_scale_name(current.name)}`")
audio_bytes = current.read_bytes()

if "replays" not in st.session_state:
    st.session_state.replays = 0

col1, col2 = st.columns([1, 1])
with col1:
    st.audio(audio_bytes)
with col2:
    if st.button("Replay (+1)"):
        st.session_state.replays += 1
        st.experimental_rerun()

st.divider()

# Rating form
with st.form("rating_form", clear_on_submit=True):
    st.markdown("### Rate it")
    valence = st.slider("Valence (unpleasant → pleasant)", 1, 7, 4)
    arousal = st.slider("Arousal (calm → excited)", 1, 7, 4)
    difficulty = st.slider("Difficulty / Strangeness (easy → hard)", 1, 7, 4)
    notes = st.text_area("Notes (optional)", placeholder="気づいたこと / 印象など")

    submitted = st.form_submit_button("Submit & Next")
    if submitted:
        row = {
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "participant_id": st.session_state.participant_id,
            "mode": st.session_state.mode,
            "filename": current.name,
            "valence": int(valence),
            "arousal": int(arousal),
            "difficulty": int(difficulty),
            "notes": notes.strip(),
            "replays": int(st.session_state.replays),
            "session_started_at": st.session_state.started_at,
        }
        append_result(row)
        st.session_state.history.append(row)
        st.session_state.replays = 0
        next_item()
        st.success("Saved!")
        time.sleep(0.2)
        st.experimental_rerun()

# Progress
total = len(list_audio_files(SEQ_DIR if st.session_state.mode == "sequential" else SIM_DIR))
done = len(st.session_state.history)
left = len(st.session_state.queue) + (1 if st.session_state.current else 0)

st.caption(f"Progress: {done}/{total} rated | Remaining in queue: {left}")

