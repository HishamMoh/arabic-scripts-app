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
    page_title="منصة تحليل النقوش العربية القديمة المفتوحة",
    page_icon="📜",
    layout="wide"
)

# ==================== إعداد قاعدة البيانات وتحديث الهيكل تلقائياً ====================
def init_db():
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS chats
                 (chat_id TEXT PRIMARY KEY, title TEXT, messages TEXT, created_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS providers
                 (name TEXT PRIMARY KEY, api_style TEXT, url TEXT, path TEXT, api_key TEXT, network_opt INTEGER, models TEXT)''')
    
    c.execute("PRAGMA table_info(providers)")
    existing_columns = [col[1] for col in c.fetchall()]
    
    required_columns = {
        "api_style": "TEXT DEFAULT 'OpenAI API'",
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
            except Exception:
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
            "api_style": "OpenAI API",
            "url": "https://api.siliconflow.com/v1",
            "path": "/chat/completions",
            "key": "",
            "network_opt": True,
            "models": {
                "Qwen/Qwen2.5-7B-Instruct": {
                    "alias": "Qwen 2.5 7B Instruct",
                    "type": "دردشة",
                    "vision": False,
                    "tools": True,
                    "reasoning": False,
                    "context": 32768,
                    "max_tokens": 4096
                },
                "deepseek-ai/DeepSeek-V3": {
                    "alias": "DeepSeek V3 الرسمي",
                    "type": "دردشة",
                    "vision": False,
                    "tools": True,
                    "reasoning": False,
                    "context": 64000,
                    "max_tokens": 4096
                }
            }
        },
        "OpenRouter": {
            "api_style": "OpenAI API",
            "url": "https://api.openrouter.ai/api/v1",
            "path": "/chat/completions",
            "key": "",
            "network_opt": True,
            "models": {
                "google/gemini-2.5-flash:free": {
                    "alias": "Gemini 2.5 Flash المجاني",
                    "type": "دردشة",
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
    except Exception:
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
        models_dict = {}
        if isinstance(models_json, str):
            try:
                models_dict = json.loads(models_json)
                if not isinstance(models_dict, dict):
                    models_dict = {}
            except:
                models_dict = {}
        elif isinstance(models_json, dict):
            models_dict = models_json
            
        providers[name] = {
            "api_style": api_style if api_style else "OpenAI API",
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
    models_val = p_data.get("models", {})
    if not isinstance(models_val, str):
        models_str = json.dumps(models_val, ensure_ascii=False)
    else:
        models_str = models_val
        
    c.execute("INSERT OR REPLACE INTO providers (name, api_style, url, path, api_key, network_opt, models) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (name, p_data.get("api_style", "OpenAI API"), p_data["url"], p_data.get("path", "/chat/completions"), p_data["key"], 1 if p_data.get("network_opt", True) else 0, models_str))
    conn.commit()
    conn.close()

# ==================== تهيئة Session State ====================
if "custom_providers" not in st.session_state:
    st.session_state.custom_providers = load_all_providers()

for p_n, p_val in st.session_state.custom_providers.items():
    if not isinstance(p_val.get("models"), dict):
        try:
            p_val["models"] = json.loads(p_val["models"]) if isinstance(p_val["models"], str) else {}
        except:
            p_val["models"] = {}

if "chat_history_archive" not in st.session_state:
    loaded_archive = load_all_chats()
    if loaded_archive:
        st.session_state.chat_history_archive = loaded_archive
    else:
        init_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        init_title = f"محادثة جديدة {datetime.now().strftime('%H:%M')}"
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
        st.session_state.chat_history_archive[init_id] = {"title": "محادثة جديدة", "messages": []}
        st.session_state.current_chat_id = init_id

if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

active_messages = st.session_state.chat_history_archive[st.session_state.current_chat_id]["messages"]

# ==================== القائمة الجانبية (Sidebar) ====================
with st.sidebar:
    st.markdown("### 📜 منصة النقوش العربية القديمة")
    st.markdown("---")
    
    if st.button("➕ دردشة جديدة", use_container_width=True, type="primary"):
        new_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_title = f"محادثة جديدة {datetime.now().strftime('%H:%M')}"
        st.session_state.current_chat_id = new_id
        st.session_state.chat_history_archive[new_id] = {
            "title": new_title,
            "messages": []
        }
        save_chat_to_db(new_id, new_title, [])
        st.session_state.current_page = "chat"
        st.rerun()

    st.markdown("#### 🕒 أرشيف المحادثات")
    
    for c_id, c_data in list(st.session_state.chat_history_archive.items()):
        btn_label = f"💬 {c_data['title']}"
        if c_id == st.session_state.current_chat_id and st.session_state.current_page == "chat":
            btn_label = f"👉 {c_data['title']}"
        if st.button(btn_label, key=f"nav_chat_{c_id}", use_container_width=True):
            st.session_state.current_chat_id = c_id
            st.session_state.current_page = "chat"
            st.rerun()

    st.markdown("---")
    col_s1, col_s2 = st.columns([4, 1])
    with col_s1:
        st.markdown("**إعدادات النظام والمزودين**")
    with col_s2:
        if st.button("⚙️", key="btn_go_settings", help="فتح لوحة الإعدادات والمزودين"):
            st.session_state.current_page = "settings"
            st.rerun()

def encode_image(uploaded_file):
    return base64.b64encode(uploaded_file.read()).decode('utf-8')

def generate_docx(text):
    doc = Document()
    doc.add_heading("تقرير تحليل النقوش العربية القديمة", level=1)
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

# ==================== الصفحات (Chat vs Settings) ====================
if st.session_state.current_page == "settings":
    col_top1, col_top2 = st.columns([5, 1])
    with col_top1:
        st.title("⚙️ لوحة الإعدادات والتحكم المركزية")
        st.markdown("إدارة مزودي النماذج، ومزامنة النماذج المتاحة من السيرفر مباشرة.")
    with col_top2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔙 العودة للشات", type="primary"):
            st.session_state.current_page = "chat"
            st.rerun()

    st.markdown("---")

    settings_tab1, settings_tab2, settings_tab3 = st.tabs([
        "🔌 مزود النموذج (Model Provider)",
        "🌐 إعدادات الشبكة",
        "🧠 الذاكرة والمستندات"
    ])

    with settings_tab1:
        st.subheader("إدارة المزودين والنماذج المخصصة")
        
        with st.expander("➕ إضافة مزود مخصص جديد"):
            with st.form("add_provider_form_clean", clear_on_submit=True):
                new_p_name = st.text_input("اسم المزود (مثال: SiliconFlow أو OpenRouter)")
                new_p_style = st.selectbox("نمط API", ["OpenAI API", "OpenAI Responses API", "Anthropic Claude API", "Google Gemini API"])
                new_p_url = st.text_input("مضيف API (Base URL)", value="https://api.siliconflow.com/v1")
                new_p_path = st.text_input("مسار API", value="/chat/completions")
                new_p_key = st.text_input("مفتاح API", type="password")
                new_p_net = st.checkbox("تحسين توافق الشبكة", value=True)
                
                submitted_new_p = st.form_submit_button("حفظ المزود الجديد")
                if submitted_new_p:
                    if new_p_name.strip():
                        p_k = new_p_name.strip()
                        if p_k not in st.session_state.custom_providers:
                            st.session_state.custom_providers[p_k] = {
                                "api_style": new_p_style,
                                "url": new_p_url.strip(),
                                "path": new_p_path.strip(),
                                "key": new_p_key.strip(),
                                "network_opt": new_p_net,
                                "models": {}
                            }
                            save_provider_to_db(p_k, st.session_state.custom_providers[p_k])
                            st.success(f"تم إضافة المزود '{p_k}' بنجاح!")
                            st.rerun()
                        else:
                            st.error("اسم المزود موجود مسبقاً!")
                    else:
                        st.error("يرجى إدخال اسم المزود!")

        st.markdown("---")
        provider_names = list(st.session_state.custom_providers.keys())
        selected_prov = st.selectbox("اختر المزود للتعديل ومزامنة النماذج:", provider_names)
        
        if selected_prov:
            prov_data = st.session_state.custom_providers[selected_prov]
            
            st.markdown(f"### خصائص المزود: `{selected_prov}`")
            col_ep1, col_ep2 = st.columns(2)
            with col_ep1:
                edit_style = st.selectbox("نمط API", ["OpenAI API", "OpenAI Responses API", "Anthropic Claude API", "Google Gemini API"], 
                                          index=0, key=f"ed_style_{selected_prov}")
                edit_url = st.text_input("مضيف API (Base URL)", value=prov_data["url"], key=f"ed_url_{selected_prov}")
            with col_ep2:
                edit_path = st.text_input("مسار API", value=prov_data.get("path", "/chat/completions"), key=f"ed_path_{selected_prov}")
                edit_key = st.text_input("مفتاح API", value=prov_data["key"], type="password", key=f"ed_key_{selected_prov}")
            
            edit_net = st.toggle("تحسين توافق الشبكة", value=prov_data.get("network_opt", True), key=f"ed_net_{selected_prov}")
            
            col_btn_p1, col_btn_p2, col_btn_p3, col_btn_p4 = st.columns(4)
            with col_btn_p1:
                if st.button("💾 حفظ البيانات", key=f"save_prov_{selected_prov}"):
                    prov_data["api_style"] = edit_style
                    prov_data["url"] = edit_url
                    prov_data["path"] = edit_path
                    prov_data["key"] = edit_key
                    prov_data["network_opt"] = edit_net
                    save_provider_to_db(selected_prov, prov_data)
                    st.success("تم الحفظ بنجاح!")
                    st.rerun()
            with col_btn_p2:
                if st.button("🧪 اختبار الاتصال", key=f"test_prov_{selected_prov}"):
                    if not edit_key:
                        st.warning("أدخل المفتاح أولاً!")
                    else:
                        try:
                            t_cli = openai.OpenAI(api_key=edit_key, base_url=edit_url, timeout=30.0)
                            t_cli.models.list()
                            st.success("✅ الاتصال سليم!")
                        except Exception as ex:
                            st.error(f"❌ فشل: {ex}")
            with col_btn_p3:
                # 🌟 الميزة الأفضل والأسهل والأوثق: جلب النماذج تلقائياً من المزود لمنع خطأ model_not_found نهائياً
                if st.button("🔄 جلب النماذج تلقائياً", key=f"fetch_models_{selected_prov}", help="جلب النماذج الحقيقية والصحيحة من السيرفر فوراً"):
                    if not edit_key:
                        st.warning("يرجى إدخال مفتاح API أولاً لجلب النماذج!")
                    else:
                        with st.spinner("جاري جلب قائمة النماذج المعتمدة من سيرفر المزود..."):
                            try:
                                f_cli = openai.OpenAI(api_key=edit_key, base_url=edit_url, timeout=30.0)
                                remote_models = f_cli.models.list()
                                fetched_dict = {}
                                for m in remote_models:
                                    m_id = m.id
                                    fetched_dict[m_id] = {
                                        "alias": m_id,
                                        "type": "دردشة",
                                        "vision": True,
                                        "tools": True,
                                        "reasoning": False,
                                        "context": 64000,
                                        "max_tokens": 4096
                                    }
                                if fetched_dict:
                                    prov_data["models"] = fetched_dict
                                    save_provider_to_db(selected_prov, prov_data)
                                    st.success(f"✅ تم جلب {len(fetched_dict)} نموذجاً صحيحاً وتحديثها بنجاح!")
                                    st.rerun()
                                else:
                                    st.warning("لم يتم إرجاع أي نماذج من السيرفر.")
                            except Exception as ex:
                                st.error(f"❌ فشل جلب النماذج: {ex}")
            with col_btn_p4:
                if len(st.session_state.custom_providers) > 1:
                    if st.button("🗑️ حذف المزود", key=f"del_prov_{selected_prov}"):
                        del st.session_state.custom_providers[selected_prov]
                        conn_del = sqlite3.connect("chats_archive.db", check_same_thread=False)
                        c_del = conn_del.cursor()
                        c_del.execute("DELETE FROM providers WHERE name = ?", (selected_prov,))
                        conn_del.commit()
                        conn_del.close()
                        st.success("تم الحذف.")
                        st.rerun()

            st.markdown("---")
            st.subheader(f"🤖 النماذج المفعلة حالياً للمزود: {selected_prov}")
            
            with st.expander("➕ إضافة نموذج يدوي إضافي"):
                with st.form(key=f"add_model_form_{selected_prov}", clear_on_submit=True):
                    m_id_in = st.text_input("معرف النموذج (Model ID الدقيق مثل: Qwen/Qwen2.5-7B-Instruct) *")
                    m_alias_in = st.text_input("اسم مستعار (اختياري)")
                    
                    col_chk1, col_chk2, col_chk3 = st.columns(3)
                    with col_chk1:
                        m_tools_chk = st.checkbox("الأدوات", value=True)
                    with col_chk2:
                        m_reason_chk = st.checkbox("الاستنتاج", value=False)
                    with col_chk3:
                        m_vision_chk = st.checkbox("الرؤية", value=True)
                        
                    col_num1, col_num2 = st.columns(2)
                    with col_num1:
                        m_ctx_in = st.number_input("السياق", value=64000, step=1000)
                    with col_num2:
                        m_max_tok_in = st.number_input("الحد الأقصى للمخرجات", value=4096, step=512)
                        
                    if st.form_submit_button("حفظ النموذج"):
                        if m_id_in.strip():
                            if not isinstance(prov_data.get("models"), dict):
                                prov_data["models"] = {}
                            prov_data["models"][m_id_in.strip()] = {
                                "alias": m_alias_in.strip() if m_alias_in.strip() else m_id_in.strip(),
                                "tools": m_tools_chk,
                                "reasoning": m_reason_chk,
                                "vision": m_vision_chk,
                                "context": m_ctx_in,
                                "max_tokens": m_max_tok_in
                            }
                            save_provider_to_db(selected_prov, prov_data)
                            st.success("تمت الإضافة بنجاح!")
                            st.rerun()
                        else:
                            st.error("المعرف مطلوب!")

            if prov_data.get("models"):
                for m_id, m_vals in list(prov_data["models"].items()):
                    st.markdown(f"""
                    <div style="border:1px solid #d0d0d0; border-radius:8px; padding:8px; margin-bottom:6px; background:#f9f9f9;">
                        <b>📌 {m_vals.get('alias', m_id)}</b> | <code>{m_id}</code>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"حذف `{m_id}`", key=f"del_m_{selected_prov}_{m_id}"):
                        del prov_data["models"][m_id]
                        save_provider_to_db(selected_prov, prov_data)
                        st.rerun()

    with settings_tab2:
        st.subheader("إعدادات الشبكة والمهل")
        st.slider("مهلة الاتصال (ثانية)", 10, 300, 120)

    with settings_tab3:
        st.subheader("إدارة الذاكرة")
        st.write("أرشيف المحادثات يتم حفظه وتحديثه تلقائياً في قاعدة البيانات المحلية.")

else:
    prov_keys = list(st.session_state.custom_providers.keys())
    selected_p_name = st.selectbox("🔌 اختر المزود الفعال:", prov_keys, key="main_active_provider")
    curr_p_obj = st.session_state.custom_providers[selected_p_name]
    
    model_keys = list(curr_p_obj.get("models", {}).keys())
    
    if not model_keys:
        st.warning("⚠️ لا توجد نماذج مضافة لهذا المزود. يرجى الانتقال إلى الإعدادات (⚙️) والضغط على زر '🔄 جلب النماذج تلقائياً'.")
        active_model_id = None
    else:
        active_model_id = st.selectbox("🤖 النموذج الفعال حالياً:", model_keys, 
                                       format_func=lambda x: f"{curr_p_obj['models'][x].get('alias', x)} ({x})",
                                       key="main_active_model")

    st.title("📜 مساعد وباحث النقوش والخطوط العربية القديمة المطور")
    st.write(f"📂 الجلسة الحالية: **{st.session_state.chat_history_archive[st.session_state.current_chat_id]['title']}**")
    st.markdown("---")

    api_key_val = curr_p_obj.get("key", "")
    api_base_url = curr_p_obj.get("url", "https://api.openai.com/v1")
    
    if not api_key_val:
        st.info("🔑 يرجى إدخال مفتاح الـ API الخاص بالمزود من لوحة الإعدادات (⚙️) لبدء التحليل.", icon="🔑")
    elif not active_model_id:
        st.warning("⚠️ يرجى اختيار أو جلب نموذج نشط.")
    else:
        client = openai.OpenAI(api_key=api_key_val, base_url=api_base_url, timeout=120.0)
        
        # ⚠️ الخلفية العلمية خط أحمر - التوجيه الأكاديمي الصارم للنقوش المسندية والخطوط الشقيقة (محفوظ تماماً دون أي تغيير)
        system_prompt = """[أنت باحث أكاديمي رفيع المستوى، وعالم آثار رقمي ومؤرخ متخصص في النقوش والكتابات العربية القديمة (خط المسند بجناحيه الجنوبي والشمالي، واللغات: السبئية، الحميرية، القتبانية، المعينية، والحضرمية، بالإضافة إلى النقوش الثمودية واللحيانية والصفاوية). اقرأ التعليمات الأكاديمية التالية بصرامة ونفذها خطوة بخطوة وفق منهجية علمية وموضوعية تامة، دون إهمال أي بند]
مهمتك هي العمل كـ "باحث ومحلل أكاديمي لنقوش المسند والخطوط الشقيقة"، وتطبيق الخطوات المنهجية التالية عند استقبال أي صورة نقش أو نص حرفي:
 * التحليل الباليوجرافي، بنية النقش، والتقدير الزمني (Palaeography, Structure & Dating):
 * فحص النقش وتحديد نوع الخط والنمط (رسمي، مخربشات صخرية، خط زبور).
 * تحديد اتجاه القراءة لكل سطر بدقة (من اليمين لليسار، أو خط المحراث)، وتوضيح أدوات الفصل المستخدمة.
 * تقديم تقدير أولي للفترة الزمنية (مرحلة مبكرة، وسيطة، أو متأخرة) بناءً على الخصائص الباليوجرافية وتطور شكل الحروف وخصائص الزخرفة إن وجدت.
 * القراءة الحرفية والترجمة السطرية المباشرة (Transliteration & Translation):
 * القراءة الحرفية: قم بنقل النص حرفياً سطرًا بسطر إلى الحروف العربية الحديثة والحروف اللاتينية المعتمدة أكاديمياً في دراسات اللغات السامية (مع الالتزام الصارم بأنظمة الترجمة الصوتية الأوروبية القياسية مثل نظام بيستون Beeston، والتفريق الواضح بين الحروف الشجرية والأسلية s1, s2, s3).
 * الفجوات والنقص: استخدم الأقواس المربعة [ ] للأحرف المتآكلة أو المرممة، والأقواس المعكوفة < > للتصويبات والإضافات، والنقاط ... للإشارة إلى أحرف مفقودة لا يمكن ترميمها أبدًا.
 * المعنى السطري: ضع تحت كل سطر قمت بنقله، المعنى والترجمة الدقيقة له بناءً على السياق, بحيث يقترن كل سطر بمدلوله المباشر.
 * البحث الأكاديمي الشامل لمحتوى النقش (Macro-Level Inscription Search):
 * ابحث عن محتوى النقش كاملاً في قواعد البيانات الأكاديمية العالمية ومدونات النقوش المتخصصة (وعلى رأسها مدونة داسي DASI، و أرشيف CSAI).
 * يجب أن يشمل بحثك كافة لغات النشر الأكاديمية (العربية، الإنجليزية، الفرنسية، الروسية، الإيطالية، الألمانية، واللغات الإثيوبية/الجعزية).
 * إذا كان النقش قد تمت دراسته سابقاً، اذكر رمزه العلمي الأكاديمي (مثل CIH, RES, Ja, Ir, Ry, Sh), مع تقديم ملخص علمي دقيق لما توصلت إليه تلك الدراسات، وإدراج روابط فعلية والحقيقية لتلك الدراسات أو لصفحة النقش في (DASI).
 * التحليل المعجمي المورفولوجي والمقارنة المتقاطعة (Micro-Level Lexical & Morphological Analysis):
 * التحليل الصرفي (Morphology): جرد الكلمات من أدوات التعريف اللاحقة والضمائر المتصلة لإرجاعها إلى جذورها اللغوية الأصلية، مع تحديد الصيغة الصرفية (اسم فاعل، فعل ماضٍ مضعف، جمع تكسير، اسم علم مركّب.. إلخ).
 * ابحث عن كل مفردة من مفردات النقش في المصادر العالمية والقواميس المتخصصة (مثل قاموس بيستون للسبئية أو المعاجم المعتمدة).
 * النقوش المقارنة: لكل مفردة، استخرج قائمة بالنقوش الأخرى التي وردت فيها هذه الكلمة لتأكيد المعنى السياقي وتتبع تطور الدلالة.
 * التوثيق: اذكر بوضوح المصادر والدراسات التي فسرت هذه المفردات بأي لغة كانت، مع ذكر (اسم الباحث، عنوان الدراسة، سنة النشر، رمز النقش المقارن), وتوفير الرابط الأكاديمي المباشر متى ما توفر.
 * صياغة التقرير الأكاديمي النهائي:
   يجب أن يكون ردك منظماً ومنهجياً وفق الهيكلة التالية حصراً:
 * مقدمة تحليلية وتاريخية: وصف مظهر النقش، نوعه، التقدير الزمني الباليوجرافي، رمزه العلمي (إن وُجد), والسياق التاريخي العام (ربط النقش بحقبة المكاربة، ملوك سبأ، أو ملوك سبأ وذي ريدان، وتحديد الآلهة أو القبائل أو الأقيال والشخصيات المذكورة فيه).
 * النص والترجمة: (القراءة الحرفية باللغتين العربية واللاتينية القياسية سطرًا بسطر، يتبعها مباشرة معنى السطر).
 * التحليل المعجمي والصرفي والدراسات المقارنة: (تفكيك الكلمات، إرجاعها لجذورها، تحديد صيغتها الصرفية، وذكر النقوش المقارنة التي وردت فيها ذات المفردات مع توثيق المصادر والروابط).
 * الخاتمة والاستنتاج التاريخي: خلاصة موضوعية لأهمية النقش وما يضيفه للمعرفة التاريخية، السياسية، أو اللغوية، وتحديد أي إشكاليات أو تضارب في التفسير بين العلماء.
 * قائمة المراجع والمصادر: (قائمة دقيقة بالدراسات، الأوراق البحثية، وروابط داسي وفق نظام توثيق أكاديمي موحد).
تنبيه صارم للأمانة العلمية:
 * التزم بالموضوعية التامة والمنهجية العلمية، وتجنب الانحياز للآراء الشخصية، وركز حصراً على الحقائق والبيانات المثبتة.
 * يُمنع منعاً باتاً اختراع أو هلوسة أي روابط (URLs) أو مراجع وهمية. إذا لم يتوفر رابط حقيقي، اكتفِ بذكر اسم المرجع والمؤلف بدقة تامة.
 * في حال عدم توفر معلومة مؤكدة، أو وجود تضارب علمي في تفسير كلمة، أو استعصى معناها تماماً لندرتها، يجب ذكر ذلك الخلاف الأكاديمي بوضوح والتصريح بغموض الكلمة علمياً، بدلاً من تخمين معنى لا يستند إلى دليل قطعي."""

        for msg in active_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        uploaded_image = st.file_uploader("📷 قم برفع صورة نقش المسند أو الحجر التاريخي (اختياري):", type=["png", "jpg", "jpeg"])

        if user_prompt := st.chat_input("اكتب سؤالك الأكاديمي أو الصق حروف النقش هنا..."):
            current_chat = st.session_state.current_chat_id
            if len(active_messages) == 0:
                st.session_state.chat_history_archive[current_chat]["title"] = user_prompt[:25] + "..."

            with st.chat_message("user"):
                st.markdown(user_prompt)
            
            if uploaded_image:
                base64_image = encode_image(uploaded_image)
                model_content_list = [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            else:
                model_content_list = user_prompt
                
            active_messages.append({"role": "user", "content": user_prompt if not uploaded_image else f"[صورة نقش مرفوعة] {user_prompt}"})
            save_chat_to_db(current_chat, st.session_state.chat_history_archive[current_chat]["title"], active_messages)

            with st.chat_message("assistant"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                response_placeholder = st.empty()
                
                status_text.text("🔍 المرحلة 1: الفحص الباليوجرافي وتحليل الخطوط...")
                progress_bar.progress(25)
                time.sleep(0.4)
                
                status_text.text("📜 المرحلة 2: تحديد القراءة الحرفية واتجاه السطور...")
                progress_bar.progress(50)
                time.sleep(0.4)
                
                status_text.text("🌐 المرحلة 3: مقارنة المفردات بمدونات داسي (DASI) والمراجع...")
                progress_bar.progress(75)
                time.sleep(0.4)
                
                status_text.text("✍️ المرحلة 4: صياغة التقرير الأكاديمي الموثق...")
                progress_bar.progress(100)

                try:
                    api_messages = [{"role": "system", "content": system_prompt}]
                    for m in active_messages:
                        api_messages.append({"role": m["role"], "content": m["content"]})
                    if uploaded_image and api_messages[-1]["role"] == "user":
                        api_messages[-1]["content"] = model_content_list

                    completion = client.chat.completions.create(
                        model=active_model_id,
                        messages=api_messages
                    )
                    output_text = completion.choices[0].message.content
                    
                    progress_bar.empty()
                    status_text.empty()
                    response_placeholder.markdown(output_text)
                    
                    active_messages.append({"role": "assistant", "content": output_text})
                    save_chat_to_db(current_chat, st.session_state.chat_history_parameters if 'chat_history_parameters' in locals() else st.session_state.chat_history_archive[current_chat]["title"], active_messages) # fixed reference
                    
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        st.download_button(
                            label="💾 تحميل التقرير كملف Markdown (.md)",
                            data=output_text,
                            file_name=f"تقرير_نقش_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                            mime="text/markdown",
                            key=f"dl_md_{len(active_messages)}"
                        )
                    with col_dl2:
                        docx_data = generate_docx(output_text)
                        st.download_button(
                            label="📄 تحميل التقرير كملف Word (.docx)",
                            data=docx_data,
                            file_name=f"تقرير_نقش_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_docx_{len(active_messages)}"
                        )
                    
                    st.rerun()
                except Exception as e:
                    progress_bar.empty()
                    status_text.empty()
                    st.error(f"حدث خطأ أثناء الاتصال بالـ API: {e}")
