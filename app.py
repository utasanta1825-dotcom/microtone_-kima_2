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
# 設定
# =========================
BASE_DIR = "微分音"
SEQ_DIR = os.path.join(BASE_DIR, "sequential")     # *_seq.wav
SIM_DIR = os.path.join(BASE_DIR, "simultaneous")   # *_sim.wav

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

LOCAL_CSV = os.path.join(DATA_DIR, "evaluation_results.csv")
PARTICIPANTS_CSV = os.path.join(DATA_DIR, "participants.csv")  # 参加者属性
ADMIN_PIN = "0000"

# =========================
# Google Sheets
# =========================
@st.cache_resource
def get_sheets():
    # secrets はこういう形を想定：
    # [gsheets]
    # spreadsheet_id = "...."
    # [gsheets.service_account]
    # ... service account json fields ...
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

def append_row_local(row):
    init_csv()
    with open(LOCAL_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

def append_participant_row_local(row):
    init_participants_csv()
    with open(PARTICIPANTS_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

def append_row(row):
    # まずローカルにも保存（保険）
    append_row_local(row)
    # Sheetsへ
    ws_results, _ = get_sheets()
    ws_results.append_row(row, value_input_option="USER_ENTERED")

def append_participant_row(row):
    # まずローカルにも保存（保険）
    append_participant_row_local(row)
    # Sheetsへ
    _, ws_profile = get_sheets()
    ws_profile.append_row(row, value_input_option="USER_ENTERED")

def make_pairs(seq_files, sim_files):
    seq = {f.replace("_seq.wav", ""): f for f in seq_files if f.endswith("_seq.wav")}
    sim = {f.replace("_sim.wav", ""): f for f in sim_files if f.endswith("_sim.wav")}

    pair_ids = sorted(set(seq.keys()) & set(sim.keys()))
    pairs = []
    for pid in pair_ids:
        pairs.append({
            "pair_id": pid,
            "SEQ": os.path.join(SEQ_DIR, seq[pid]),
            "SIM": os.path.join(SIM_DIR, sim[pid]),
            "SEQ_name": seq[pid],
            "SIM_name": sim[pid],
        })
    return pairs

# =========================
# UI / ページ設定
# =========================
st.set_page_config(page_title="音律評価実験（2音）", layout="centered")

VALENCE_LABELS = {5:"とてもよい",4:"よい",3:"ふつう",2:"あまりよくない",1:"悪い"}
AROUSAL_LABELS = {5:"とても緊張感がある",4:"緊張感がある",3:"どちらでもない",2:"あまり緊張感がない",1:"全く緊張感がない"}
DIFF_LABELS = {5:"とても違和感がある",4:"違和感がある",3:"どちらでもない",2:"あまり違和感がない",1:"全く違和感がない"}

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

st.markdown("<div class='big-title'>音律評価実験（2音）</div>", unsafe_allow_html=True)
st.markdown("<div class='sub'>順番再生と同時再生を別々に評価します。</div>", unsafe_allow_html=True)

# =========================
# セッション初期化
# =========================
if "participant_id" not in st.session_state:
    st.session_state.participant_id = ""
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if "pair_order" not in st.session_state:
    st.session_state.pair_order = []
if "pair_index" not in st.session_state:
    st.session_state.pair_index = 0

if "phase" not in st.session_state:
    st.session_state.phase = "seq"

if "played_seq" not in st.session_state:
    st.session_state.played_seq = False
if "played_sim" not in st.session_state:
    st.session_state.played_sim = False

if "play_count_seq" not in st.session_state:
    st.session_state.play_count_seq = 0
if "play_count_sim" not in st.session_state:
    st.session_state.play_count_sim = 0

if "profile_done" not in st.session_state:
    st.session_state.profile_done = False

# seq評価をsim画面でも確実に保存できるように退避
if "seq_saved" not in st.session_state:
    st.session_state.seq_saved = None  # (valence, arousal, diff)

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
            st.download_button("⬇️ 評価CSV（evaluation_results.csv）をダウンロード", f, file_name="evaluation_results.csv", mime="text/csv")
        try:
            df = pd.read_csv(LOCAL_CSV)
            st.info(f"評価 記録件数：{len(df)}")
        except Exception:
            st.info("評価CSV：まだデータがありません。")

    if os.path.exists(PARTICIPANTS_CSV):
        with open(PARTICIPANTS_CSV, "rb") as f:
            st.download_button("⬇️ 参加者CSV（participants.csv）をダウンロード", f, file_name="participants.csv", mime="text/csv")
        try:
            df2 = pd.read_csv(PARTICIPANTS_CSV)
            st.info(f"参加者属性 記録件数：{len(df2)}")
        except Exception:
            st.info("参加者CSV：まだデータがありません。")

    st.markdown("---")
    st.caption("※ Google Sheets には results / participants シートへ書き込まれます。")

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
    st.markdown("<hr>", unsafe_allow_html=True)

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
        "Q3. チューニングする楽器があれば（例：ギター、バイオリン、管楽器など）",
        value=st.session_state.get("tuning_instruments", ""),
        key="tuning_instruments",
        placeholder="未回答でもOK",
    )

    cA, cB = st.columns([1, 1])
    with cA:
        if st.button("この回答で開始する ▶"):
            ts = datetime.datetime.utcnow().isoformat()
            append_participant_row([participant_id, ts, tuning_exp, tuning_by_ear, tuning_instruments.strip()])
            st.session_state.profile_done = True
            st.rerun()
    with cB:
        if st.button("未回答で開始する ▶"):
            ts = datetime.datetime.utcnow().isoformat()
            append_participant_row([participant_id, ts, "未回答", "未回答", ""])
            st.session_state.profile_done = True
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# =========================
# 音源ロード（seq / sim）
# =========================
seq_dir_full, seq_files = list_wavs(SEQ_DIR)
sim_dir_full, sim_files = list_wavs(SIM_DIR)

if seq_dir_full is None:
    st.error(f"音源フォルダが見つかりません: {SEQ_DIR}")
    st.stop()
if sim_dir_full is None:
    st.error(f"音源フォルダが見つかりません: {SIM_DIR}")
    st.stop()

pairs = make_pairs(seq_files, sim_files)
if not pairs:
    st.error("ペアが作れませんでした。*_seq.wav と *_sim.wav の命名が揃っているか確認してください。")
    st.stop()

if not st.session_state.pair_order:
    st.session_state.pair_order = random.sample(range(len(pairs)), len(pairs))
    st.session_state.pair_index = 0
    st.session_state.phase = "seq"
    st.session_state.played_seq = False
    st.session_state.played_sim = False
    st.session_state.play_count_seq = 0
    st.session_state.play_count_sim = 0
    init_csv()
    init_participants_csv()

idx = st.session_state.pair_index
total = len(pairs)

if idx >= total:
    st.success("🎉 全ペアの評価が完了しました！ありがとうございました！")
    st.stop()

pair = pairs[st.session_state.pair_order[idx]]
st.markdown(f"**参加者ID:** `{participant_id}`　<span class='badge'>{idx+1} / {total} ペア</span>", unsafe_allow_html=True)
st.progress((idx + 1) / total)

phase = st.session_state.phase

# =========================
# ① seq フェーズ
# =========================
if phase == "seq":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("## ① 順番再生を評価")
    st.markdown("<div class='small'>*_seq.wav を聴いて評価します。</div>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    seq_bytes = read_audio_bytes(pair["SEQ"])
    if seq_bytes is None:
        st.error("seqファイルの読み込みに失敗しました。")
        st.write("SEQ:", pair["SEQ"])
        st.stop()

    if st.button("▶ 再生を有効化"):
        st.session_state.played_seq = True
        st.session_state.play_count_seq += 1

    if st.session_state.played_seq:
        st.audio(seq_bytes, format="audio/wav")
    else:
        st.info("まず上のボタンで再生を有効化してください。")

    st.caption(f"seq 再生回数：{st.session_state.play_count_seq}")
    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown("### 評価")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**聴き心地**")
        st.radio("", [5,4,3,2,1], index=2, key="seq_valence", format_func=lambda x: VALENCE_LABELS[x])
    with c2:
        st.markdown("**緊張**")
        st.radio("", [5,4,3,2,1], index=2, key="seq_arousal", format_func=lambda x: AROUSAL_LABELS[x])
    with c3:
        st.markdown("**違和感**")
        st.radio("", [5,4,3,2,1], index=2, key="seq_diff", format_func=lambda x: DIFF_LABELS[x])

    if st.button("seqの評価を確定して、simへ", disabled=not st.session_state.played_seq):
        st.session_state.seq_saved = (st.session_state["seq_valence"], st.session_state["seq_arousal"], st.session_state["seq_diff"])
        st.session_state.phase = "sim"
        st.session_state.played_sim = False
        st.session_state.play_count_sim = 0
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# ② sim フェーズ
# =========================
else:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("## ② 同時音を評価")
    st.markdown("<div class='small'>*_sim.wav を聴いて評価します。</div>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    sim_bytes = read_audio_bytes(pair["SIM"])
    if sim_bytes is None:
        st.error("simファイルの読み込みに失敗しました。")
        st.write("SIM:", pair["SIM"])
        st.stop()

    if st.button("▶ 再生を有効化"):
        st.session_state.played_sim = True
        st.session_state.play_count_sim += 1

    if st.session_state.played_sim:
        st.audio(sim_bytes, format="audio/wav")
    else:
        st.info("まず上のボタンで再生を有効化してください。")

    st.caption(f"sim 再生回数：{st.session_state.play_count_sim}")
    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown("### 評価（sim）")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**聴き心地**")
        sim_valence = st.radio("", [5,4,3,2,1], index=2, key="sim_valence", format_func=lambda x: VALENCE_LABELS[x])
    with c2:
        st.markdown("**緊張**")
        sim_arousal = st.radio("", [5,4,3,2,1], index=2, key="sim_arousal", format_func=lambda x: AROUSAL_LABELS[x])
    with c3:
        st.markdown("**違和感**")
        sim_diff = st.radio("", [5,4,3,2,1], index=2, key="sim_diff", format_func=lambda x: DIFF_LABELS[x])

    if st.button("評価を記録して次のペアへ", disabled=not st.session_state.played_sim):
        timestamp = datetime.datetime.utcnow().isoformat()

        if st.session_state.seq_saved is None:
            st.error("seqの評価が見つかりません。seq画面に戻ってやり直してください。")
            st.stop()

        seq_valence, seq_arousal, seq_diff = st.session_state.seq_saved

        row = [
            participant_id,
            timestamp,
            pair["pair_id"],
            pair["SEQ_name"],
            pair["SIM_name"],
            seq_valence,
            seq_arousal,
            seq_diff,
            st.session_state.play_count_seq,
            sim_valence,
            sim_arousal,
            sim_diff,
            st.session_state.play_count_sim,
        ]
        append_row(row)

        # 次ペアへ：状態リセット
        st.session_state.pair_index += 1
        st.session_state.phase = "seq"
        st.session_state.played_seq = False
        st.session_state.played_sim = False
        st.session_state.play_count_seq = 0
        st.session_state.play_count_sim = 0

        # 評価値残り対策
        for k in ["seq_valence", "seq_arousal", "seq_diff", "sim_valence", "sim_arousal", "sim_diff"]:
            if k in st.session_state:
                del st.session_state[k]

        st.session_state.seq_saved = None
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
