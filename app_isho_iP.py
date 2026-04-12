import streamlit as st
import pandas as pd
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials

PASSWORD = "1203"

SHEET_NAME = "弁理士試験_意匠"  # ←ここをあなたのシート名に変更

# ===== 認証 =====
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    pw = st.text_input("パスワードを入力", type="password")
    if st.button("ログイン"):
        if pw == PASSWORD:
            st.session_state.auth = True
        else:
            st.error("パスワードが違います")

        st.rerun()

    st.stop()

# ===== Google Sheets接続 =====
@st.cache_resource
def get_gspread_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], scope
    )
    return gspread.authorize(creds)

# ===== データ読み込み =====
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet = client.open(SHEET_NAME).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# ===== データ保存 =====
def save_data(df):
    client = get_gspread_client()
    sheet = client.open(SHEET_NAME).sheet1
    sheet.update([df.columns.values.tolist()] + df.values.tolist())

df = load_data()

# ===== 初期化 =====
def safe_sample(df, n):
    if len(df) == 0:
        return df
    return df.sample(n=min(n, len(df)))

if "data" not in st.session_state:
    df_A = df[df.iloc[:, 3] == 'A']
    df_B = df[df.iloc[:, 3] == 'B']
    df_C = df[df.iloc[:, 3] == 'C']

    # ===== 基本サンプリング（最大値で取得）=====
    sample_A = safe_sample(df_A, 1)
    sample_B = safe_sample(df_B, 3)
    sample_C = safe_sample(df_C, 6)

    # ===== 初期セット =====
    result = pd.concat([sample_A, sample_B, sample_C])

    total_needed = 10

    # ===== 不足分をCで補完 =====
    if len(result) < total_needed:
        remaining_C = df_C.drop(sample_C.index)
        extra_C = safe_sample(remaining_C, total_needed - len(result))
        result = pd.concat([result, extra_C])

    # ===== まだ不足ならBで補完 =====
    if len(result) < total_needed:
        remaining_B = df_B.drop(sample_B.index)
        extra_B = safe_sample(remaining_B, total_needed - len(result))
        result = pd.concat([result, extra_B])

    # ===== まだ不足ならAで補完 =====
    if len(result) < total_needed:
        remaining_A = df_A.drop(sample_A.index)
        extra_A = safe_sample(remaining_A, total_needed - len(result))
        result = pd.concat([result, extra_A])

    # ===== 最後は全体から補完（保険）=====
    if len(result) < total_needed:
        used_index = result.index
        remaining_all = df.drop(used_index, errors="ignore")
        extra_all = safe_sample(remaining_all, total_needed - len(result))
        result = pd.concat([result, extra_all])

    # ===== 最終代入（必ず実行される）=====
    st.session_state.data = result.sample(frac=1).reset_index(drop=True)
    

if "current" not in st.session_state:
    st.session_state.current = None

if "show_answer" not in st.session_state:
    st.session_state.show_answer = False

if "queue" not in st.session_state:
    st.session_state.queue = []

if "step" not in st.session_state:
    st.session_state.step = 0

st.title("弁理士試験 学習アプリ")

# ===== 問題出題 =====
if st.button("問題を出す"):
    st.session_state.step += 1

    due_questions = [q for q in st.session_state.queue if q["due"] <= st.session_state.step]

    if due_questions:
        q = random.choice(due_questions)
        st.session_state.current = None
        st.session_state.recall_row = q["row"]
        st.session_state.queue.remove(q)

    elif not st.session_state.data.empty:
        st.session_state.current = random.randrange(len(st.session_state.data))

    st.session_state.show_answer = False

# ===== 問題表示 =====
if st.session_state.current is not None:
    row = st.session_state.data.iloc[st.session_state.current]

    st.subheader("問題")
    st.markdown(row.iloc[1].replace("\n", "  \n"))

    if st.button("答えを見る"):
        st.session_state.show_answer = True

# ===== 解答表示 =====
if st.session_state.show_answer:
    row = st.session_state.data.iloc[st.session_state.current]

    st.subheader("解答")
    st.markdown(row.iloc[2].replace("\n", "  \n"))

    result = st.radio("正解しましたか？", ["y", "n"], key="result")

    if result == "y":
        new_rank = st.selectbox("新しいRank", ["A", "B", "C"], key="rank")

        if st.button("更新して次へ"):
            idx = row.name
            df.at[idx, df.columns[3]] = new_rank

            # ★ Excel保存 → Sheets保存に変更
            save_data(df)

            st.session_state.data = st.session_state.data.drop(
                st.session_state.data.index[st.session_state.current]
            ).reset_index(drop=True)

            st.session_state.current = None
            st.session_state.show_answer = False

            st.rerun()

    elif result == "n":
        if st.button("次の問題へ"):

            remaining = len(st.session_state.data) + len(st.session_state.queue)

            if remaining <= 2:
                delay = 1
            else:
                delay = random.randint(2, 3)

            st.session_state.queue.append({
                "row": row,
                "due": st.session_state.step + delay
            })

            st.session_state.current = None
            st.session_state.show_answer = False

            st.rerun()

# ===== 全問終了時の表示 =====
if (
    "data" in st.session_state
    and len(st.session_state.data) == 0
    and not st.session_state.data.empty
    and not st.session_state.queue
):
    st.success("🎉 すべての問題が終了しました！")
    if st.button("もう一度やる"):
        del st.session_state.data
        del st.session_state.current
        del st.session_state.show_answer
        st.rerun()
    st.stop()