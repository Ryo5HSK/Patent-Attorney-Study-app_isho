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
            st.rerun()
        else:
            st.error("パスワードが違います")
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

    sample_A = safe_sample(df_A, 1)
    sample_B = safe_sample(df_B, 3)
    sample_C = safe_sample(df_C, 6)

    result = pd.concat([sample_A, sample_B, sample_C])
    total_needed = 10

    for df_target, sample_target in [(df_C, sample_C), (df_B, sample_B), (df_A, sample_A)]:
        if len(result) < total_needed:
            remaining = df_target.drop(sample_target.index, errors="ignore")
            extra = safe_sample(remaining, total_needed - len(result))
            result = pd.concat([result, extra])

    if len(result) < total_needed:
        used_index = result.index
        remaining_all = df.drop(used_index, errors="ignore")
        extra_all = safe_sample(remaining_all, total_needed - len(result))
        result = pd.concat([result, extra_all])

    st.session_state.data = result.reset_index(drop=True)

# ===== 状態管理 (Queue等を排除したシンプル版) =====
if "current_q" not in st.session_state:
    st.session_state.current_q = None

if "show_answer" not in st.session_state:
    st.session_state.show_answer = False

st.title("弁理士試験 学習アプリ")

# ===== 全問終了時の表示 =====
if (
    "data" in st.session_state
    and st.session_state.data.empty 
    and st.session_state.current_q is None
):
    st.success("🎉 すべての問題が終了しました！")
    if st.button("もう一度やる"):
        del st.session_state.data
        del st.session_state.current_q
        st.cache_data.clear() 
        st.rerun()
    st.stop()


# ===== 問題出題 =====
if st.session_state.current_q is None:
    if st.button("問題を出す"):
        # ★ 残っているリストからランダムに1問取得（まだ消さない）
        st.session_state.current_q = st.session_state.data.sample(n=1).iloc[0]
        st.session_state.show_answer = False
        st.rerun()

# ===== 問題表示 =====
if st.session_state.current_q is not None:
    row = st.session_state.current_q

    st.subheader("問題")
    st.markdown(row.iloc[1].replace("\n", "  \n"))

    if not st.session_state.show_answer:
        if st.button("答えを見る"):
            st.session_state.show_answer = True
            st.rerun()

# ===== 解答・結果入力表示 =====
if st.session_state.show_answer:
    row = st.session_state.current_q

    st.subheader("解答")
    st.markdown(row.iloc[2].replace("\n", "  \n"))

    result = st.radio("正解しましたか？", ["y", "n"], key="result", horizontal=True)

    if result == "y":
        current_rank = row.iloc[3] if row.iloc[3] in ["A", "B", "C"] else "C"
        new_rank = st.selectbox("新しいRank", ["A", "B", "C"], index=["A", "B", "C"].index(current_rank), key="rank")

        if st.button("更新して次へ"):
            idx = row.name 
            df.at[idx, df.columns[3]] = new_rank
            save_data(df)

            # ★ yの場合：正解した問題だけをリスト(data)から削除
            st.session_state.data = st.session_state.data.drop(idx).reset_index(drop=True)
            
            st.session_state.current_q = None
            st.session_state.show_answer = False
            st.rerun()

    elif result == "n":
        if st.button("次の問題へ"):
            # ★ nの場合：リスト(data)には残したまま、出題状態だけリセット
            st.session_state.current_q = None
            st.session_state.show_answer = False
            st.rerun()