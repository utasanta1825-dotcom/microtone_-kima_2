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
# 設定（あなたのGitHub構造）
# =========================
BASE_DIR = "assets"
SEQ_DIR = os.path.join(BASE_DIR, "sequential")
SIM_DIR_BASIC = os.path.join(BASE_DIR, "simultaneous_basic")
SIM_DIR_COLORS = os.path.join(BASE_DIR, "simultaneous_colors")

BLOCKS = [
    {"key": "SEQ", "label": "順番再生（SEQ）", "dir": SEQ_DIR},
    {"key": "basic", "label": "同時音（basic / prog_triad_basic）", "dir": SIM_DIR_BASIC},
    {"key": "colors", "label": "同時音（colors / set_root0_colors）", "dir": SIM_DIR_COLORS},
]

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
            "Block",        # SEQ / basic / colors
            "Item_ID",      # A_balanced など
            "File",
            "Valence",
            "Arousal",
            "Diff",
            "PlayCount",
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
    ws_results, _ = get_sheets()
    ws_results.append_row(row, value_input_option="USER_ENTERED")

def append_participant_row(row):
    _, ws_profile = get_sheets()
    ws_profile.append_row(row, value_input_option="USER_ENTERED")

def infer_item_id(filename: str) -> str:
    """
    先頭キーを Item_ID にする
    例:
      A_balanced_SEQ_scale.wav -> A_balanced
      A_balanced_SIMSEQ_prog_triad_basic.wav -> A_balanced
      A_balanced_SIMSEQ_set_root0_colors.wav -> A_balanced
    """
    m = re.match(r"^(.+?)_(SEQ|SIM)", filename)
    return m.group(1) if m else os.path.splitext(filename)[0]

def build_trials_for_block(block_key: str, block_dir: str, wav_files: list[str]) -> list[dict]:
    """
    1ブロック分の trials を作る
    trials: [{"block":..., "item_id":..., "path":..., "filename":...}, ...]
    """
    items = []
    for fn in wav_files:
        item_id = infer_item_id(fn)
        items.append({
            "block": block_key,
            "item_id": item_id,
            "path": os.path.join(block_dir, fn),
            "filename": fn,
        })
    return items

# =========================
# UI / ページ設定
# =========================
st.set_page_config(page_title="音律評価実験（3ブロック）", layout="centered")

VALENCE_LABELS = {
    5: "とてもよい",
    4: "よい",
    3: "ふつう",
    2: "あまりよくない",
    1: "悪い",
}
AROUSAL_LABELS = {
    5: "とても緊張感がある",
    4: "緊張感がある",
    3: "どちらでもない",
    2: "あまり緊張感がない",
    1: "全く緊張感がない",
}
DIFF_LABELS = {
    5: "とても違和感がある",
    4: "違和感がある",
    3: "どちらでもない",
    2: "あまり違和感がない",
    1: "全く違和感がない",
}

