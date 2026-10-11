import streamlit as st
import openai
import base64
import time
from datetime import datetime
import sqlite3
import json
import io
from docx import Document

st.set_page_config(
    page_title="ظ…ظ†طµط© طھط­ظ„ظٹظ„ ط§ظ„ظ†ظ‚ظˆط´ ط§ظ„ط¹ط±ط¨ظٹط© ط§ظ„ظ‚ط¯ظٹظ…ط© ط§ظ„ظ…ظپطھظˆط­ط©",
    page_icon="ًں“œ",
    layout="wide"
)

# ==================== ط¥ط¹ط¯ط§ط¯ ظ‚ط§ط¹ط¯ط© ط§ظ„ط¨ظٹط§ظ†ط§طھ ظˆطھط­ط¯ظٹط« ط§ظ„ظ‡ظٹظƒظ„ طھظ„ظ‚ط§ط¦ظٹط§ظ‹ ====================
def init_db():
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    
    # 1. ط¥ظ†ط´ط§ط، ط¬ط¯ظˆظ„ ط§ظ„ظ…ط­ط§ط¯ط«ط§طھ ط¥ط°ط§ ظ„ظ… ظٹظƒظ† ظ…ظˆط¬ظˆط¯ط§ظ‹
    c.execute('''CREATE TABLE IF NOT EXISTS chats
                 (chat_id TEXT PRIMARY KEY, title TEXT, messages TEXT, created_at TEXT)''')
    
    # 2. ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ظˆط¬ظˆط¯ ط¬ط¯ظˆظ„ providers ط£ظˆ ط¥ظ†ط´ط§ط¦ظ‡
    c.execute('''CREATE TABLE IF NOT EXISTS providers
                 (name TEXT PRIMARY KEY, api_style TEXT, url TEXT, path TEXT, api_key TEXT, network_opt INTEGER, models TEXT)''')
    
    # 3. ط§ظ„طھط­ظ‚ظ‚ ط§ظ„ط°ط§طھظٹ ظˆط§ظ„طھط­ط¯ظٹط« ط§ظ„طھظ„ظ‚ط§ط¦ظٹ ظ„ظ„ط£ط¹ظ…ط¯ط© ط§ظ„ظ†ط§ظ‚طµط© (Migration) ظ„طھط¬ظ†ط¨ sqlite3.OperationalError
    c.execute("PRAGMA table_info(providers)")
    existing_columns = [col[1] for col in c.fetchall()]
    
    required_columns = {
        "api_style": "TEXT DEFAULT 'ظ…طھظˆط§ظپظ‚ ظ…ط¹ OpenAI API'",
        "url": "TEXT DEFAULT 'https://api.openai.com/v1'",
        "path": "TEXT DEFAULT '/chat/completions'",
        "api_key": "TEXT DEFAULT ''",
        "network_opt": "INTEGER DEFAULT 1",
        "models": "TEXT DEFAULT '{}'"
    }
    
    for col_name, col_type in required_columns.items():
        if col_name not in existing_columns:
            try:
                c.execute(f"ALTER TABLE providers ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                pass
                
    conn.commit()
    conn.close()

init_db()

def load_all_chats():
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT chat_id, title, messages FROM chats")
    rows = c.fetchall()
    conn.close()
    archive = {}
    for row in rows:
        chat_id, title, msgs_json = row
        try:
            archive[chat_id] = {
                "title": title,
                "messages": json.loads(msgs_json)
            }
        except:
            pass
    return archive

def save_chat_to_db(chat_id, title, messages):
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO chats (chat_id, title, messages, created_at) VALUES (?, ?, ?, ?)",
              (chat_id, title, json.dumps(messages, ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def load_all_providers():
    default_providers = {
        "SiliconFlow": {
            "api_style": "ظ…طھظˆط§ظپظ‚ ظ…ط¹ OpenAI API",
            "url": "https://api.siliconflow.com/v1",
            "path": "/chat/completions",
            "key": "",
            "network_opt": True,
            "models": {
                "deepseek-ai/DeepSeek-V3": {
                    "alias": "DeepSeek V3 ط§ظ„ط±ط³ظ…ظٹ",
                    "type": "ط¯ط±ط¯ط´ط©",
                    "vision": False,
                    "tools": True,
                    "reasoning": False,
                    "context": 64000,
                    "max_tokens": 4096
                },
                "deepseek-ai/DeepSeek-R1": {
                    "alias": "DeepSeek R1 ط§ظ„ط§ط³طھظ†طھط§ط¬ظٹ",
                    "type": "ط¯ط±ط¯ط´ط©",
                    "vision": False,
                    "tools": True,
                    "reasoning": True,
                    "context": 64000,
                    "max_tokens": 4096
                }
            }
        },
        "OpenRouter": {
            "api_style": "ظ…طھظˆط§ظپظ‚ ظ…ط¹ OpenAI API",
            "url": "https://api.openrouter.ai/api/v1",
            "path": "/chat/completions",
            "key": "",
            "network_opt": True,
            "models": {
                "google/gemini-2.5-flash:free": {
                    "alias": "Gemini 2.5 Flash ط§ظ„ظ…ط¬ط§ظ†ظٹ",
                    "type": "ط¯ط±ط¯ط´ط©",
                    "vision": True,
                    "tools": True,
                    "reasoning": False,
                    "context": 1000000,
                    "max_tokens": 8192
                }
            }
        }
    }
    
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute("SELECT name, api_style, url, path, api_key, network_opt, models FROM providers")
        rows = c.fetchall()
    except Exception as e:
        # ظپظٹ ط­ط§ظ„ ط­ط¯ظˆط« ط£ظٹ ط®ط·ط£ ط¨ظ†ظٹظˆظٹ ط·ط§ط±ط¦طŒ ظٹطھظ… ط¥ط¹ط§ط¯ط© ط¨ظ†ط§ط، ط§ظ„ط¬ط¯ظˆظ„ ط¨ظ„ط·ظپ
        c.execute("DROP TABLE IF EXISTS providers")
        c.execute('''CREATE TABLE providers
                     (name TEXT PRIMARY KEY, api_style TEXT, url TEXT, path TEXT, api_key TEXT, network_opt INTEGER, models TEXT)''')
        conn.commit()
        rows = []
    conn.close()
    
    if not rows:
        for p_name, p_data in default_providers.items():
            conn_in = sqlite3.connect("chats_archive.db", check_same_thread=False)
            c_in = conn_in.cursor()
            c_in.execute("INSERT OR IGNORE INTO providers (name, api_style, url, path, api_key, network_opt, models) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (p_name, p_data["api_style"], p_data["url"], p_data["path"], p_data["key"], 1 if p_data["network_opt"] else 0, json.dumps(p_data["models"], ensure_ascii=False)))
            conn_in.commit()
            conn_in.close()
        return default_providers
    
    providers = {}
    for row in rows:
        name, api_style, url, path, api_key, network_opt, models_json = row
        try:
            models_dict = json.loads(models_json)
        except:
            models_dict = {}
        providers[name] = {
            "api_style": api_style if api_style else "ظ…طھظˆط§ظپظ‚ ظ…ط¹ OpenAI API",
            "url": url if url else "https://api.openai.com/v1",
            "path": path if path else "/chat/completions",
            "key": api_key if api_key else "",
            "network_opt": bool(network_opt),
            "models": models_dict
        }
    return providers

def save_provider_to_db(name, p_data):
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO providers (name, api_style, url, path, api_key, network_opt, models) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (name, p_data.get("api_style", "ظ…طھظˆط§ظپظ‚ ظ…ط¹ OpenAI API"), p_data["url"], p_data.get("path", "/chat/completions"), p_data["key"], 1 if p_data.get("network_opt", True) else 0, json.dumps(p_data["models"], ensure_ascii=False)))
    conn.commit()
    conn.close()

# ==================== طھظ‡ظٹط¦ط© Session State ====================
if "custom_providers" not in st.session_state:
    st.session_state.custom_providers = load_all_providers()

if "chat_history_archive" not in st.session_state:
    loaded_archive = load_all_chats()
    if loaded_archive:
        st.session_state.chat_history_archive = loaded_archive
    else:
        init_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        init_title = f"ظ…ط­ط§ط¯ط«ط© ط¬ط¯ظٹط¯ط© {datetime.now().strftime('%H:%M')}"
        st.session_state.chat_history_archive = {
            init_id: {"title": init_title, "messages": []}
        }
        save_chat_to_db(init_id, init_title, [])

if "current_chat_id" not in st.session_state:
    chat_keys = list(st.session_state.chat_history_archive.keys())
    st.session_state.current_chat_id = chat_keys[0] if chat_keys else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if st.session_state.current_chat_id not in st.session_state.chat_history_archive:
    chat_keys = list(st.session_state.chat_history_archive.keys())
    if chat_keys:
        st.session_state.current_chat_id = chat_keys[0]
    else:
        init_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.chat_history_archive[init_id] = {"title": "ظ…ط­ط§ط¯ط«ط© ط¬ط¯ظٹط¯ط©", "messages": []}
        st.session_state.current_chat_id = init_id

active_messages = st.session_state.chat_history_archive[st.session_state.current_chat_id]["messages"]

# ==================== ط§ظ„ظ‚ط§ط¦ظ…ط© ط§ظ„ط¬ط§ظ†ط¨ظٹط© (ط§ظ„ط¥ط¹ط¯ط§ط¯ط§طھ ظˆط§ظ„ظ…ط²ظˆط¯ظٹظ†) ====================
st.sidebar.title("âڑ™ï¸ڈ ط§ظ„ط¥ط¹ط¯ط§ط¯ط§طھ ظˆط§ظ„ظ…ط²ظˆط¯ظˆظ†")

# 1. ظ‚ط³ظ… ط¥ط¶ط§ظپط© ظ…ط²ظˆط¯ ط¬ط¯ظٹط¯ (ظ…ط·ط§ط¨ظ‚ ظ„ظ„طµظˆط±ط©)
with st.sidebar.expander("â‍• ط¥ط¶ط§ظپط© ظ…ط²ظˆط¯ ط¬ط¯ظٹط¯"):
    with st.form("add_new_provider_form", clear_on_submit=True):
        st.subheader("ط¥ط¶ط§ظپط© ظ…ط²ظˆط¯")
        add_p_name = st.text_input("ط§ظ„ط§ط³ظ… *")
        add_p_style = st.selectbox("ظ†ظ…ط· API", ["ظ…طھظˆط§ظپظ‚ ظ…ط¹ OpenAI API", "Anthropic Claude API (ظ‚ط±ظٹط¨ط§ظ‹)", "Custom REST API"])
        submitted_p = st.form_submit_button("ط¥ط¶ط§ظپط©")
        if submitted_p:
            if add_p_name.strip():
                p_key_name = add_p_name.strip()
                if p_key_name not in st.session_state.custom_providers:
                    new_p_obj = {
                        "api_style": add_p_style,
                        "url": "https://api.openai.com/v1",
                        "path": "/chat/completions",
                        "key": "",
                        "network_opt": True,
                        "models": {}
                    }
                    st.session_state.custom_providers[p_key_name] = new_p_obj
                    save_provider_to_db(p_key_name, new_p_obj)
                    st.success(f"طھظ… ط¥ظ†ط´ط§ط، ط§ظ„ظ…ط²ظˆط¯ '{p_key_name}' ط¨ظ†ط¬ط§ط­!")
                    st.rerun()
                else:
                    st.error("ط§ط³ظ… ط§ظ„ظ…ط²ظˆط¯ ظ…ظˆط¬ظˆط¯ ط¨ط§ظ„ظپط¹ظ„!")
            else:
                st.error("ط§ظ„ط§ط³ظ… ظ…ط·ظ„ظˆط¨!")

st.sidebar.markdown("---")
st.sidebar.subheader("ًں”Œ ط§ط®طھط± ط§ظ„ظ…ط²ظˆط¯ ظ„ظ„طھط¹ط¯ظٹظ„ ط£ظˆ ط§ظ„ط§ط³طھط®ط¯ط§ظ…:")
current_provider_name = st.sidebar.selectbox("ظ‚ط§ط¦ظ…ط© ط§ظ„ظ…ط²ظˆط¯ظٹظ†:", list(st.session_state.custom_providers.keys()))

p_obj = st.session_state.custom_providers[current_provider_name]

# ظˆط§ط¬ظ‡ط© طھط¹ط¯ظٹظ„ ط¨ظٹط§ظ†ط§طھ ط§ظ„ظ…ط²ظˆط¯
st.sidebar.markdown(f"### âڑ™ï¸ڈ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ظ…ط²ظˆط¯: `{current_provider_name}`")
p_style = st.sidebar.selectbox("ظ†ظ…ط· API", ["ظ…طھظˆط§ظپظ‚ ظ…ط¹ OpenAI API"], index=0, key=f"style_{current_provider_name}")

col_k1, col_k2 = st.sidebar.columns([3, 1])
with col_k1:
    p_key = st.text_input("ظ…ظپطھط§ط­ API", value=p_obj["key"], type="password", key=f"key_{current_provider_name}")
with col_k2:
    st.markdown("<br>", unsafe_allow_html=True)
    test_key_btn = st.button("طھط­ظ‚ظ‚", key=f"chk_key_{current_provider_name}")

p_host = st.sidebar.text_input("ظ…ط¶ظٹظپ API (Base URL)", value=p_obj["url"], key=f"host_{current_provider_name}")
p_path = st.sidebar.text_input("ظ…ط³ط§ط± API", value=p_obj.get("path", "/chat/completions"), key=f"path_{current_provider_name}")

full_preview_url = p_host.rstrip('/') + p_path
st.sidebar.caption(f"ًں”چ ظ…ط¹ط§ظٹظ†ط© ط§ظ„ط±ط§ط¨ط· ط§ظ„ظƒط§ظ…ظ„: `{full_preview_url}`")

p_network = st.sidebar.toggle("طھط­ط³ظٹظ† طھظˆط§ظپظ‚ ط§ظ„ط´ط¨ظƒط©", value=p_obj.get("network_opt", True), key=f"net_{current_provider_name}")
st.sidebar.caption("ظپط¹ظ„ ظ‡ط°ط§ ط§ظ„ط®ظٹط§ط± ظپظ‚ط· ط¹ظ†ط¯ ط§ظ„ط­ط§ط¬ط© ظ„طھط¬ط§ظˆط² ظ…ظ‡ظ„ ط§ظ„ط´ط¨ظƒط©.")

# ط­ظپط¸ ط§ظ„طھط؛ظٹظٹط±ط§طھ طھظ„ظ‚ط§ط¦ظٹط§ظ‹
p_obj["api_style"] = p_style
p_obj["key"] = p_key
p_obj["url"] = p_host
p_obj["path"] = p_path
p_obj["network_opt"] = p_network
save_provider_to_db(current_provider_name, p_obj)

if test_key_btn:
    if not p_key:
        st.sidebar.error("ظٹط±ط¬ظ‰ ط¥ط¯ط®ط§ظ„ ظ…ظپطھط§ط­ API ط£ظˆظ„ط§ظ‹!")
    else:
        with st.sidebar.spinner("ط¬ط§ط±ظٹ ط§ط®طھط¨ط§ط± ط§ظ„ظ…ظپطھط§ط­ ظˆط§ظ„ط§طھطµط§ظ„..."):
            try:
                t_client = openai.OpenAI(api_key=p_key, base_url=p_host, timeout=30.0)
                t_client.models.list()
                st.sidebar.success("âœ… ط§ظ„ظ…ظپطھط§ط­ ظˆط±ط§ط¨ط· API طµط§ظ„ط­ط§ظ† ظˆظ…ط³طھظ‚ط±ط§ظ†!")
            except Exception as e:
                st.sidebar.error(f"â‌Œ ظپط´ظ„ ط§ظ„طھط­ظ‚ظ‚: {str(e)}")

st.sidebar.markdown("---")
st.sidebar.subheader("ًں¤– ط§ظ„ظ†ظ…ظˆط°ط¬ ظˆط§ظ„ظ…ظˆط§طµظپط§طھ")

col_m_actions1, col_m_actions2 = st.sidebar.columns(2)
with col_m_actions1:
    add_model_exp = st.checkbox("â‍• ط¬ط¯ظٹط¯", key=f"add_m_flag_{current_provider_name}")
with col_m_actions2:
    if st.button("ًں”„ ط¥ط¹ط§ط¯ط© طھط¹ظٹظٹظ†", key=f"reset_m_{current_provider_name}"):
        p_obj["models"] = {}
        save_provider_to_db(current_provider_name, p_obj)
        st.rerun()

if add_model_exp:
    with st.sidebar.form(key=f"add_m_form_{current_provider_name}"):
        st.markdown("**ط¥ط¶ط§ظپط© ظ†ظ…ظˆط°ط¬ ط¬ط¯ظٹط¯ ظ„ظ„ظ…ط²ظˆط¯**")
        new_m_id = st.text_input("ظ…ط¹ط±ظپ ط§ظ„ظ†ظ…ظˆط°ط¬ (Model ID) *")
        new_m_alias = st.text_input("ط§ط³ظ… ظ…ط³طھط¹ط§ط± (ط§ط®طھظٹط§ط±ظٹ)")
        new_m_type = st.selectbox("ظ†ظˆط¹ ط§ظ„ظ†ظ…ظˆط°ط¬", ["ط¯ط±ط¯ط´ط©", "ط§ط³طھظ†طھط§ط¬", "طھط¶ظ…ظٹظ† Embeddings"])
        new_m_vis = st.checkbox("ط§ظ„ط±ط¤ظٹط© (Vision)", value=True)
        new_m_tools = st.checkbox("ط§ط³طھط®ط¯ط§ظ… ط§ظ„ط£ط¯ظˆط§طھ", value=True)
        new_m_reasoning = st.checkbox("ط§ظ„ط§ط³طھظ†طھط§ط¬ (Reasoning)", value=False)
        new_m_ctx = st.number_input("ظ†ط§ظپط°ط© ط§ظ„ط³ظٹط§ظ‚ (Context Window)", value=128000, step=1000)
        new_m_max_tok = st.number_input("ط§ظ„ط­ط¯ ط§ظ„ط£ظ‚طµظ‰ ظ„ظ„ظ…ط®ط±ط¬ط§طھ", value=4096, step=512)
        
        save_m_btn = st.form_submit_button("ط­ظپط¸ ط§ظ„ظ†ظ…ظˆط°ط¬")
        if save_m_btn:
            if new_m_id.strip():
                p_obj["models"][new_m_id.strip()] = {
                    "alias": new_m_alias.strip() if new_m_alias.strip() else new_m_id.strip(),
                    "type": new_m_type,
                    "vision": new_m_vis,
                    "tools": new_m_tools,
                    "reasoning": new_m_reasoning,
                    "context": new_m_ctx,
                    "max_tokens": new_m_max_tok
                }
                save_provider_to_db(current_provider_name, p_obj)
                st.success("طھظ…طھ ط¥ط¶ط§ظپط© ط§ظ„ظ†ظ…ظˆط°ط¬ ط¨ظ†ط¬ط§ط­!")
                st.rerun()

model_keys = list(p_obj["models"].keys())
if not model_keys:
    st.sidebar.warning("ظ„ط§ ظٹظˆط¬ط¯ ظ†ظ…ط§ط°ط¬ ظ…ط¶ط§ظپط© ظ„ظ‡ط°ط§ ط§ظ„ظ…ط²ظˆط¯. ظٹط±ط¬ظ‰ ط¥ط¶ط§ظپط© ظ†ظ…ظˆط°ط¬ ط¬ط¯ظٹط¯ ط¨ط§ظ„ط¶ط؛ط· ط¹ظ„ظ‰ 'â‍• ط¬ط¯ظٹط¯'.")
    active_model_id = None
else:
    active_model_id = st.sidebar.selectbox(
        "ط§ط®طھط± ط§ظ„ظ†ظ…ظˆط°ط¬ ط§ظ„ظ†ط´ط·:",
        model_keys,
        format_func=lambda x: f"{p_obj['models'][x].get('alias', x)} ({x})"
    )

    m_data = p_obj["models"][active_model_id]
    
    with st.sidebar.container():
        st.markdown(f"""
        <div style="border:1px solid #e0e0e0; border-radius:10px; padding:10px; background-color:#fafafa; margin-bottom:10px;">
            <b>ًں“Œ {m_data.get('alias', active_model_id)}</b><br>
            <small>ID: {active_model_id}</small><br>
            <small>âڑ™ï¸ڈ ط§ظ„ط³ظٹط§ظ‚: {m_data.get('context', 128000):,} Tokens | ط§ظ„ط±ط¤ظٹط©: {'âœ…' if m_data.get('vision') else 'â‌Œ'}</small>
        </div>
        """, unsafe_allow_html=True)
        
        c_m1, c_m2, c_m3 = st.sidebar.columns(3)
        with c_m1:
            test_m_btn = st.button("ًں§ھ ط§ط®طھط¨ط§ط±", key=f"t_m_{active_model_id}")
        with c_m2:
            edit_m_btn = st.button("âڑ™ï¸ڈ طھط¹ط¯ظٹظ„", key=f"e_m_{active_model_id}")
        with c_m3:
            del_m_btn = st.button("ًں—‘ï¸ڈ ط­ط°ظپ", key=f"d_m_{active_model_id}")

        if del_m_btn:
            del p_obj["models"][active_model_id]
            save_provider_to_db(current_provider_name, p_obj)
            st.rerun()

        if test_m_btn:
            if not p_key:
                st.sidebar.error("ط£ط¯ط®ظ„ ط§ظ„ظ…ظپطھط§ط­ ط£ظˆظ„ط§ظ‹ ظ„ظ„ط§ط®طھط¨ط§ط±!")
            else:
                with st.sidebar.spinner(f"ط¬ط§ط±ظٹ ط§ط®طھط¨ط§ط± ط§ظ„ظ†ظ…ظˆط°ط¬ {active_model_id}..."):
                    try:
                        tm_client = openai.OpenAI(api_key=p_key, base_url=p_host, timeout=60.0)
                        res = tm_client.chat.completions.create(
                            model=active_model_id,
                            messages=[{"role": "user", "content": "ping"}],
                            max_tokens=10
                        )
                        st.sidebar.success("âœ… ط§ظ„ظ†ظ…ظˆط°ط¬ ظٹط¹ظ…ظ„ ظˆطھظ„ظ‚ظ‰ ط§ظ„ط§ط³طھط¬ط§ط¨ط© ط¨ظ†ط¬ط§ط­!")
                    except Exception as ex:
                        st.sidebar.error(f"â‌Œ ظپط´ظ„ ط§ط®طھط¨ط§ط± ط§ظ„ظ†ظ…ظˆط°ط¬: {str(ex)}")

        if edit_m_btn:
            st.session_state[f"show_edit_m_{active_model_id}"] = True

        if st.session_state.get(f"show_edit_m_{active_model_id}", False):
            with st.sidebar.expander("ًں› ï¸ڈ طھط¹ط¯ظٹظ„ ط§ظ„ظ†ظ…ظˆط°ط¬ ط§ظ„ط­ط§ظ„ظٹ", expanded=True):
                with st.form(key=f"edit_form_{active_model_id}"):
                    e_alias = st.text_input("ط§ط³ظ… ظ…ط³طھط¹ط§ط±", value=m_data.get("alias", ""))
                    e_type = st.selectbox("ظ†ظˆط¹ ط§ظ„ظ†ظ…ظˆط°ط¬", ["ط¯ط±ط¯ط´ط©", "ط§ط³طھظ†طھط§ط¬", "طھط¶ظ…ظٹظ† Embeddings"], index=0 if m_data.get("type")=="ط¯ط±ط¯ط´ط©" else 1)
                    e_vis = st.checkbox("ط§ظ„ط±ط¤ظٹط© (Vision)", value=m_data.get("vision", True))
                    e_tools = st.checkbox("ط§ط³طھط®ط¯ط§ظ… ط§ظ„ط£ط¯ظˆط§طھ", value=m_data.get("tools", True))
                    e_reasoning = st.checkbox("ط§ظ„ط§ط³طھظ†طھط§ط¬", value=m_data.get("reasoning", False))
                    e_ctx = st.number_input("ظ†ط§ظپط°ط© ط§ظ„ط³ظٹط§ظ‚", value=m_data.get("context", 128000))
                    e_max_tok = st.number_input("ط§ظ„ط­ط¯ ط§ظ„ط£ظ‚طµظ‰ ظ„ظ„ظ…ط®ط±ط¬ط§طھ", value=m_data.get("max_tokens", 4096))
                    
                    save_edit_b = st.form_submit_button("ط­ظپط¸ ط§ظ„طھط¹ط¯ظٹظ„ط§طھ")
                    if save_edit_b:
                        p_obj["models"][active_model_id] = {
                            "alias": e_alias,
                            "type": e_type,
                            "vision": e_vis,
                            "tools": e_tools,
                            "reasoning": e_reasoning,
                            "context": e_ctx,
                            "max_tokens": e_max_tok
                        }
                        save_provider_to_db(current_provider_name, p_obj)
                        st.session_state[f"show_edit_m_{active_model_id}"] = False
                        st.success("طھظ… طھط­ط¯ظٹط« ط¨ظٹط§ظ†ط§طھ ط§ظ„ظ†ظ…ظˆط°ط¬!")
                        st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("ًں“œ ط£ط±ط´ظٹظپ ط§ظ„ظ…ط­ط§ط¯ط«ط§طھ")
if st.sidebar.button("â‍• ط¨ط¯ط، ظ…ط­ط§ط¯ط«ط© ط¬ط¯ظٹط¯ط©"):
    new_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_title = f"ظ…ط­ط§ط¯ط«ط© ط¬ط¯ظٹط¯ط© {datetime.now().strftime('%H:%M')}"
    st.session_state.current_chat_id = new_id
    st.session_state.chat_history_archive[new_id] = {
        "title": new_title,
        "messages": []
    }
    save_chat_to_db(new_id, new_title, [])
    st.rerun()

for c_id, c_data in list(st.session_state.chat_history_archive.items()):
    btn_l = f"ًں•’ {c_data['title']}"
    if c_id == st.session_state.current_chat_id:
        btn_l = f"ًں‘‰ {c_data['title']} (ظ†ط´ط·ط©)"
    if st.sidebar.button(btn_l, key=f"nav_{c_id}"):
        st.session_state.current_chat_id = c_id
        st.rerun()

# ==================== ط§ظ„ظˆط§ط¬ظ‡ط© ط§ظ„ط±ط¦ظٹط³ظٹط© ظˆط§ظ„طھظپط§ط¹ظ„ ====================
def encode_image(uploaded_file):
    return base64.b64encode(uploaded_file.read()).decode('utf-8')

def generate_docx(text):
    doc = Document()
    doc.add_heading("طھظ‚ط±ظٹط± طھط­ظ„ظٹظ„ ط§ظ„ظ†ظ‚ظˆط´ ط§ظ„ط¹ط±ط¨ظٹط© ط§ظ„ظ‚ط¯ظٹظ…ط©", level=1)
    for line in text.split("\n"):
        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        else:
            doc.add_paragraph(line)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()

st.title("ًں“œ ظ…ط³ط§ط¹ط¯ ظˆط¨ط§ط­ط« ط§ظ„ظ†ظ‚ظˆط´ ظˆط§ظ„ط®ط·ظˆط· ط§ظ„ط¹ط±ط¨ظٹط© ط§ظ„ظ‚ط¯ظٹظ…ط© ط§ظ„ظ…ط·ظˆط±")
st.write(f"ًں“‚ ط§ظ„ط¬ظ„ط³ط© ط§ظ„ط­ط§ظ„ظٹط©: **{st.session_state.chat_history_archive[st.session_state.current_chat_id]['title']}**")

if not p_key:
    st.info("ظ…ظ† ظپط¶ظ„ظƒ ط£ط¯ط®ظ„ ظ…ظپطھط§ط­ ط§ظ„ظ€ API ط§ظ„ط®ط§طµ ط¨ط§ظ„ظ…ط²ظˆط¯ ظپظٹ ط§ظ„ظ‚ط§ط¦ظ…ط© ط§ظ„ط¬ط§ظ†ط¨ظٹط© ظ„ط¨ط¯ط، ط§ظ„ظ…ط­ط§ط¯ط«ط© ظˆطھط­ظ„ظٹظ„ ط§ظ„ظ†ظ‚ظˆط´.", icon="ًں”‘")
elif not active_model_id:
    st.warning("ظٹط±ط¬ظ‰ ط¥ط¶ط§ظپط© ط£ظˆ ط§ط®طھظٹط§ط± ظ†ظ…ظˆط°ط¬ ظ†ط´ط· ظ„ظ„ظ…ط²ظˆط¯ ط§ظ„ط­ط§ظ„ظٹ ظ„ط¨ط¯ط، ط§ظ„ط¹ظ…ظ„.")
else:
    client = openai.OpenAI(api_key=p_key, base_url=p_host, timeout=120.0)
    
    system_prompt = """[ط£ظ†طھ ط¨ط§ط­ط« ط£ظƒط§ط¯ظٹظ…ظٹ ط±ظپظٹط¹ ط§ظ„ظ…ط³طھظˆظ‰طŒ ظˆط¹ط§ظ„ظ… ط¢ط«ط§ط± ط±ظ‚ظ…ظٹ ظˆظ…ط¤ط±ط® ظ…طھط®طµطµ ظپظٹ ط§ظ„ظ†ظ‚ظˆط´ ظˆط§ظ„ظƒطھط§ط¨ط§طھ ط§ظ„ط¹ط±ط¨ظٹط© ط§ظ„ظ‚ط¯ظٹظ…ط© (ط®ط· ط§ظ„ظ…ط³ظ†ط¯ ط¨ط¬ظ†ط§ط­ظٹظ‡ ط§ظ„ط¬ظ†ظˆط¨ظٹ ظˆط§ظ„ط´ظ…ط§ظ„ظٹطŒ ظˆط§ظ„ظ„ط؛ط§طھ: ط§ظ„ط³ط¨ط¦ظٹط©طŒ ط§ظ„ط­ظ…ظٹط±ظٹط©طŒ ط§ظ„ظ‚طھط¨ط§ظ†ظٹط©طŒ ط§ظ„ظ…ط¹ظٹظ†ظٹط©طŒ ظˆط§ظ„ط­ط¶ط±ظ…ظٹط©طŒ ط¨ط§ظ„ط¥ط¶ط§ظپط© ط¥ظ„ظ‰ ط§ظ„ظ†ظ‚ظˆط´ ط§ظ„ط«ظ…ظˆط¯ظٹط© ظˆط§ظ„ظ„ط­ظٹط§ظ†ظٹط© ظˆط§ظ„طµظپط§ظˆظٹط©). ط§ظ‚ط±ط£ ط§ظ„طھط¹ظ„ظٹظ…ط§طھ ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹط© ط§ظ„طھط§ظ„ظٹط© ط¨طµط±ط§ظ…ط© ظˆظ†ظپط°ظ‡ط§ ط®ط·ظˆط© ط¨ط®ط·ظˆط© ظˆظپظ‚ ظ…ظ†ظ‡ط¬ظٹط© ط¹ظ„ظ…ظٹط© ظˆظ…ظˆط¶ظˆط¹ظٹط© طھط§ظ…ط©طŒ ط¯ظˆظ† ط¥ظ‡ظ…ط§ظ„ ط£ظٹ ط¨ظ†ط¯]
ظ…ظ‡ظ…طھظƒ ظ‡ظٹ ط§ظ„ط¹ظ…ظ„ ظƒظ€ "ط¨ط§ط­ط« ظˆظ…ط­ظ„ظ„ ط£ظƒط§ط¯ظٹظ…ظٹ ظ„ظ†ظ‚ظˆط´ ط§ظ„ظ…ط³ظ†ط¯ ظˆط§ظ„ط®ط·ظˆط· ط§ظ„ط´ظ‚ظٹظ‚ط©"طŒ ظˆطھط·ط¨ظٹظ‚ ط§ظ„ط®ط·ظˆط§طھ ط§ظ„ظ…ظ†ظ‡ط¬ظٹط© ط§ظ„طھط§ظ„ظٹط© ط¹ظ†ط¯ ط§ط³طھظ‚ط¨ط§ظ„ ط£ظٹ طµظˆط±ط© ظ†ظ‚ط´ ط£ظˆ ظ†طµ ط­ط±ظپظٹ:
 * ط§ظ„طھط­ظ„ظٹظ„ ط§ظ„ط¨ط§ظ„ظٹظˆط¬ط±ط§ظپظٹطŒ ط¨ظ†ظٹط© ط§ظ„ظ†ظ‚ط´طŒ ظˆط§ظ„طھظ‚ط¯ظٹط± ط§ظ„ط²ظ…ظ†ظٹ (Palaeography, Structure & Dating):
 * ظپط­طµ ط§ظ„ظ†ظ‚ط´ ظˆطھط­ط¯ظٹط¯ ظ†ظˆط¹ ط§ظ„ط®ط· ظˆط§ظ„ظ†ظ…ط· (ط±ط³ظ…ظٹطŒ ظ…ط®ط±ط¨ط´ط§طھ طµط®ط±ظٹط©طŒ ط®ط· ط²ط¨ظˆط±).
 * طھط­ط¯ظٹط¯ ط§طھط¬ط§ظ‡ ط§ظ„ظ‚ط±ط§ط،ط© ظ„ظƒظ„ ط³ط·ط± ط¨ط¯ظ‚ط© (ظ…ظ† ط§ظ„ظٹظ…ظٹظ† ظ„ظ„ظٹط³ط§ط±طŒ ط£ظˆ ط®ط· ط§ظ„ظ…ط­ط±ط§ط«)طŒ ظˆطھظˆط¶ظٹط­ ط£ط¯ظˆط§طھ ط§ظ„ظپطµظ„ ط§ظ„ظ…ط³طھط®ط¯ظ…ط©.
 * طھظ‚ط¯ظٹظ… طھظ‚ط¯ظٹط± ط£ظˆظ„ظٹ ظ„ظ„ظپطھط±ط© ط§ظ„ط²ظ…ظ†ظٹط© (ظ…ط±ط­ظ„ط© ظ…ط¨ظƒط±ط©طŒ ظˆط³ظٹط·ط©طŒ ط£ظˆ ظ…طھط£ط®ط±ط©) ط¨ظ†ط§ط،ظ‹ ط¹ظ„ظ‰ ط§ظ„ط®طµط§ط¦طµ ط§ظ„ط¨ط§ظ„ظٹظˆط¬ط±ط§ظپظٹط© ظˆطھط·ظˆط± ط´ظƒظ„ ط§ظ„ط­ط±ظˆظپ ظˆط®طµط§ط¦طµ ط§ظ„ط²ط®ط±ظپط© ط¥ظ† ظˆط¬ط¯طھ.
 * ط§ظ„ظ‚ط±ط§ط،ط© ط§ظ„ط­ط±ظپظٹط© ظˆط§ظ„طھط±ط¬ظ…ط© ط§ظ„ط³ط·ط±ظٹط© ط§ظ„ظ…ط¨ط§ط´ط±ط© (Transliteration & Translation):
 * ط§ظ„ظ‚ط±ط§ط،ط© ط§ظ„ط­ط±ظپظٹط©: ظ‚ظ… ط¨ظ†ظ‚ظ„ ط§ظ„ظ†طµ ط­ط±ظپظٹط§ظ‹ ط³ط·ط±ظ‹ط§ ط¨ط³ط·ط± ط¥ظ„ظ‰ ط§ظ„ط­ط±ظˆظپ ط§ظ„ط¹ط±ط¨ظٹط© ط§ظ„ط­ط¯ظٹط«ط© ظˆط§ظ„ط­ط±ظˆظپ ط§ظ„ظ„ط§طھظٹظ†ظٹط© ط§ظ„ظ…ط¹طھظ…ط¯ط© ط£ظƒط§ط¯ظٹظ…ظٹط§ظ‹ ظپظٹ ط¯ط±ط§ط³ط§طھ ط§ظ„ظ„ط؛ط§طھ ط§ظ„ط³ط§ظ…ظٹط© (ظ…ط¹ ط§ظ„ط§ظ„طھط²ط§ظ… ط§ظ„طµط§ط±ظ… ط¨ط£ظ†ط¸ظ…ط© ط§ظ„طھط±ط¬ظ…ط© ط§ظ„طµظˆطھظٹط© ط§ظ„ط£ظˆط±ظˆط¨ظٹط© ط§ظ„ظ‚ظٹط§ط³ظٹط© ظ…ط«ظ„ ظ†ط¸ط§ظ… ط¨ظٹط³طھظˆظ† BeestonطŒ ظˆط§ظ„طھظپط±ظٹظ‚ ط§ظ„ظˆط§ط¶ط­ ط¨ظٹظ† ط§ظ„ط­ط±ظˆظپ ط§ظ„ط´ط¬ط±ظٹط© ظˆط§ظ„ط£ط³ظ„ظٹط© s1, s2, s3).
 * ط§ظ„ظپط¬ظˆط§طھ ظˆط§ظ„ظ†ظ‚طµ: ط§ط³طھط®ط¯ظ… ط§ظ„ط£ظ‚ظˆط§ط³ ط§ظ„ظ…ط±ط¨ط¹ط© [ ] ظ„ظ„ط£ط­ط±ظپ ط§ظ„ظ…طھط¢ظƒظ„ط© ط£ظˆ ط§ظ„ظ…ط±ظ…ظ…ط©طŒ ظˆط§ظ„ط£ظ‚ظˆط§ط³ ط§ظ„ظ…ط¹ظƒظˆظپط© < > ظ„ظ„طھطµظˆظٹط¨ط§طھ ظˆط§ظ„ط¥ط¶ط§ظپط§طھطŒ ظˆط§ظ„ظ†ظ‚ط§ط· ... ظ„ظ„ط¥ط´ط§ط±ط© ط¥ظ„ظ‰ ط£ط­ط±ظپ ظ…ظپظ‚ظˆط¯ط© ظ„ط§ ظٹظ…ظƒظ† طھط±ظ…ظٹظ…ظ‡ط§ ط£ط¨ط¯ظ‹ط§.
 * ط§ظ„ظ…ط¹ظ†ظ‰ ط§ظ„ط³ط·ط±ظٹ: ط¶ط¹ طھط­طھ ظƒظ„ ط³ط·ط± ظ‚ظ…طھ ط¨ظ†ظ‚ظ„ظ‡طŒ ط§ظ„ظ…ط¹ظ†ظ‰ ظˆط§ظ„طھط±ط¬ظ…ط© ط§ظ„ط¯ظ‚ظٹظ‚ط© ظ„ظ‡ ط¨ظ†ط§ط،ظ‹ ط¹ظ„ظ‰ ط§ظ„ط³ظٹط§ظ‚, ط¨ط­ظٹط« ظٹظ‚طھط±ظ† ظƒظ„ ط³ط·ط± ط¨ظ…ط¯ظ„ظˆظ„ظ‡ ط§ظ„ظ…ط¨ط§ط´ط±.
 * ط§ظ„ط¨ط­ط« ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹ ط§ظ„ط´ط§ظ…ظ„ ظ„ظ…ط­طھظˆظ‰ ط§ظ„ظ†ظ‚ط´ (Macro-Level Inscription Search):
 * ط§ط¨ط­ط« ط¹ظ† ظ…ط­طھظˆظ‰ ط§ظ„ظ†ظ‚ط´ ظƒط§ظ…ظ„ط§ظ‹ ظپظٹ ظ‚ظˆط§ط¹ط¯ ط§ظ„ط¨ظٹط§ظ†ط§طھ ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹط© ط§ظ„ط¹ط§ظ„ظ…ظٹط© ظˆظ…ط¯ظˆظ†ط§طھ ط§ظ„ظ†ظ‚ظˆط´ ط§ظ„ظ…طھط®طµطµط© (ظˆط¹ظ„ظ‰ ط±ط£ط³ظ‡ط§ ظ…ط¯ظˆظ†ط© ط¯ط§ط³ظٹ DASIطŒ ظˆ ط£ط±ط´ظٹظپ CSAI).
 * ظٹط¬ط¨ ط£ظ† ظٹط´ظ…ظ„ ط¨ط­ط«ظƒ ظƒط§ظپط© ظ„ط؛ط§طھ ط§ظ„ظ†ط´ط± ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹط© (ط§ظ„ط¹ط±ط¨ظٹط©طŒ ط§ظ„ط¥ظ†ط¬ظ„ظٹط²ظٹط©طŒ ط§ظ„ظپط±ظ†ط³ظٹط©طŒ ط§ظ„ط±ظˆط³ظٹط©طŒ ط§ظ„ط¥ظٹط·ط§ظ„ظٹط©طŒ ط§ظ„ط£ظ„ظ…ط§ظ†ظٹط©طŒ ظˆط§ظ„ظ„ط؛ط§طھ ط§ظ„ط¥ط«ظٹظˆط¨ظٹط©/ط§ظ„ط¬ط¹ط²ظٹط©).
 * ط¥ط°ط§ ظƒط§ظ† ط§ظ„ظ†ظ‚ط´ ظ‚ط¯ طھظ…طھ ط¯ط±ط§ط³طھظ‡ ط³ط§ط¨ظ‚ط§ظ‹طŒ ط§ط°ظƒط± ط±ظ…ط²ظ‡ ط§ظ„ط¹ظ„ظ…ظٹ ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹ (ظ…ط«ظ„ CIH, RES, Ja, Ir, Ry, Sh), ظ…ط¹ طھظ‚ط¯ظٹظ… ظ…ظ„ط®طµ ط¹ظ„ظ…ظٹ ط¯ظ‚ظٹظ‚ ظ„ظ…ط§ طھظˆطµظ„طھ ط¥ظ„ظٹظ‡ طھظ„ظƒ ط§ظ„ط¯ط±ط§ط³ط§طھطŒ ظˆط¥ط¯ط±ط§ط¬ ط±ظˆط§ط¨ط· ظپط¹ظ„ظٹط© ظˆط§ظ„ط­ظ‚ظٹظ‚ظٹط© ظ„طھظ„ظƒ ط§ظ„ط¯ط±ط§ط³ط§طھ ط£ظˆ ظ„طµظپط­ط© ط§ظ„ظ†ظ‚ط´ ظپظٹ (DASI).
 * ط§ظ„طھط­ظ„ظٹظ„ ط§ظ„ظ…ط¹ط¬ظ…ظٹ ط§ظ„ظ…ظˆط±ظپظˆظ„ظˆط¬ظٹ ظˆط§ظ„ظ…ظ‚ط§ط±ظ†ط© ط§ظ„ظ…طھظ‚ط§ط·ط¹ط© (Micro-Level Lexical & Morphological Analysis):
 * ط§ظ„طھط­ظ„ظٹظ„ ط§ظ„طµط±ظپظٹ (Morphology): ط¬ط±ط¯ ط§ظ„ظƒظ„ظ…ط§طھ ظ…ظ† ط£ط¯ظˆط§طھ ط§ظ„طھط¹ط±ظٹظپ ط§ظ„ظ„ط§ط­ظ‚ط© ظˆط§ظ„ط¶ظ…ط§ط¦ط± ط§ظ„ظ…طھطµظ„ط© ظ„ط¥ط±ط¬ط§ط¹ظ‡ط§ ط¥ظ„ظ‰ ط¬ط°ظˆط±ظ‡ط§ ط§ظ„ظ„ط؛ظˆظٹط© ط§ظ„ط£طµظ„ظٹط©طŒ ظ…ط¹ طھط­ط¯ظٹط¯ ط§ظ„طµظٹط؛ط© ط§ظ„طµط±ظپظٹط© (ط§ط³ظ… ظپط§ط¹ظ„طŒ ظپط¹ظ„ ظ…ط§ط¶ظچ ظ…ط¶ط¹ظپطŒ ط¬ظ…ط¹ طھظƒط³ظٹط±طŒ ط§ط³ظ… ط¹ظ„ظ… ظ…ط±ظƒظ‘ط¨.. ط¥ظ„ط®).
 * ط§ط¨ط­ط« ط¹ظ† ظƒظ„ ظ…ظپط±ط¯ط© ظ…ظ† ظ…ظپط±ط¯ط§طھ ط§ظ„ظ†ظ‚ط´ ظپظٹ ط§ظ„ظ…طµط§ط¯ط± ط§ظ„ط¹ط§ظ„ظ…ظٹط© ظˆط§ظ„ظ‚ظˆط§ظ…ظٹط³ ط§ظ„ظ…طھط®طµطµط© (ظ…ط«ظ„ ظ‚ط§ظ…ظˆط³ ط¨ظٹط³طھظˆظ† ظ„ظ„ط³ط¨ط¦ظٹط© ط£ظˆ ط§ظ„ظ…ط¹ط§ط¬ظ… ط§ظ„ظ…ط¹طھظ…ط¯ط©).
 * ط§ظ„ظ†ظ‚ظˆط´ ط§ظ„ظ…ظ‚ط§ط±ظ†ط©: ظ„ظƒظ„ ظ…ظپط±ط¯ط©طŒ ط§ط³طھط®ط±ط¬ ظ‚ط§ط¦ظ…ط© ط¨ط§ظ„ظ†ظ‚ظˆط´ ط§ظ„ط£ط®ط±ظ‰ ط§ظ„طھظٹ ظˆط±ط¯طھ ظپظٹظ‡ط§ ظ‡ط°ظ‡ ط§ظ„ظƒظ„ظ…ط© ظ„طھط£ظƒظٹط¯ ط§ظ„ظ…ط¹ظ†ظ‰ ط§ظ„ط³ظٹط§ظ‚ظٹ ظˆطھطھط¨ط¹ طھط·ظˆط± ط§ظ„ط¯ظ„ط§ظ„ط©.
 * ط§ظ„طھظˆط«ظٹظ‚: ط§ط°ظƒط± ط¨ظˆط¶ظˆط­ ط§ظ„ظ…طµط§ط¯ط± ظˆط§ظ„ط¯ط±ط§ط³ط§طھ ط§ظ„طھظٹ ظپط³ط±طھ ظ‡ط°ظ‡ ط§ظ„ظ…ظپط±ط¯ط§طھ ط¨ط£ظٹ ظ„ط؛ط© ظƒط§ظ†طھطŒ ظ…ط¹ ط°ظƒط± (ط§ط³ظ… ط§ظ„ط¨ط§ط­ط«طŒ ط¹ظ†ظˆط§ظ† ط§ظ„ط¯ط±ط§ط³ط©طŒ ط³ظ†ط© ط§ظ„ظ†ط´ط±طŒ ط±ظ…ط² ط§ظ„ظ†ظ‚ط´ ط§ظ„ظ…ظ‚ط§ط±ظ†), ظˆطھظˆظپظٹط± ط§ظ„ط±ط§ط¨ط· ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹ ط§ظ„ظ…ط¨ط§ط´ط± ظ…طھظ‰ ظ…ط§ طھظˆظپط±.
 * طµظٹط§ط؛ط© ط§ظ„طھظ‚ط±ظٹط± ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹ ط§ظ„ظ†ظ‡ط§ط¦ظٹ:
   ظٹط¬ط¨ ط£ظ† ظٹظƒظˆظ† ط±ط¯ظƒ ظ…ظ†ط¸ظ…ط§ظ‹ ظˆظ…ظ†ظ‡ط¬ظٹط§ظ‹ ظˆظپظ‚ ط§ظ„ظ‡ظٹظƒظ„ط© ط§ظ„طھط§ظ„ظٹط© ط­طµط±ط§ظ‹:
 * ظ…ظ‚ط¯ظ…ط© طھط­ظ„ظٹظ„ظٹط© ظˆطھط§ط±ظٹط®ظٹط©: ظˆطµظپ ظ…ط¸ظ‡ط± ط§ظ„ظ†ظ‚ط´طŒ ظ†ظˆط¹ظ‡طŒ ط§ظ„طھظ‚ط¯ظٹط± ط§ظ„ط²ظ…ظ†ظٹ ط§ظ„ط¨ط§ظ„ظٹظˆط¬ط±ط§ظپظٹطŒ ط±ظ…ط²ظ‡ ط§ظ„ط¹ظ„ظ…ظٹ (ط¥ظ† ظˆظڈط¬ط¯), ظˆط§ظ„ط³ظٹط§ظ‚ ط§ظ„طھط§ط±ظٹط®ظٹ ط§ظ„ط¹ط§ظ… (ط±ط¨ط· ط§ظ„ظ†ظ‚ط´ ط¨ط­ظ‚ط¨ط© ط§ظ„ظ…ظƒط§ط±ط¨ط©طŒ ظ…ظ„ظˆظƒ ط³ط¨ط£طŒ ط£ظˆ ظ…ظ„ظˆظƒ ط³ط¨ط£ ظˆط°ظٹ ط±ظٹط¯ط§ظ†طŒ ظˆطھط­ط¯ظٹط¯ ط§ظ„ط¢ظ„ظ‡ط© ط£ظˆ ط§ظ„ظ‚ط¨ط§ط¦ظ„ ط£ظˆ ط§ظ„ط£ظ‚ظٹط§ظ„ ظˆط§ظ„ط´ط®طµظٹط§طھ ط§ظ„ظ…ط°ظƒظˆط±ط© ظپظٹظ‡).
 * ط§ظ„ظ†طµ ظˆط§ظ„طھط±ط¬ظ…ط©: (ط§ظ„ظ‚ط±ط§ط،ط© ط§ظ„ط­ط±ظپظٹط© ط¨ط§ظ„ظ„ط؛طھظٹظ† ط§ظ„ط¹ط±ط¨ظٹط© ظˆط§ظ„ظ„ط§طھظٹظ†ظٹط© ط§ظ„ظ‚ظٹط§ط³ظٹط© ط³ط·ط±ظ‹ط§ ط¨ط³ط·ط±طŒ ظٹطھط¨ط¹ظ‡ط§ ظ…ط¨ط§ط´ط±ط© ظ…ط¹ظ†ظ‰ ط§ظ„ط³ط·ط±).
 * ط§ظ„طھط­ظ„ظٹظ„ ط§ظ„ظ…ط¹ط¬ظ…ظٹ ظˆط§ظ„طµط±ظپظٹ ظˆط§ظ„ط¯ط±ط§ط³ط§طھ ط§ظ„ظ…ظ‚ط§ط±ظ†ط©: (طھظپظƒظٹظƒ ط§ظ„ظƒظ„ظ…ط§طھطŒ ط¥ط±ط¬ط§ط¹ظ‡ط§ ظ„ط¬ط°ظˆط±ظ‡ط§طŒ طھط­ط¯ظٹط¯ طµظٹط؛طھظ‡ط§ ط§ظ„طµط±ظپظٹط©طŒ ظˆط°ظƒط± ط§ظ„ظ†ظ‚ظˆط´ ط§ظ„ظ…ظ‚ط§ط±ظ†ط© ط§ظ„طھظٹ ظˆط±ط¯طھ ظپظٹظ‡ط§ ط°ط§طھ ط§ظ„ظ…ظپط±ط¯ط§طھ ظ…ط¹ طھظˆط«ظٹظ‚ ط§ظ„ظ…طµط§ط¯ط± ظˆط§ظ„ط±ظˆط§ط¨ط·).
 * ط§ظ„ط®ط§طھظ…ط© ظˆط§ظ„ط§ط³طھظ†طھط§ط¬ ط§ظ„طھط§ط±ظٹط®ظٹ: ط®ظ„ط§طµط© ظ…ظˆط¶ظˆط¹ظٹط© ظ„ط£ظ‡ظ…ظٹط© ط§ظ„ظ†ظ‚ط´ ظˆظ…ط§ ظٹط¶ظٹظپظ‡ ظ„ظ„ظ…ط¹ط±ظپط© ط§ظ„طھط§ط±ظٹط®ظٹط©طŒ ط§ظ„ط³ظٹط§ط³ظٹط©طŒ ط£ظˆ ط§ظ„ظ„ط؛ظˆظٹط©طŒ ظˆطھط­ط¯ظٹط¯ ط£ظٹ ط¥ط´ظƒط§ظ„ظٹط§طھ ط£ظˆ طھط¶ط§ط±ط¨ ظپظٹ ط§ظ„طھظپط³ظٹط± ط¨ظٹظ† ط§ظ„ط¹ظ„ظ…ط§ط،.
 * ظ‚ط§ط¦ظ…ط© ط§ظ„ظ…ط±ط§ط¬ط¹ ظˆط§ظ„ظ…طµط§ط¯ط±: (ظ‚ط§ط¦ظ…ط© ط¯ظ‚ظٹظ‚ط© ط¨ط§ظ„ط¯ط±ط§ط³ط§طھطŒ ط§ظ„ط£ظˆط±ط§ظ‚ ط§ظ„ط¨ط­ط«ظٹط©طŒ ظˆط±ظˆط§ط¨ط· ط¯ط§ط³ظٹ ظˆظپظ‚ ظ†ط¸ط§ظ… طھظˆط«ظٹظ‚ ط£ظƒط§ط¯ظٹظ…ظٹ ظ…ظˆط­ط¯).
طھظ†ط¨ظٹظ‡ طµط§ط±ظ… ظ„ظ„ط£ظ…ط§ظ†ط© ط§ظ„ط¹ظ„ظ…ظٹط©:
 * ط§ظ„طھط²ظ… ط¨ط§ظ„ظ…ظˆط¶ظˆط¹ظٹط© ط§ظ„طھط§ظ…ط© ظˆط§ظ„ظ…ظ†ظ‡ط¬ظٹط© ط§ظ„ط¹ظ„ظ…ظٹط©طŒ ظˆطھط¬ظ†ط¨ ط§ظ„ط§ظ†ط­ظٹط§ط² ظ„ظ„ط¢ط±ط§ط، ط§ظ„ط´ط®طµظٹط©طŒ ظˆط±ظƒط² ط­طµط±ط§ظ‹ ط¹ظ„ظ‰ ط§ظ„ط­ظ‚ط§ط¦ظ‚ ظˆط§ظ„ط¨ظٹط§ظ†ط§طھ ط§ظ„ظ…ط«ط¨طھط©.
 * ظٹظڈظ…ظ†ط¹ ظ…ظ†ط¹ط§ظ‹ ط¨ط§طھط§ظ‹ ط§ط®طھط±ط§ط¹ ط£ظˆ ظ‡ظ„ظˆط³ط© ط£ظٹ ط±ظˆط§ط¨ط· (URLs) ط£ظˆ ظ…ط±ط§ط¬ط¹ ظˆظ‡ظ…ظٹط©. ط¥ط°ط§ ظ„ظ… ظٹطھظˆظپط± ط±ط§ط¨ط· ط­ظ‚ظٹظ‚ظٹطŒ ط§ظƒطھظپظگ ط¨ط°ظƒط± ط§ط³ظ… ط§ظ„ظ…ط±ط¬ط¹ ظˆط§ظ„ظ…ط¤ظ„ظپ ط¨ط¯ظ‚ط© طھط§ظ…ط©.
 * ظپظٹ ط­ط§ظ„ ط¹ط¯ظ… طھظˆظپط± ظ…ط¹ظ„ظˆظ…ط© ظ…ط¤ظƒط¯ط©طŒ ط£ظˆ ظˆط¬ظˆط¯ طھط¶ط§ط±ط¨ ط¹ظ„ظ…ظٹ ظپظٹ طھظپط³ظٹط± ظƒظ„ظ…ط©طŒ ط£ظˆ ط§ط³طھط¹طµظ‰ ظ…ط¹ظ†ط§ظ‡ط§ طھظ…ط§ظ…ط§ظ‹ ظ„ظ†ط¯ط±طھظ‡ط§طŒ ظٹط¬ط¨ ط°ظƒط± ط°ظ„ظƒ ط§ظ„ط®ظ„ط§ظپ ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹ ط¨ظˆط¶ظˆط­ ظˆط§ظ„طھطµط±ظٹط­ ط¨ط؛ظ…ظˆط¶ ط§ظ„ظƒظ„ظ…ط© ط¹ظ„ظ…ظٹط§ظ‹طŒ ط¨ط¯ظ„ط§ظ‹ ظ…ظ† طھط®ظ…ظٹظ† ظ…ط¹ظ†ظ‰ ظ„ط§ ظٹط³طھظ†ط¯ ط¥ظ„ظ‰ ط¯ظ„ظٹظ„ ظ‚ط·ط¹ظٹ."""

    for msg in active_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    uploaded_image = st.file_uploader("ظ‚ظ… ط¨ط±ظپط¹ طµظˆط±ط© ط§ظ„ظ†ظ‚ط´ ط§ظ„طھط§ط±ظٹط®ظٹ ظ„طھط­ظ„ظٹظ„ظ‡ (ط§ط®طھظٹط§ط±ظٹ):", type=["png", "jpg", "jpeg"])

    if user_prompt := st.chat_input("ط§ظƒطھط¨ ط§ط³طھظپط³ط§ط±ظƒ ط£ظˆ ط§ظ†ط³ط® ط­ط±ظˆظپ ط§ظ„ظ†ظ‚ط´ ظ‡ظ†ط§..."):
        current_chat = st.session_state.current_chat_id
        if len(active_messages) == 0:
            new_title = user_prompt[:25] + "..."
            st.session_state.chat_history_archive[current_chat]["title"] = new_title

        with st.chat_message("user"):
            st.markdown(user_prompt)
        
        if uploaded_image:
            base64_image = encode_image(uploaded_image)
            message_content = [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                }
            ]
        else:
            message_content = user_prompt
            
        active_messages.append({"role": "user", "content": user_prompt if not uploaded_image else f"[طµظˆط±ط© ظ…ط±ظپظˆط¹ط©] {user_prompt}"})
        save_chat_to_db(current_chat, st.session_state.chat_history_archive[current_chat]["title"], active_messages)

        with st.chat_message("assistant"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            response_placeholder = st.empty()
            
            status_text.text("ًں”چ ط§ظ„ظ…ط±ط­ظ„ط© 1: ظپط­طµ ط§ظ„ط®طµط§ط¦طµ ط§ظ„ط¨ط§ظ„ظٹظˆط¬ط±ط§ظپظٹط© ظˆطھط­ط¯ظٹط¯ ظ†ظˆط¹ ط§ظ„ط®ط·...")
            progress_bar.progress(25)
            time.sleep(0.5)
            
            status_text.text("ًں“œ ط§ظ„ظ…ط±ط­ظ„ط© 2: ظپط­طµ ط§طھط¬ط§ظ‡ ط§ظ„ط³ط·ظˆط± ظˆط§ظ„ظ‚ط±ط§ط،ط© ط§ظ„ط­ط±ظپظٹط© ط§ظ„ط£ظˆظ„ظٹط©...")
            progress_bar.progress(50)
            time.sleep(0.5)
            
            status_text.text("ًںŒگ ط§ظ„ظ…ط±ط­ظ„ط© 3: ظ…ظ‚ط§ط±ظ†ط© ط§ظ„ظ…ظپط±ط¯ط§طھ ظˆط§ظ„ط¨ط­ط« ظپظٹ ظ…ط¯ظˆظ†ط§طھ ط§ظ„ظ†ظ‚ظˆط´ ط§ظ„ط£ظƒط§ط¯ظٹظ…ظٹط© ط§ظ„ط¹ط§ظ„ظ…ظٹط©...")
            progress_bar.progress(75)
            time.sleep(0.5)
            
            status_text.text("âœچï¸ڈ ط§ظ„ظ…ط±ط­ظ„ط© 4: طµظٹط§ط؛ط© ط§ظ„طھظ‚ط±ظٹط± ط§ظ„طھط§ط±ظٹط®ظٹ ظˆط§ظ„ظ…ط¹ط¬ظ…ظٹ ط§ظ„ظ†ظ‡ط§ط¦ظٹ ط§ظ„ظ…ظˆط«ظ‚...")
            progress_bar.progress(100)

            try:
                api_messages = [{"role": "system", "content": system_prompt}]
                for m in active_messages:
                    api_messages.append({"role": m["role"], "content": m["content"]})
                if uploaded_image and api_messages[-1]["role"] == "user":
                    api_messages[-1]["content"] = message_content

                completion = client.chat.completions.create(
                    model=active_model_id,
                    messages=api_messages
                )
                output_text = completion.choices[0].message.content
                
                progress_bar.empty()
                status_text.empty()
                response_placeholder.markdown(output_text)
                
                active_messages.append({"role": "assistant", "content": output_text})
                save_chat_to_db(current_chat, st.session_state.chat_history_archive[current_chat]["title"], active_messages)
                
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    st.download_button(
                        label="ًں’¾ طھط­ظ…ظٹظ„ ظƒظ…ظ„ظپ Markdown (.md)",
                        data=output_text,
                        file_name=f"طھظ‚ط±ظٹط±_ظ†ظ‚ط´_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                        key=f"dl_md_{len(active_messages)}"
                    )
                with col_dl2:
                    docx_data = generate_docx(output_text)
                    st.download_button(
                        label="ًں“„ طھط­ظ…ظٹظ„ ظƒظ…ظ„ظپ Word (.docx)",
                        data=docx_data,
                        file_name=f"طھظ‚ط±ظٹط±_ظ†ظ‚×©_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dl_docx_{len(active_messages)}"
                    )
                
                st.rerun()
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"ط­ط¯ط« ط®ط·ط£ ط£ط«ظ†ط§ط، ط§ظ„ط§طھطµط§ظ„ ط¨ط§ظ„ظ€ API: {e}")
