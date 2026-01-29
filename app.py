import streamlit as st
import os
import csv
import random
import re
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# 設定（GitHub構造に合わせる）
# =========================
BASE_DIR = "assets"
SEQ_DIR = os.path.join(BASE_DIR, "sequential", )
SIM_DIR = os.path.join(BASE_DIR, "simultaneous")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

LOCAL_CSV = os.path.join(DATA_DIR, "evaluation_results.csv")
PARTICIPANTS_CSV = os.path.join(DATA_DIR, "participants.csv")
ADMIN_PIN = "0000"

# =========================
# Google Sheets
# =========================
@st.cache_resource
def get_sheets():
    info = dict(st.secrets["gsheets"]["service_account"])
    info["private_key"] = info["private_key"].replace("\\n", "\n")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(st.secrets["gsheets"]["spreadsheet_id"])
    return sh.worksheet("results"), sh.worksheet("participants")

# =========================
# ユーティリティ
# =========================
def abs_path(rel_path: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel_path)

def list_wavs(rel_dir: str):
    full_dir = abs_path(rel_dir)
    if not os.path.exists(full_dir):
        return None, []
    files = sorted([f for f in os.listdir(full_dir) if f.lower().endswith(".wav")])
    return full_dir, files

def read_audio_bytes(rel_path: str):
    try:
        with open(abs_path(rel_path), "rb") as f:
            return f.read()
    except Exception:
        return None

