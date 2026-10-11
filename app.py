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

# ==================== إعداد قاعدة البيانات SQLite ====================
def init_db():
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS chats
                 (chat_id TEXT PRIMARY KEY, title TEXT, messages TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS providers
                 (name TEXT PRIMARY KEY, api_style TEXT, url TEXT, path TEXT, api_key TEXT, network_opt INTEGER, models TEXT)''')
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
            "api_style": "متوافق مع OpenAI API",
            "url": "https://api.siliconflow.com/v1",
            "path": "/chat/completions",
            "key": "",
            "network_opt": True,
            "models": {
                "deepseek-ai/DeepSeek-V3": {
                    "alias": "DeepSeek V3 الرسمي",
                    "type": "دردشة",
                    "vision": False,
                    "tools": True,
                    "reasoning": False,
                    "context": 64000,
                    "max_tokens": 4096
                },
                "deepseek-ai/DeepSeek-R1": {
                    "alias": "DeepSeek R1 الاستنتاجي",
                    "type": "دردشة",
                    "vision": False,
                    "tools": True,
                    "reasoning": True,
                    "context": 64000,
                    "max_tokens": 4096
                }
            }
        },
        "OpenRouter": {
            "api_style": "متوافق مع OpenAI API",
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
    c.execute("SELECT name, api_style, url, path, api_key, network_opt, models FROM providers")
    rows = c.fetchall()
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
            "api_style": api_style if api_style else "متوافق مع OpenAI API",
            "url": url,
            "path": path if path else "/chat/completions",
            "key": api_key,
            "network_opt": bool(network_opt),
            "models": models_dict
        }
    return providers

def save_provider_to_db(name, p_data):
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO providers (name, api_style, url, path, api_key, network_opt, models) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (name, p_data.get("api_style", "متوافق مع OpenAI API"), p_data["url"], p_data.get("path", "/chat/completions"), p_data["key"], 1 if p_data.get("network_opt", True) else 0, json.dumps(p_data["models"], ensure_ascii=False)))
    conn.commit()
    conn.close()

# ==================== تهيئة Session State ====================
if "custom_providers" not in st.session_state:
    st.session_state.custom_providers = load_all_providers()

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

active_messages = st.session_state.chat_history_archive[st.session_state.current_chat_id]["messages"]

# ==================== القائمة الجانبية (الإعدادات والمزودين) ====================
st.sidebar.title("⚙️ الإعدادات والمزودون")

# 1. قسم إضافة مزود جديد (شاشة إضافة مزود المطابقة للصورة)
with st.sidebar.expander("➕ إضافة مزود جديد"):
    with st.form("add_new_provider_form", clear_on_submit=True):
        st.subheader("إضافة مزود")
        add_p_name = st.text_input("الاسم *")
        add_p_style = st.selectbox("نمط API", ["متوافق مع OpenAI API", "Anthropic Claude API (قريباً)", "Custom REST API"])
        submitted_p = st.form_submit_button("إضافة")
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
                    st.success(f"تم إنشاء المزود '{p_key_name}' بنجاح!")
                    st.rerun()
                else:
                    st.error("اسم المزود موجود بالفعل!")
            else:
                st.error("الاسم مطلوب!")

st.sidebar.markdown("---")
st.sidebar.subheader("🔌 اختر المزود للتعديل أو الاستخدام:")
current_provider_name = st.sidebar.selectbox("قائمة المزودين:", list(st.session_state.custom_providers.keys()))

p_obj = st.session_state.custom_providers[current_provider_name]

# واجهة تعديل بيانات المزود (طابق الصورة 2)
st.sidebar.markdown(f"### ⚙️ إعدادات المزود: `{current_provider_name}`")
p_style = st.sidebar.selectbox("نمط API", ["متوافق مع OpenAI API"], index=0, key=f"style_{current_provider_name}")

col_k1, col_k2 = st.sidebar.columns([3, 1])
with col_k1:
    p_key = st.text_input("مفتاح API", value=p_obj["key"], type="password", key=f"key_{current_provider_name}")
with col_k2:
    st.markdown("<br>", unsafe_allow_html=True)
    test_key_btn = st.button("تحقق", key=f"chk_key_{current_provider_name}")

p_host = st.sidebar.text_input("مضيف API (Base URL)", value=p_obj["url"], key=f"host_{current_provider_name}")
p_path = st.sidebar.text_input("مسار API", value=p_obj.get("path", "/chat/completions"), key=f"path_{current_provider_name}")

full_preview_url = p_host.rstrip('/') + p_path
st.sidebar.caption(f"🔍 معاينة الرابط الكامل: `{full_preview_url}`")

p_network = st.sidebar.toggle("تحسين توافق الشبكة", value=p_obj.get("network_opt", True), key=f"net_{current_provider_name}")
st.sidebar.caption("فعل هذا الخيار فقط عند الحاجة لتجاوز مهل الشبكة.")

# حفظ أي تغيير في بيانات المزود تلقائياً
p_obj["api_style"] = p_style
p_obj["key"] = p_key
p_obj["url"] = p_host
p_obj["path"] = p_path
p_obj["network_opt"] = p_network
save_provider_to_db(current_provider_name, p_obj)

# زر التحقق من المفتاح والربط المباشر
if test_key_btn:
    if not p_key:
        st.sidebar.error("يرجى إدخال مفتاح API أولاً!")
    else:
        with st.sidebar.spinner("جاري اختبار المفتاح والاتصال..."):
            try:
                t_client = openai.OpenAI(api_key=p_key, base_url=p_host, timeout=30.0)
                t_client.models.list()
                st.sidebar.success("✅ المفتاح ورابط API صالحان ومستقران!")
            except Exception as e:
                st.sidebar.error(f"❌ فشل التحقق: {str(e)}")

st.sidebar.markdown("---")
# إدارة نماذج المزود (طابق الصورة 2 والصورة 3)
st.sidebar.subheader("🤖 النموذج والمواصفات")

col_m_actions1, col_m_actions2 = st.sidebar.columns(2)
with col_m_actions1:
    add_model_exp = st.checkbox("➕ جديد", key=f"add_m_flag_{current_provider_name}")
with col_m_actions2:
    if st.button("🔄 إعادة تعيين", key=f"reset_m_{current_provider_name}"):
        p_obj["models"] = {}
        save_provider_to_db(current_provider_name, p_obj)
        st.rerun()

# إضافة نموذج جديد
if add_model_exp:
    with st.sidebar.form(key=f"add_m_form_{current_provider_name}"):
        st.markdown("**إضافة نموذج جديد للمزود**")
        new_m_id = st.text_input("معرف النموذج (Model ID) *")
        new_m_alias = st.text_input("اسم مستعار (اختياري)")
        new_m_type = st.selectbox("نوع النموذج", ["دردشة", "استنتاج", "تضمين Embeddings"])
        new_m_vis = st.checkbox("الرؤية (Vision)", value=True)
        new_m_tools = st.checkbox("استخدام الأدوات", value=True)
        new_m_reasoning = st.checkbox("الاستنتاج (Reasoning)", value=False)
        new_m_ctx = st.number_input("نافذة السياق (Context Window)", value=128000, step=1000)
        new_m_max_tok = st.number_input("الحد الأقصى للمخرجات", value=4096, step=512)
        
        save_m_btn = st.form_submit_button("حفظ النموذج")
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
                st.success("تمت إضافة النموذج بنجاح!")
                st.rerun()

# اختيار النموذج النشط حالياً
model_keys = list(p_obj["models"].keys())
if not model_keys:
    st.sidebar.warning("لا يوجد نماذج مضافة لهذا المزود. يرجى إضافة نموذج جديد بالضغط على '➕ جديد'.")
    active_model_id = None
else:
    active_model_id = st.sidebar.selectbox(
        "اختر النموذج النشط:",
        model_keys,
        format_func=lambda x: f"{p_obj['models'][x].get('alias', x)} ({x})"
    )

    m_data = p_obj["models"][active_model_id]
    
    # بطاقة عرض النموذج وتعديله واختباره (طابق الصورة 2 وصورة 3)
    with st.sidebar.container():
        st.markdown(f"""
        <div style="border:1px solid #e0e0e0; border-radius:10px; padding:10px; background-color:#fafafa; margin-bottom:10px;">
            <b>📌 {m_data.get('alias', active_model_id)}</b><br>
            <small>ID: {active_model_id}</small><br>
            <small>⚙️ السياق: {m_data.get('context', 128000):,} Tokens | الرؤية: {'✅' if m_data.get('vision') else '❌'}</small>
        </div>
        """, unsafe_allow_html=True)
        
        c_m1, c_m2, c_m3 = st.sidebar.columns(3)
        with c_m1:
            test_m_btn = st.button("🧪 اختبار", key=f"t_m_{active_model_id}")
        with c_m2:
            edit_m_btn = st.button("⚙️ تعديل", key=f"e_m_{active_model_id}")
        with c_m3:
            del_m_btn = st.button("🗑️ حذف", key=f"d_m_{active_model_id}")

        if del_m_btn:
            del p_obj["models"][active_model_id]
            save_provider_to_db(current_provider_name, p_obj)
            st.rerun()

        if test_m_btn:
            if not p_key:
                st.sidebar.error("أدخل المفتاح أولاً للاختبار!")
            else:
                with st.sidebar.spinner(f"جاري اختبار النموذج {active_model_id}..."):
                    try:
                        tm_client = openai.OpenAI(api_key=p_key, base_url=p_host, timeout=60.0)
                        res = tm_client.chat.completions.create(
                            model=active_model_id,
                            messages=[{"role": "user", "content": "ping"}],
                            max_tokens=10
                        )
                        st.sidebar.success("✅ النموذج يعمل وتلقى الاستجابة بنجاح!")
                    except Exception as ex:
                        st.sidebar.error(f"❌ فشل اختبار النموذج: {str(ex)}")

        if edit_m_btn:
            st.session_state[f"show_edit_m_{active_model_id}"] = True

        if st.session_state.get(f"show_edit_m_{active_model_id}", False):
            with st.sidebar.expander("🛠️ تعديل النموذج الحالي", expanded=True):
                with st.form(key=f"edit_form_{active_model_id}"):
                    e_alias = st.text_input("اسم مستعار", value=m_data.get("alias", ""))
                    e_type = st.selectbox("نوع النموذج", ["دردشة", "استنتاج", "تضمين Embeddings"], index=0 if m_data.get("type")=="دردشة" else 1)
                    e_vis = st.checkbox("الرؤية (Vision)", value=m_data.get("vision", True))
                    e_tools = st.checkbox("استخدام الأدوات", value=m_data.get("tools", True))
                    e_reasoning = st.checkbox("الاستنتاج", value=m_data.get("reasoning", False))
                    e_ctx = st.number_input("نافذة السياق", value=m_data.get("context", 128000))
                    e_max_tok = st.number_input("الحد الأقصى للمخرجات", value=m_data.get("max_tokens", 4096))
                    
                    save_edit_b = st.form_submit_button("حفظ التعديلات")
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
                        st.success("تم تحديث بيانات النموذج!")
                        st.rerun()

st.sidebar.markdown("---")
# قسم أرشيف المحادثات
st.sidebar.title("📜 أرشيف المحادثات")
if st.sidebar.button("➕ بدء محادثة جديدة"):
    new_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_title = f"محادثة جديدة {datetime.now().strftime('%H:%M')}"
    st.session_state.current_chat_id = new_id
    st.session_state.chat_history_archive[new_id] = {
        "title": new_title,
        "messages": []
    }
    save_chat_to_db(new_id, new_title, [])
    st.rerun()

for c_id, c_data in list(st.session_state.chat_history_archive.items()):
    btn_l = f"🕒 {c_data['title']}"
    if c_id == st.session_state.current_chat_id:
        btn_l = f"👉 {c_data['title']} (نشطة)"
    if st.sidebar.button(btn_l, key=f"nav_{c_id}"):
        st.session_state.current_chat_id = c_id
        st.rerun()

# ==================== الواجهة الرئيسية والتفاعل ====================
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

st.title("📜 مساعد وباحث النقوش والخطوط العربية القديمة المطور")
st.write(f"📂 الجلسة الحالية: **{st.session_state.chat_history_archive[st.session_state.current_chat_id]['title']}**")

if not p_key:
    st.info("من فضلك أدخل مفتاح الـ API الخاص بالمزود في القائمة الجانبية لبدء المحادثة وتحليل النقوش.", icon="🔑")
elif not active_model_id:
    st.warning("يرجى إضافة أو اختيار نموذج نشط للمزود الحالي لبدء العمل.")
else:
    client = openai.OpenAI(api_key=p_key, base_url=p_host, timeout=120.0)
    
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

    uploaded_image = st.file_uploader("قم برفع صورة النقش التاريخي لتحليله (اختياري):", type=["png", "jpg", "jpeg"])

    if user_prompt := st.chat_input("اكتب استفسارك أو انسخ حروف النقش هنا..."):
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
            
        active_messages.append({"role": "user", "content": user_prompt if not uploaded_image else f"[صورة مرفوعة] {user_prompt}"})
        save_chat_to_db(current_chat, st.session_state.chat_history_archive[current_chat]["title"], active_messages)

        with st.chat_message("assistant"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            response_placeholder = st.empty()
            
            status_text.text("🔍 المرحلة 1: فحص الخصائص الباليوجرافية وتحديد نوع الخط...")
            progress_bar.progress(25)
            time.sleep(0.5)
            
            status_text.text("📜 المرحلة 2: فحص اتجاه السطور والقراءة الحرفية الأولية...")
            progress_bar.progress(50)
            time.sleep(0.5)
            
            status_text.text("🌐 المرحلة 3: مقارنة المفردات والبحث في مدونات النقوش الأكاديمية العالمية...")
            progress_bar.progress(75)
            time.sleep(0.5)
            
            status_text.text("✍️ المرحلة 4: صياغة التقرير التاريخي والمعجمي النهائي الموثق...")
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
                        label="💾 تحميل كملف Markdown (.md)",
                        data=output_text,
                        file_name=f"تقرير_نقش_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                        key=f"dl_md_{len(active_messages)}"
                    )
                with col_dl2:
                    docx_data = generate_docx(output_text)
                    st.download_button(
                        label="📄 تحميل كملف Word (.docx)",
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
