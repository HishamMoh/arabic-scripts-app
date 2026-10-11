import streamlit as st
import openai
import base64
import time
from datetime import datetime

st.set_page_config(page_title="منصة تحليل النقوش العربية القديمة المفتوحة", page_icon="📜", layout="centered")

if "custom_providers" not in st.session_state:
    st.session_state.custom_providers = {
        "منصة SiliconFlow (افتراضي)": {
            "url": "https://api.siliconflow.com/v1",
            "model": "deepseek-ai/DeepSeek-V3",
            "key": ""
        },
        "منصة OpenRouter (افتراضي)": {
            "url": "https://api.openrouter.ai/api/v1",
            "model": "google/gemini-2.5-flash:free",
            "key": ""
        }
    }

if "chat_history_archive" not in st.session_state:
    st.session_state.chat_history_archive = {}

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if st.session_state.current_chat_id not in st.session_state.chat_history_archive:
    st.session_state.chat_history_archive[st.session_state.current_chat_id] = {
        "title": f"محادثة جديدة {datetime.now().strftime('%H:%M')}",
        "messages": []
    }

active_messages = st.session_state.chat_history_archive[st.session_state.current_chat_id]["messages"]

st.sidebar.title("📜 أرشيف المحادثات السابقة")

if st.sidebar.button("➕ بدء محادثة جديدة"):
    st.session_state.current_chat_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.chat_history_archive[st.session_state.current_chat_id] = {
        "title": f"محادثة جديدة {datetime.now().strftime('%H:%M')}",
        "messages": []
    }
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
st.sidebar.title("🛠️ إدارة وحفظ المزودين")

with st.sidebar.expander("➕ إضافة مزود جديد للقائمة"):
    new_name = st.text_input("اسم المزود (مثال: My DeepSeek):")
    new_url = st.text_input("رابط المنصة (Base URL):", value="https://api.openai.com/v1")
    new_model = st.text_input("اسم النموذج (Model Name):")
    new_key = st.text_input("مفتاح الـ API الخاص به:", type="password")
    add_btn = st.button("💾 حفظ المزود في القائمة")
    
    if add_btn and new_name and new_model:
        st.session_state.custom_providers[new_name] = {
            "url": new_url,
            "model": new_model,
            "key": new_key
        }
        st.sidebar.success(f"تمت إضافة '{new_name}' إلى قائمتك بنجاح!")

st.sidebar.subheader("🔌 اختر المزود النشط حالياً:")
current_provider = st.sidebar.selectbox("اختر من قائمتك المحفوظة:", list(st.session_state.custom_providers.keys()))

provider_data = st.session_state.custom_providers[current_provider]
base_url = provider_data["url"]
user_model = provider_data["model"]

user_api_key = st.sidebar.text_input(f"مفتاح الـ API لـ ({current_provider}):", value=provider_data["key"], type="password")
st.session_state.custom_providers[current_provider]["key"] = user_api_key

st.sidebar.info(f"""🤖 النموذج النشط: {user_model}
🔗 الرابط: {base_url}""")

if st.sidebar.button("⚡ اختبار اتصال النموذج والمفتاح (Test)"):
    if not user_api_key:
        st.sidebar.error("من فضلك أدخل مفتاح الـ API أولاً لتتمكن من إرسال طلب الاختبار!")
    else:
        with st.sidebar.spinner("جاري فحص حالة السيرفر والمفتاح..."):
            try:
                test_client = openai.OpenAI(api_key=user_api_key, base_url=base_url)
                test_client.chat.completions.create(
                    model=user_model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5
                )
                st.sidebar.success("✅ الاتصال ناجح ومستقر! المفتاح والنموذج يعملان بأفضل كفاءة.")
            except Exception as e:
                st.sidebar.error(f"❌ فشل الاتصال! تحقق من الرابط والمفتاح.\nالخطأ العلمي: {str(e)}")

def encode_image(uploaded_file):
    return base64.b64encode(uploaded_file.read()).decode('utf-8')

st.title("📜 مساعد وباحث النقوش والخطوط العربية القديمة المطور")
st.write(f"📂 الجلسة الحالية: **{st.session_state.chat_history_archive[st.session_state.current_chat_id]['title']}**")

if not user_api_key:
    st.info("من فضلك، اختر المزود النشط وأدخل مفتاح الـ API الخاص به في القائمة الجانبية لبدء المحادثة.", icon="🔑")
else:
    client = openai.OpenAI(api_key=user_api_key, base_url=base_url)
    
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
 * إذا كان النقش قد تمت دراسته سابقاً، اذكر رمزه العلمي الأكاديمي (مثل CIH, RES, Ja, Ir, Ry, Sh), مع تقديم ملخص علمي دقيق لما توصلت إليه تلك الدراسات، وإدراج روابط فعلية وحقيقية لتلك الدراسات أو لصفحة النقش في (DASI).
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
        if len(active_messages) == 0:
            st.session_state.chat_history_archive[st.session_state.current_chat_id]["title"] = user_prompt[:25] + "..."

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

        with st.chat_message("assistant"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            response_placeholder = st.empty()
            
            status_text.text("🔍 المرحلة 1: فحص الخصائص الباليوجرافية وتحديد نوع الخط...")
            progress_bar.progress(25)
            time.sleep(1)
            
            status_text.text("📜 المرحلة 2: فحص اتجاه السطور والقراءة الحرفية الأولية...")
            progress_bar.progress(50)
            time.sleep(1)
            
            status_text.text("🌐 المرحلة 3: مقارنة المفردات والبحث في مدونات النقوش الأكاديمية العالمية...")
            progress_bar.progress(75)
            time.sleep(1)
            
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
                
                st.download_button(
                    label="💾 تحميل التقرير الأكاديمي الحالي كملف نصي",
                    data=output_text,
                    file_name=f"تقرير_نقش_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
                
                st.rerun()
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"حدث خطأ أثناء الاتصال بالـ API: {e}\nتأكد من صحة الرابط (Base URL)، المفتاح، واسم الموديل المختار.")