def init_csv():
    if not os.path.exists(LOCAL_CSV):
        header = [
            "Participant_ID",
            "Timestamp_UTC",
            "Pair_ID",
            "SEQ_File",
            "SIM_File",
            "SEQ_Valence",
            "SEQ_Arousal",
            "SEQ_Diff",
            "SEQ_PlayCount",
            "SIM_Valence",
            "SIM_Arousal",
            "SIM_Diff",
            "SIM_PlayCount",
        ]
        with open(LOCAL_CSV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def init_participants_csv():
    if not os.path.exists(PARTICIPANTS_CSV):
        header = [
            "Participant_ID",
            "Timestamp_UTC",
            "Tuning_Exp",
            "Tuning_ByEar",
            "Tuning_Instruments",
        ]
        with open(PARTICIPANTS_CSV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def append_row(row):
    init_csv()
    with open(LOCAL_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
    ws_results, _ = get_sheets()
    ws_results.append_row(row, value_input_option="USER_ENTERED")

def append_participant_row(row):
    init_participants_csv()
    with open(PARTICIPANTS_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
    _, ws_profile = get_sheets()
    ws_profile.append_row(row, value_input_option="USER_ENTERED")

# =========================
# ペア作成（今の命名対応）
# =========================
def make_pairs(seq_files, sim_files):
    def key_from_seq(fn):
        m = re.match(r"^(.+?)_SEQ", fn)
        return m.group(1) if m else None

    def key_from_sim(fn):
        m = re.match(r"^(.+?)_SIM", fn)
        return m.group(1) if m else None

    seq_map = {}
    for f in seq_files:
        k = key_from_seq(f)
        if k:
            seq_map[k] = f

    sim_map = {}
    for f in sim_files:
        k = key_from_sim(f)
        if k:
            sim_map[k] = f

    pair_ids = sorted(set(seq_map.keys()) & set(sim_map.keys()))
    pairs = []
    for pid in pair_ids:
        pairs.append({
            "pair_id": pid,
            "SEQ": os.path.join(SEQ_DIR, seq_map[pid]),
            "SIM": os.path.join(SIM_DIR, sim_map[pid]),
            "SEQ_name": seq_map[pid],
            "SIM_name": sim_map[pid],
        })
    return pairs

# =========================
# UI
# =========================
st.set_page_config(page_title="音律評価実験（2音）", layout="centered")

VALENCE_LABELS = {5:"とてもよい",4:"よい",3:"ふつう",2:"あまりよくない",1:"悪い"}
AROUSAL_LABELS = {5:"とても緊張感がある",4:"緊張感がある",3:"どちらでもない",2:"あまり緊張感がない",1:"全く緊張感がない"}
DIFF_LABELS = {5:"とても違和感がある",4:"違和感がある",3:"どちらでもない",2:"あまり違和感がない",1:"全く違和感がない"}

st.markdown("## 🎧 音律評価実験（2音）")
st.markdown("順番再生（SEQ）→ 同時再生（SIM）を評価します。")

# =========================
# セッション初期化
# =========================
for k, v in {
    "participant_id": "",
    "is_admin": False,
    "pair_order": [],
    "pair_index": 0,
    "phase": "seq",
    "played_seq": False,
    "played_sim": False,
    "play_count_seq": 0,
    "play_count_sim": 0,
    "profile_done": False,
    "seq_saved": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================
# 参加者ID
# =========================
if not st.session_state.participant_id and not st.session_state.is_admin:
    pid = st.text_input("参加者ID（管理者PINもここ）")
    if pid:
        if pid == ADMIN_PIN:
            st.session_state.is_admin = True
            st.rerun()
        elif re.match(r"^[A-Za-z0-9_]+$", pid):
            st.session_state.participant_id = pid
            st.rerun()
        else:
            st.error("英数字と _ のみ使用できます")
    st.stop()

participant_id = st.session_state.participant_id

# =========================
# 音源ロード
# =========================
seq_dir, seq_files = list_wavs(SEQ_DIR)
sim_dir, sim_files = list_wavs(SIM_DIR)

if seq_dir is None or sim_dir is None:
    st.error("音源フォルダが見つかりません")
    st.stop()

pairs = make_pairs(seq_files, sim_files)
if not pairs:
    st.error("SEQ / SIM のペアが作れません")
    st.stop()

if not st.session_state.pair_order:
    st.session_state.pair_order = random.sample(range(len(pairs)), len(pairs))
    init_csv()
    init_participants_csv()

idx = st.session_state.pair_index
if idx >= len(pairs):
    st.success("🎉 全ての評価が完了しました！")
    st.stop()

pair = pairs[st.session_state.pair_order[idx]]

# =========================
# SEQ
# =========================
if st.session_state.phase == "seq":
    st.markdown(f"### SEQ : {pair['pair_id']}")
    audio = read_audio_bytes(pair["SEQ"])
    if st.button("▶ 再生"):
        st.session_state.played_seq = True
        st.session_state.play_count_seq += 1
    if st.session_state.played_seq:
        st.audio(audio)

    v = st.radio("聴き心地", [5,4,3,2,1], index=2, format_func=lambda x: VALENCE_LABELS[x])
    a = st.radio("緊張", [5,4,3,2,1], index=2, format_func=lambda x: AROUSAL_LABELS[x])
    d = st.radio("違和感", [5,4,3,2,1], index=2, format_func=lambda x: DIFF_LABELS[x])

    if st.button("SIMへ"):
        st.session_state.seq_saved = (v, a, d)
        st.session_state.phase = "sim"
        st.session_state.played_sim = False
        st.rerun()

# =========================
# SIM
# =========================
else:
    st.markdown(f"### SIM : {pair['pair_id']}")
    audio = read_audio_bytes(pair["SIM"])
    if st.button("▶ 再生"):
        st.session_state.played_sim = True
        st.session_state.play_count_sim += 1
    if st.session_state.played_sim:
        st.audio(audio)

    v = st.radio("聴き心地", [5,4,3,2,1], index=2, format_func=lambda x: VALENCE_LABELS[x])
    a = st.radio("緊張", [5,4,3,2,1], index=2, format_func=lambda x: AROUSAL_LABELS[x])
    d = st.radio("違和感", [5,4,3,2,1], index=2, format_func=lambda x: DIFF_LABELS[x])

    if st.button("記録して次へ"):
        ts = datetime.datetime.utcnow().isoformat()
        sv, sa, sd = st.session_state.seq_saved

        append_row([
            participant_id,
            ts,
            pair["pair_id"],
            pair["SEQ_name"],
            pair["SIM_name"],
            sv, sa, sd, st.session_state.play_count_seq,
            v, a, d, st.session_state.play_count_sim,
        ])

        st.session_state.pair_index += 1
        st.session_state.phase = "seq"
        st.session_state.played_seq = False
        st.session_state.played_sim = False
        st.session_state.play_count_seq = 0
        st.session_state.play_count_sim = 0
        st.session_state.seq_saved = None
        st.rerun()
