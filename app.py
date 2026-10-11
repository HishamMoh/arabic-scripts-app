import streamlit as st
import openai
import base64
import time
from datetime import datetime
import sqlite3
import json
import io
from docx import Document

st.set_page_config(page_title="منصة تحليل النقوش العربية القديمة المفتوحة", page_icon="📜", layout="centered")

# ==================== إعداد قاعدة البيانات SQLite ====================
def init_db():
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS chats
                 (chat_id TEXT PRIMARY KEY, title TEXT, messages TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS providers
                 (name TEXT PRIMARY KEY, url TEXT, models TEXT, api_key TEXT)''')
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
        "منصة SiliconFlow": {
            "url": "https://api.siliconflow.com/v1",
            "models": ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1"],
            "key": ""
        },
        "منصة OpenRouter": {
            "url": "https://api.openrouter.ai/api/v1",
            "models": ["google/gemini-2.5-flash:free", "deepseek/deepseek-chat"],
            "key": ""
        }
    }
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT name, url, models, api_key FROM providers")
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        for p_name, p_data in default_providers.items():
            c_inner = sqlite3.connect("chats_archive.db", check_same_thread=False)
            c_inner.execute("INSERT OR IGNORE INTO providers (name, url, models, api_key) VALUES (?, ?, ?, ?)",
                            (p_name, p_data["url"], json.dumps(p_data["models"], ensure_ascii=False), p_data["key"]))
            c_inner.commit()
            c_inner.close()
        return default_providers
    
    providers = {}
    for row in rows:
        name, url, models_json, api_key = row
        try:
            models_list = json.loads(models_json)
        except:
            models_list = ["default-model"]
        providers[name] = {
            "url": url,
            "models": models_list,
            "key": api_key
        }
    return providers

def save_provider_to_db(name, url, models_list, api_key):
    conn = sqlite3.connect("chats_archive.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO providers (name, url, models, api_key) VALUES (?, ?, ?, ?)",
              (name, url, json.dumps(models_list, ensure_ascii=False), api_key))
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

# ==================== القائمة الجانبية ====================
st.sidebar.title("📜 أرشيف المحادثات السابقة")

if st.sidebar.button("➕ بدء محادثة جديدة"):
    new_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_title = f"محادثة جديدة {datetime.now().strftime('%H:%M')}"
    st.session_state.current_chat_id = new_id
    st.session_state.chat_history_archive[new_id] = {
        "title": new_title,
        "messages": []
    }
    save_chat_to_db(new_id, new_title, [])
    st.sidebar.success("تم الانتقال إلى محادثة جديدة فارغة!")
    st.rerun()

st.sidebar.markdown("**المحادثات المحفوظة بالتاريخ:**")
for chat_id, chat_data in list(st.session_state.chat_history_archive.items()):
    btn_label = f"🕒 {chat_data['title']}"
    if chat_id == st.session_state.current_chat_id:
        btn_label = f"👉 {chat_data['title']} (نشطة حالياً)"
    
    if st.sidebar.button(btn_label, key=f"nav_{chat_id}"):
        st.session_state.current_chat_id = chat_id
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("🛠️ إدارة المزودين والنفائس")

# نموذج إضافة مزود جديد مع تفريغ الخانات تلقائياً
with st.sidebar.expander("➕ إضافة مزود جديد ونماذجه"):
    with st.form("add_provider_form", clear_on_submit=True):
        new_name = st.text_input("اسم المزود (مثال: My Provider):")
        new_url = st.text_input("رابط المنصة (Base URL):", value="https://api.openai.com/v1")
        new_models_str = st.text_area("أسماء النماذج مفصولة بفواصل (Model Names):", value="gpt-4o, gpt-3.5-turbo")
        new_key = st.text_input("مفتاح الـ API الخاص به:", type="password")
        submitted = st.form_submit_button("💾 حفظ المزود في القائمة")
        
        if submitted and new_name and new_models_str:
            models_list = [m.strip() for m in new_models_str.split(",") if m.strip()]
            st.session_state.custom_providers[new_name] = {
                "url": new_url,
                "models": models_list,
                "key": new_key
            }
            save_provider_to_db(new_name, new_url, models_list, new_key)
            st.success(f"تمت إضافة '{new_name}' ونماذجه بنجاح وتفريغ الخانات تلقائياً!")
            st.rerun()

st.sidebar.subheader("🔌 اختر المزود النشط حالياً:")
current_provider = st.sidebar.selectbox("اختر من قائمتك المحفوظة:", list(st.session_state.custom_providers.keys()))

provider_data = st.session_state.custom_providers[current_provider]
base_url = provider_data["url"]
available_models = provider_data["models"]

st.sidebar.subheader("🎯 اختر النموذج النشط:")
user_model = st.sidebar.selectbox("النماذج المتاحة للمزود:", available_models)

user_api_key = st.sidebar.text_input(f"مفتاح الـ API لـ ({current_provider}):", value=provider_data["key"], type="password")
st.session_state.custom_providers[current_provider]["key"] = user_api_key
save_provider_to_db(current_provider, base_url, available_models, user_api_key)

st.sidebar.info(f"🤖 النموذج النشط: {user_model}\n🔗 الرابط: {base_url}")

if st.sidebar.button("⚡ اختبار اتصال النموذج والمفتاح (Test)"):
    if not user_api_key:
        st.sidebar.error("من فضلك أدخل مفتاح الـ API أولاً لتتمكن من إرسال طلب الاختبار!")
    else:
        with st.sidebar.spinner("جاري فحص حالة السيرفر والمفتاح..."):
            try:
                test_client = openai.OpenAI(api_key=user_api_key, base_url=base_url, timeout=120.0)
                test_client.chat.completions.create(
                    model=user_model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=10
                )
                st.sidebar.success("✅ الاتصال ناجح ومستقر! المفتاح والنموذج يعملان بأفضل كفاءة.")
            except Exception as e:
                st.sidebar.error(f"❌ فشل الاتصال! تحقق من الرابط والمفتاح.\nالخطأ العلمي: {str(e)}")

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

if not user_api_key:
    st.info("من فضلك، أدخل مفتاح الـ API الخاص بالمزود في القائمة الجانبية لبدء المحادثة وتحليل النقوش.", icon="🔑")
else:
    client = openai.OpenAI(api_key=user_api_key, base_url=base_url, timeout=120.0)
    
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
                    model=user_model,
                    messages=api_messages
                )
                output_text = completion.choices[0].message.content
                
                progress_bar.empty()
                status_text.empty()
                response_placeholder.markdown(output_text)
                
                active_messages.append({"role": "assistant", "content": output_text})
                save_chat_to_db(current_chat, st.session_state.chat_history_archive[current_chat]["title"], active_messages)
                
                # أزرار تحميل التقرير بصيغتي Markdown و Word (docx)
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
                st.error(f"حدث خطأ أثناء الاتصال بالـ API أو استلام التقرير النهائي: {e}\nتأكد من صحة الرابط (Base URL)، المفتاح، والنموذج المختار.")
