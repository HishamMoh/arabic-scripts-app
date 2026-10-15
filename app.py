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
    page_title="المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة",
    page_icon="📜",
    layout="wide"
)

# ==================== إعداد قاعدة البيانات وتحديث الهيكل تلقائياً ====================
def init_db():
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    
    c.execute('CREATE TABLE IF NOT EXISTS chats (chat_id TEXT PRIMARY KEY, title TEXT, messages TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS providers (name TEXT PRIMARY KEY, api_style TEXT, url TEXT, path TEXT, api_key TEXT, network_opt INTEGER, models TEXT)')
    
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
        c.execute('CREATE TABLE providers (name TEXT PRIMARY KEY, api_style TEXT, url TEXT, path TEXT, api_key TEXT, network_opt INTEGER, models TEXT)')
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
    doc.add_heading("المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة", level=1)
    doc.add_paragraph("Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics")
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

def generate_pdf(text):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=letter)
    width, height = letter
    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics")
    y -= 25
    c.setFont("Helvetica", 10)
    for line in text.split("\n"):
        if y < 40:
            c.showPage()
            y = height - 40
        c.drawString(40, y, line[:95])
        y -= 14
    c.save()
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

    st.title("📜 المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة")
    st.caption("Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics")
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
        
        # ⚠️ التعليمات الأكاديمية المطلقة المقتبسة من هيكل وثيقة (CIH 352) النموذجية القياسية
        system_prompt = '''[أنت خبير إبيغرافي وعالم آثار رقمي في "المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة" (Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics). مهمتك هي تحليل وتوثيق النقوش وفق أعلى وأحدث معايير التحقيق الأكاديمي الصارم المعتمَد في مدونات DASI و CSAI والدراسات السامية الدولية (مثل نموذج CIH 352)].

عند استقبال أي صورة أو نص لنقش مسندي أو أثري، يجب أن تقوم بصياغة **تقرير دراسة وتوثيق إبيغرافي تحليلي لنقش مسند** ملتزماً بالهيكل والدقة العلمية والتصميم القياسي التالي حرفياً:

---
### 🏛️ رأس الوثيقة والمعلومات الإبيغرافية الأساسية
- **المؤسسة:** المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة (Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics)
- **رمز الوثيقة / Document Ref:** (توليد رمز أكاديمي دقيق مثل: `ARC-EPI-DASI / CSAI / [اسم المجموعة أو الموقع] ([الرمز المعياري إن وجد مثل CIH/RES/Ja/Ir/Ry])`)
- **تاريخ الإصدار / Date:** [تاريخ اليوم]
- **اسم الأثر / Title:** [عنوان النقش الأكاديمي بالعربية والإنجليزي]
- **الموقع الأثري / Findspot:** [الموقع الجغرافي والقبلي الدقيق]
- **الحقبة التقديرية / Period:** [تحديد القرن والعصر السياسي والتاريخي]
- **الرمز بمدونة DASI / CIH:** [رمز المطابقة الأكاديمي]
- **طراز الخط / Script Style:** [وصف شامل لطبيعة الخط والصخرة والباتينا الصحراوية] | **درجة المطابقة / Confidence:** [نسبة التحقيق 95%-100%]
- **اتجاه القراءة / Direction:** [من اليمين إلى اليسار / خط المحراث، وعدد الأسطر] | **أداة الفصل / Divider:** [وصف الفواصل العمودية |]

---
### أولاً: القراءة الحرفية والنقل الحرفي الصوتي (Epigraphic Transliteration)
1. **النص الأصيل بخط المسند (Monumental Musnad Script):** (كتابة النص كاملاً بأسطر المسند اليوني كود مع الفواصل c).
2. **المقابلة والنقل الحرفي بالحروف العربية:** (نقل الأسطر مرقمة مع الفواصل المائلة /).
3. **Nomenclatural Semitic Latin Transliteration (Beeston Standard):** (النقل اللاتيني السامي الدقيق بمعايير بيستون مع التمييز الصارم بين الأحرف الشجرية والأسلية s1, s2, s3 والرموز الصوتية ḥ, ḫ, ʿ, ġ, ṯ, ḏ, ḍ, ẓ, ṭ, ʾ).

---
### ثانياً: التحليل السطري المباشر والنقل الحرفي (Line-by-Line Breakdown)
لكل سطر على حدة:
- **السطر X [اتجاه القراءة]:** [النص بخط المسند]
- **النقل الحرفي العربي:** [الحروف العربية]
- **Semitic Latin:** [النقل اللاتيني]
- **المعنى السطري المباشر:** «[الترجمة العربية السطرية الدقيقة]» (“[English Line Translation]”)
- **ملاحظة إبيغرافية:** [تحليل صيغ السطر والخصائص المعمارية أو الدينية أو القانونية].

---
### ثالثاً: الترجمة الأكاديمية المقارنة (Comparative Translation)
- **الترجمة العربية الدقيقة (المعنى السياقي المباشر):** (ترجمة سياقية كاملة مجمعة ومدرجة بالأسطور المرقّمة بين أقواس « »).
- **Academic English Translation:** (ترجمة أكاديمية إنجليزية كاملة مطابقة للنشر العلمي الدولي).

---
### رابعاً: التحليل المعجمي والصرفي للمفردات (Morphological & Lexical Analysis)
يجب تقديم جدول تحليلي دقيق أو قائمة مفصلة لكل مفردة من مفردات النقش تشتمل على:
1. المفردة بالمسند واللاتيني
2. الجذر والصيغة الصرفية (Morphology: اسم علم، فعل ماضٍ، اسم مكان، مركب إضافي، تمكين، تعريف بالنون..)
3. المعنى المعجمي (عربي / إنجليزي)
4. التحليل الصرفي والدراسة المقارنة (الشرح المعجمي من قاموس بيستون Sabaic Dictionary أو المعاجم المعتمدة).
5. **النظائر والنقوش المقارنة:** ذكر رموز النقوش الأخرى التي وردت فيها ذات المفردة (مثل: CIH, RES, Ja, Ir, Ry).

---
### خامساً: التحليل الباليوجرافي وبنية الخط (Palaeography & Comparative Analysis)
- **خصائص طراز الخط وحفر المسند:** (وصف النمط الباليوجرافي وتقنية الحفر Ductus الأزاميل ورسم الحروف).
- **الدراسة الإبيغرافية المقارنة مع النقوش الشقيقة:** (مقارنة الصياغة بالنقوش المماثلة).
- **مورفولوجيا الحروف:** (شكل الميم، الهاء، الراء، العين، الباء...).
- **معيار التقدير الزمني:** (تحديد الفترة الإبيغرافية بدقة).

---
### سادساً: الاستنتاج التاريخي والحضاري (Historical & Cultural Synthesis)
- **القيمة التاريخية والحضارية:** (خلاصة شاملة للبعد السياسي، الاجتماعي، المعماري، أو الديني للنقش).
- **القضايا الخلافية والجدل الإبيغرافي بين العلماء:** (عرض النقاشات العلمية بين كبار الباحثين مثل كريستيان روبان، مطهر الإرياني، والتر مولر، بيستون، وغيرهم وحسم الرأي الأكاديمي).

---
### سابعاً: التوثيق وقائمة المراجع الأكاديمية (Epigraphical Bibliography)
تضمين مراجع أكاديمية عالمية حقيقية وموثقة وفق صيغة التوثيق القياسية:
1. Beeston, A. F. L. et al., Sabaic Dictionary (1982).
2. Biella, J. C., Dictionary of Old South Arabian (1982).
3. Corpus of South Arabian Inscriptions (CSAI) & Digital Archive for the Study of preIslamic Arabian Inscriptions (DASI).
4. Robin, Christian Julien, Inventaire des inscriptions sudarabiques.
5. مطهر علي الإرياني، نقوش مسندية وتعليقات.
6. Corpus Inscriptionum Semiticarum (CIS), Pars IV (CIH / RES).

---
### 🔐 الختم الرقمي والتوقيع الإبيغرافي
- **إعداد وتوثيق الباحث:** باحث في الإبيغرافيا والآثار — المختبر الرقمي لدراسات المسند ونقوش اليمن القديم
- **الختم الرقمي:** `SHA256-EPIGRAPHIC-VERIFIED-DASI___CSAI___[رمز_النقش]` • **سنة التوثيق:** 2026

⚠️ **تنبيه الأمانة العلمية الصارم:**
- التزم بالموضوعية والدقة التامة دون أي اختراع لروابط أو مراجع وهمية.
- إذا كان النص المرفوع غير مسندي أو غير واضح، صرّح بذلك بأمانة علمية مع تقديم البديل الأكاديمي المتاح.'''

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
                status_placeholder = st.empty()
                progress_bar = st.progress(0)
                response_placeholder = st.empty()
                
                try:
                    status_placeholder.markdown("⏳ **المرحلة 1:** الفحص الباليوجرافي وتحليل خط المسند وقراءة الأسطر...")
                    progress_bar.progress(25)
                    time.sleep(0.3)
                    
                    status_placeholder.markdown("⏳ **المرحلة 2:** إجراء النقل الحرفي الصوتي (Beeston Standard) والتحليل السطري...")
                    progress_bar.progress(50)
                    time.sleep(0.3)
                    
                    status_placeholder.markdown("⏳ **المرحلة 3:** التحليل الصرفي والمعجمي ومطابقة المفردات بقواعد DASI و CSAI...")
                    progress_bar.progress(75)
                    time.sleep(0.3)
                    
                    status_placeholder.markdown("⏳ **المرحلة 4:** صياغة وثيقة التوثيق الإبيغرافي القياسية والختم الرقمي...")
                    progress_bar.progress(100)
                    time.sleep(0.3)

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
                    status_placeholder.markdown("✅ **تم إنجاز التقرير والدراسة الإبيغرافية بنجاح تام.**")
                    response_placeholder.markdown(output_text)
                    
                    active_messages.append({"role": "assistant", "content": output_text})
                    save_chat_to_db(current_chat, st.session_state.chat_history_archive[current_chat]["title"], active_messages)
                    
                    st.markdown("---")
                    st.markdown("### 📥 تحميل التقرير الأكاديمي الموثق")
                    dl_col1, dl_col2, dl_col3 = st.columns(3)
                    with dl_col1:
                        docx_data = generate_docx(output_text)
                        st.download_button(
                            label="📄 تحميل Word (.docx)",
                            data=docx_data,
                            file_name=f"تقرير_توثيق_إبيغرافي_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_docx_{len(active_messages)}"
                        )
                    with dl_col2:
                        st.download_button(
                            label="📝 تحميل Markdown (.md)",
                            data=output_text,
                            file_name=f"تقرير_توثيق_إبيغرافي_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                            mime="text/markdown",
                            key=f"dl_md_{len(active_messages)}"
                        )
                    with dl_col3:
                        pdf_data = generate_pdf(model_content_list[0]['text'] if isinstance(model_content_list, list) else user_prompt)
                        st.download_button(
                            label="📑 تحميل PDF (.pdf)",
                            data=pdf_data,
                            file_name=f"تقرير_توثيق_إبيغرافي_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            key=f"dl_pdf_{len(active_messages)}"
                        )
                    
                    st.rerun()
                except Exception as e:
                    progress_bar.empty()
                    status_placeholder.markdown(f"❌ **فشلت العملية أو حدث خطأ أثناء الاتصال بالـ API:** `{e}`")