st.markdown("""
<style>
.big-title {font-size: 28px; font-weight: 800; margin-bottom: 6px;}
.sub {color:#555; margin-bottom: 16px;}
.card {padding:14px; background:#fff; border:1px solid #e5e5e5; border-radius:14px; margin: 12px 0;}
.badge {display:inline-block; padding:3px 10px; border-radius:999px; background:#f3f4f6; font-size:12px; margin-left:8px;}
.small {color:#666; font-size: 13px;}
hr {border:none; border-top:1px solid #eee; margin: 14px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='big-title'>音律評価実験（3ブロック）</div>", unsafe_allow_html=True)


# =========================
# セッション初期化
# =========================
if "participant_id" not in st.session_state:
    st.session_state.participant_id = ""
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if "profile_done" not in st.session_state:
    st.session_state.profile_done = False

# 3ブロック試行リスト
if "trials" not in st.session_state:
    st.session_state.trials = []
if "trial_index" not in st.session_state:
    st.session_state.trial_index = 0

# 再生状態
if "played" not in st.session_state:
    st.session_state.played = False
if "play_count" not in st.session_state:
    st.session_state.play_count = 0

# =========================
# 参加者ID入力
# =========================
if (not st.session_state.participant_id) and (not st.session_state.is_admin):
    st.markdown("### 実験開始")
    pid = st.text_input("参加者ID（管理者PINもここ）")
    if pid:
        if pid == ADMIN_PIN:
            st.session_state.is_admin = True
            st.rerun()
        elif re.match(r"^[A-Za-z0-9_]+$", pid):
            st.session_state.participant_id = pid
            st.rerun()
        else:
            st.error("英数字と _ のみ使用できます。")
    st.stop()

# =========================
# 管理者モード
# =========================
if st.session_state.is_admin:
    st.markdown("## 管理者モード")
    init_csv()
    init_participants_csv()

    if os.path.exists(LOCAL_CSV):
        with open(LOCAL_CSV, "rb") as f:
            st.download_button("⬇️ 評価CSV（evaluation_results.csv）をダウンロード", f, file_name=os.path.basename(LOCAL_CSV), mime="text/csv")
        try:
            df = pd.read_csv(LOCAL_CSV)
            st.info(f"評価 記録件数：{len(df)}")
        except Exception:
            st.info("評価CSV：まだデータがありません。")

    if os.path.exists(PARTICIPANTS_CSV):
        with open(PARTICIPANTS_CSV, "rb") as f:
            st.download_button("⬇️ 参加者CSV（participants.csv）をダウンロード", f, file_name=os.path.basename(PARTICIPANTS_CSV), mime="text/csv")
        try:
            df2 = pd.read_csv(PARTICIPANTS_CSV)
            st.info(f"参加者属性 記録件数：{len(df2)}")
        except Exception:
            st.info("参加者CSV：まだデータがありません。")

    if st.button("管理者モードを終了"):
        st.session_state.clear()
        st.rerun()
    st.stop()

participant_id = st.session_state.participant_id

# =========================
# 背景アンケート
# =========================
if (not st.session_state.profile_done):
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("## 最初にいくつか質問（30秒）")
    st.markdown("<div class='small'>音の感じ方に影響する可能性があるため、自己申告で回答してください。未回答でもOKです。</div>", unsafe_allow_html=True)
    st.markdown("---")

    tuning_exp = st.radio(
        "Q1. 自分で楽器のチューニング（調弦/調整）を行った経験はありますか？",
        ["未回答", "よくする", "たまにする", "過去にしたことがある", "ない"],
        index=0,
        key="tuning_exp",
    )

    tuning_by_ear = st.radio(
        "Q2. チューニングのとき、耳で音程を合わせることはありますか？",
        ["未回答", "耳で合わせることが多い", "チューナー中心だが耳でも確認", "チューナー任せ/他人に任せる", "ない"],
        index=0,
        key="tuning_by_ear",
    )

    tuning_instruments = st.text_input(
        "Q3. チューニングする楽器があれば（例：ギター、バイオリン、管楽器、ドラムなど）",
        value=st.session_state.get("tuning_instruments", ""),
        key="tuning_instruments",
        placeholder="未回答でもOK",
    )

    cA, cB = st.columns([1, 1])
    with cA:
        if st.button("この回答で開始する ▶"):
            init_participants_csv()
            ts = datetime.datetime.utcnow().isoformat()
            row = [participant_id, ts, tuning_exp, tuning_by_ear, tuning_instruments.strip()]
            append_participant_row(row)
            st.session_state.profile_done = True
            st.rerun()

    with cB:
        if st.button("未回答で開始する ▶"):
            init_participants_csv()
            ts = datetime.datetime.utcnow().isoformat()
            row = [participant_id, ts, "未回答", "未回答", ""]
            append_participant_row(row)
            st.session_state.profile_done = True
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# =========================
# 音源ロード & trials 作成（初回だけ）
# =========================
def build_all_trials():
    trials_all = []

    for b in BLOCKS:
        d_full, wavs = list_wavs(b["dir"])
        if d_full is None:
            st.error(f"音源フォルダが見つかりません: {b['dir']}")
            st.stop()
        if not wavs:
            st.error(f"音源がありません: {b['dir']}")
            st.stop()

        block_trials = build_trials_for_block(b["key"], b["dir"], wavs)

        # ブロック内ランダム（ここが重要）
        random.shuffle(block_trials)

        trials_all.extend(block_trials)

    return trials_all

if not st.session_state.trials:
    init_csv()
    st.session_state.trials = build_all_trials()
    st.session_state.trial_index = 0
    st.session_state.played = False
    st.session_state.play_count = 0

# =========================
# 進捗
# =========================
idx = st.session_state.trial_index
total = len(st.session_state.trials)

if idx >= total:
    st.success("🎉 全ブロックの評価が完了しました！ありがとうございました！")
    st.stop()

trial = st.session_state.trials[idx]

# ブロック表示用
block_info = next((b for b in BLOCKS if b["key"] == trial["block"]), None)
block_label = block_info["label"] if block_info else trial["block"]

st.markdown(
    f"**参加者ID:** `{participant_id}`　"
    f"<span class='badge'>{idx+1} / {total} 回</span>",
    unsafe_allow_html=True
)
st.progress((idx + 1) / total)


# ブロック境界の案内（最初の要素が切り替わった時にわかるように）
if idx > 0:
    prev_block = st.session_state.trials[idx - 1]["block"]
    if prev_block != trial["block"]:
        st.info(f"ブロックが切り替わりました：{prev_block} → {trial['block']}")

# キャッシュクリアボタン
if st.button("🔄 再生状態をリセット（この1試行だけ）"):
    st.session_state.played = False
    st.session_state.play_count = 0
    st.rerun()

# =========================
# 試行UI
# =========================
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.markdown("## 音源を聴いて評価")
st.markdown("<div class='small'>ボタンで再生を有効化してから音を聴き、評価してください。</div>", unsafe_allow_html=True)
st.markdown("---")

audio_bytes = read_audio_bytes(trial["path"])
if audio_bytes is None:
    st.error("音源の読み込みに失敗しました。パスを確認してください。")
    st.write("PATH:", trial["path"])
    st.stop()

if st.button("▶ 再生を有効化"):
    st.session_state.played = True
    st.session_state.play_count += 1

if st.session_state.played:
    st.audio(audio_bytes, format="audio/wav")
else:
    st.info("まず上のボタンで再生を有効化してください。")

st.caption(f"再生回数：{st.session_state.play_count}")
st.markdown("<hr>", unsafe_allow_html=True)

st.markdown("### 評価")
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("**聴き心地**")
    st.radio(
        label="",
        options=[5, 4, 3, 2, 1],
        index=2,
        key="valence",
        format_func=lambda x: VALENCE_LABELS[x],
    )

with c2:
    st.markdown("**緊張**")
    st.radio(
        label="",
        options=[5, 4, 3, 2, 1],
        index=2,
        key="arousal",
        format_func=lambda x: AROUSAL_LABELS[x],
    )

with c3:
    st.markdown("**違和感**")
    st.radio(
        label="",
        options=[5, 4, 3, 2, 1],
        index=2,
        key="diff",
        format_func=lambda x: DIFF_LABELS[x],
    )

if st.button("評価を記録して次へ", disabled=not st.session_state.played):
    timestamp = datetime.datetime.utcnow().isoformat()

    row = [
        participant_id,
        timestamp,
        trial["block"],
        trial["item_id"],
        trial["filename"],
        st.session_state["valence"],
        st.session_state["arousal"],
        st.session_state["diff"],
        st.session_state.play_count,
    ]
    append_row(row)

    # 次へ
    st.session_state.trial_index += 1
    st.session_state.played = False
    st.session_state.play_count = 0

    # 前回値残り対策
    for k in ["valence", "arousal", "diff"]:
        if k in st.session_state:
            del st.session_state[k]

    st.rerun()

st.markdown("</div>", unsafe_allow_html=True)
