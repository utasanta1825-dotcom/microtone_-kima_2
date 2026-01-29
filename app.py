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
# 設定（あなたのGitHub構造に合わせる）
# =========================
BASE_DIR = "assets"
SEQ_DIR = os.path.join(BASE_DIR, "sequential")

SIM_CONDS = {
    "basic": os.path.join(BASE_DIR, "simultaneous_basic"),
    "colors": os.path.join(BASE_DIR, "simultaneous_colors"),
}

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

LOCAL_CSV = os.path.join(DATA_DIR, "evaluation_results.csv")
PARTICIPANTS_CSV = os.path.join(DATA_DIR, "participants.csv")
ADMIN_PIN = "0000"

COND_LABEL = {
    "basic": "同時音（basic / prog_triad_basic）",
    "colors": "同時音（colors / set_root0_colors）",
}

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
            "Condition",          # ★追加
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
    ws_results, _ = get_sheets()
    ws_results.append_row(row, value_input_option="USER_ENTERED")

def append_participant_row(row):
    _, ws_profile = get_sheets()
    ws_profile.append_row(row, value_input_option="USER_ENTERED")

# =========================
# ペア作成（2条件：basic/colors）
# =========================
def make_pairs_multi(seq_files, sim_files_by_cond):
    """
    seq_files: sequentialのwav一覧
    sim_files_by_cond: {"basic":[...], "colors":[...]}
    返り値: pairs = [{"pair_id":..., "condition":..., "SEQ":..., "SIM":..., ...}, ...]
    """

    def key_from_seq(fn: str):
        # 例: A_balanced_SEQ_scale.wav -> A_balanced
        m = re.match(r"^(.+?)_SEQ", fn)
        return m.group(1) if m else None

    def key_from_sim(fn: str):
        # 例: A_balanced_SIMSEQ_prog_triad_basic.wav -> A_balanced
        m = re.match(r"^(.+?)_SIM", fn)
        return m.group(1) if m else None

    seq_map = {}
    for f in seq_files:
        k = key_from_seq(f)
        if k:
            seq_map[k] = f

    pairs = []
    for cond, sim_files in sim_files_by_cond.items():
        sim_map = {}
        for f in sim_files:
            k = key_from_sim(f)
            if k:
                sim_map[k] = f

        common = sorted(set(seq_map.keys()) & set(sim_map.keys()))
        for pid in common:
            pairs.append({
                "pair_id": pid,
                "condition": cond,
                "SEQ": os.path.join(SEQ_DIR, seq_map[pid]),
                "SIM": os.path.join(SIM_CONDS[cond], sim_map[pid]),
                "SEQ_name": seq_map[pid],
                "SIM_name": sim_map[pid],
            })

    return pairs

# =========================
# UI / ページ設定
# =========================
st.set_page_config(page_title="音律評価実験（2音）", layout="centered")

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

st.markdown("<div class='big-title'>音律評価実験（2音）</div>", unsafe_allow_html=True)
st.markdown("<div class='sub'>順番再生（SEQ）→ 同時音（SIM）を別々に評価します（SIMは2条件）。</div>", unsafe_allow_html=True)

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
# 音源ロード
# =========================
seq_dir_full, seq_files = list_wavs(SEQ_DIR)
if seq_dir_full is None:
    st.error(f"音源フォルダが見つかりません: {SEQ_DIR}")
    st.stop()

sim_files_by_cond = {}
for cond, sim_dir in SIM_CONDS.items():
    d_full, files = list_wavs(sim_dir)
    if d_full is None:
        st.error(f"音源フォルダが見つかりません: {sim_dir}")
        st.stop()
    sim_files_by_cond[cond] = files

pairs = make_pairs_multi(seq_files, sim_files_by_cond)
if not pairs:
    st.error("ペアが作れませんでした。SEQ/SIMの命名（A_balancedなど）が揃っているか確認してください。")
    st.stop()

# ランダム順（全ペア混ぜる）
if not st.session_state.pair_order:
    st.session_state.pair_order = random.sample(range(len(pairs)), len(pairs))
    st.session_state.pair_index = 0
    st.session_state.phase = "seq"
    st.session_state.played_seq = False
    st.session_state.played_sim = False
    st.session_state.play_count_seq = 0
    st.session_state.play_count_sim = 0
    init_csv()

idx = st.session_state.pair_index
total = len(pairs)

if idx >= total:
    st.success("🎉 全ペアの評価が完了しました！ありがとうございました！")
    st.stop()

pair = pairs[st.session_state.pair_order[idx]]

st.markdown(
    f"**参加者ID:** `{participant_id}`　"
    f"<span class='badge'>{idx+1} / {total} ペア</span>",
    unsafe_allow_html=True
)
st.progress((idx + 1) / total)

st.markdown(f"**条件:** `{pair['condition']}`（{COND_LABEL.get(pair['condition'], pair['condition'])}）")

phase = st.session_state.phase

# =========================
# ① seq フェーズ
# =========================
if phase == "seq":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("## ① 順番再生を評価（SEQ）")
    st.markdown("<div class='small'>sequential の wav を聴いて評価します。</div>", unsafe_allow_html=True)
    st.markdown("---")

    seq_bytes = read_audio_bytes(pair["SEQ"])
    if seq_bytes is None:
        st.error("SEQファイルの読み込みに失敗しました。")
        st.write("SEQ:", pair["SEQ"])
        st.stop()

    if st.button("▶ 再生を有効化（SEQ）"):
        st.session_state.played_seq = True
        st.session_state.play_count_seq += 1

    if st.session_state.played_seq:
        st.audio(seq_bytes, format="audio/wav")
    else:
        st.info("まず上のボタンで再生を有効化してください。")

    st.caption(f"SEQ 再生回数：{st.session_state.play_count_seq}")
    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown("### 評価（SEQ）")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**聴き心地**")
        st.radio(
            label="",
            options=[5, 4, 3, 2, 1],
            index=2,
            key="seq_valence",
            format_func=lambda x: VALENCE_LABELS[x],
        )

    with c2:
        st.markdown("**緊張**")
        st.radio(
            label="",
            options=[5, 4, 3, 2, 1],
            index=2,
            key="seq_arousal",
            format_func=lambda x: AROUSAL_LABELS[x],
        )

    with c3:
        st.markdown("**違和感**")
        st.radio(
            label="",
            options=[5, 4, 3, 2, 1],
            index=2,
            key="seq_diff",
            format_func=lambda x: DIFF_LABELS[x],
        )

    if st.button("SEQの評価を確定して、SIMへ", disabled=not st.session_state.played_seq):
        st.session_state.seq_saved = (
            st.session_state["seq_valence"],
            st.session_state["seq_arousal"],
            st.session_state["seq_diff"],
        )
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
    st.markdown("## ② 同時音を評価（SIM）")
    st.markdown("<div class='small'>条件フォルダ（basic/colors）の wav を聴いて評価します。</div>", unsafe_allow_html=True)
    st.markdown("---")

    sim_bytes = read_audio_bytes(pair["SIM"])
    if sim_bytes is None:
        st.error("SIMファイルの読み込みに失敗しました。")
        st.write("SIM:", pair["SIM"])
        st.stop()

    if st.button("▶ 再生を有効化（SIM）"):
        st.session_state.played_sim = True
        st.session_state.play_count_sim += 1

    if st.session_state.played_sim:
        st.audio(sim_bytes, format="audio/wav")
    else:
        st.info("まず上のボタンで再生を有効化してください。")

    st.caption(f"SIM 再生回数：{st.session_state.play_count_sim}")
    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown("### 評価（SIM）")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**聴き心地**")
        sim_valence = st.radio(
            label="",
            options=[5, 4, 3, 2, 1],
            index=2,
            key="sim_valence",
            format_func=lambda x: VALENCE_LABELS[x],
        )

    with c2:
        st.markdown("**緊張**")
        sim_arousal = st.radio(
            label="",
            options=[5, 4, 3, 2, 1],
            index=2,
            key="sim_arousal",
            format_func=lambda x: AROUSAL_LABELS[x],
        )

    with c3:
        st.markdown("**違和感**")
        sim_diff = st.radio(
            label="",
            options=[5, 4, 3, 2, 1],
            index=2,
            key="sim_diff",
            format_func=lambda x: DIFF_LABELS[x],
        )

    if st.button("評価を記録して次のペアへ", disabled=not st.session_state.played_sim):
        timestamp = datetime.datetime.utcnow().isoformat()

        if st.session_state.seq_saved is None:
            st.error("SEQの評価が見つかりません。SEQ画面に戻ってやり直してください。")
            st.stop()

        seq_valence, seq_arousal, seq_diff = st.session_state.seq_saved

        row = [
            participant_id,
            timestamp,
            pair["pair_id"],
            pair["condition"],     # ★追加
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

        # 評価値も消す（前回値残り対策）
        for k in ["seq_valence", "seq_arousal", "seq_diff", "sim_valence", "sim_arousal", "sim_diff"]:
            if k in st.session_state:
                del st.session_state[k]

        # 退避データもリセット
        st.session_state.seq_saved = None

        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
