import streamlit as st
import openai
import base64

# إعداد واجهة المستخدم لتطبيق الشات العالمي المفتوح والمخصص
st.set_page_config(page_title="محلل النقوش العربية القديمة المخصص", page_icon="📜", layout="centered")
st.title("📜 مساعد وباحث النقوش والخطوط العربية القديمة المخصص")
st.write("مرحباً بك! تطبيق ويب مفتوح بالكامل يتيح لك حفظ وإدارة قائمة مزودي الـ AI الخاصة بك بدقة لتحليل وقراءة نقوش خط المسند.")

# 1. تهيئة قائمة المزودين الافتراضية داخل ذاكرة المتصفح إذا لم تكن موجودة
if "custom_providers" not in st.session_state:
    st.session_state.custom_providers = {
        "منصة SiliconFlow (افتراضي)": {
            "url": "https://siliconflow.com",
            "model": "deepseek-ai/DeepSeek-V3",
            "key": ""
        },
        "منصة OpenRouter (افتراضي)": {
            "url": "https://openrouter.ai",
            "model": "google/gemini-2.5-flash:free",
            "key": ""
        }
    }

st.sidebar.title("🛠️ إدارة وحفظ المزودين")

# 2. نموذج لإضافة مزود جديد وحفظه في القائمة
with st.sidebar.expander("➕ إضافة مزود جديد للقائمة"):
    new_name = st.text_input("اسم المزود (مثال: My DeepSeek):")
    new_url = st.text_input("رابط المنصة (Base URL):", value="https://openai.com")
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

# 3. قائمة اختيار المزود الحالي النشط من القائمة المخزنة
st.sidebar.markdown("---")
st.sidebar.subheader("🔌 اختر المزود النشط حالياً:")
current_provider = st.sidebar.selectbox("اختر من قائمتك المحفوظة:", list(st.session_state.custom_providers.keys()))

# استخراج بيانات المزود الذي تم اختياره من القائمة لتشغيله
provider_data = st.session_state.custom_providers[current_provider]
base_url = provider_data["url"]
user_model = provider_data["model"]

# السماح للمستخدم برؤية وتحديث المفتاح الخاص بالمزود المختار مباشرة
user_api_key = st.sidebar.text_input(f"مفتاح الـ API لـ ({current_provider}):", value=provider_data["key"], type="password")
st.session_state.custom_providers[current_provider]["key"] = user_api_key

# عرض تفاصيل السيرفر النشط للتأكيد
st.sidebar.info(f"🤖 النموذج النشط: {user_model}\n🔗 الرابط: {base_url}")

# ⚡ 4. ميزة اختبار جودة اتصال النموذج والمفتاح المضافة حديثاً
if st.sidebar.button("⚡ اختبار اتصال النموذج والمفتاح (Test)"):
    if not user_api_key:
        st.sidebar.error("من فضلك أدخل مفتاح الـ API أولاً لتتمكن من إرسال طلب الاختبار!")
    else:
        with st.sidebar.spinner("جاري فحص حالة السيرفر والمفتاح..."):
            try:
                test_client = openai.OpenAI(api_key=user_api_key, base_url=base_url)
                # إرسال طلب فحص مصغر جداً وغير مكلف لتأكيد جهوزية الـ API
                test_client.chat.completions.create(
                    model=user_model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5
                )
                st.sidebar.success("✅ الاتصال ناجح ومستقر! المفتاح والنموذج يعملان بأفضل كفاءة.")
            except Exception as e:
                st.sidebar.error(f"❌ فشل الاتصال! تحقق من الرابط والمفتاح.\nالخطأ العلمي: {str(e)}")

# دالة لتحويل الصور المرفوعة إلى صيغة Base64 المفهومة لجميع الـ APIs
def encode_image(uploaded_file):
    return base64.b64encode(uploaded_file.read()).decode('utf-8')

if not user_api_key:
    st.info("من فضلك، اختر المزود النشط وأدخل مفتاح الـ API الخاص به في القائمة الجانبية لبدء المحادثة.", icon="🔑")
else:
    # تهيئة اتصال العميل الموحد المفتوح المتوافق مع معيار OpenAI الشامل
    client = openai.OpenAI(api_key=user_api_key, base_url=base_url)
    
    # تعريف تعليمات النظام الصارمة (System Instructions) الخاصة بدراسة النقوش
    system_prompt = """[أنت باحث أكاديمي رفيع المستوى، وعالم آثار رقمي ومؤرخ متخصص في النقوش والكتابات العربية القديمة (خط المسند بجناحيه الجنوبي والشمالي، واللغات: السبئية، الحميرية، القتبانية، المعينية، والحضرمية، بالإضافة إلى النقوش الثمودية واللحيانية والصفاوية). اقرأ التعليمات الأكاديمية التالية بصرامة ونفذها خطوة بخطوة وفق منهجية علمية وموضوعية تامة، دون إهمال أي بند]
مهمتك هي العمل كـ "باحث ومحلل أكاديمي لنقوش المسند والخطوط الشقيقة"، وتطبيق الخطوات المنهجية التالية عند استقبال أي صورة نقش أو نص حرفي:
 * التحليل الباليوجرافي، بنية النقش، والتقدير الزمني (Palaeography, Structure & Dating):
 * فحص النقش وتحديد نوع الخط والنمط (رسمي، مخربشات صخرية، خط زبور).
 * تحديد اتجاه القراءة لكل سطر بدقة (من اليمين لليسار، أو خط المحراث)، وتوضيح أدوات الفصل المستخدمة.
 * تقديم تقدير أولي للفترة الزمنية بناءً على الخصائص الباليوجرافية وتطور شكل الحروف وخصائص الزخرفة إن وجدت.
 * القراءة الحرفية والترجمة السطرية المباشرة (Transliteration & Translation):
 * القراءة الحرفية: قم بنقل النص حرفياً سطرًا بسطر إلى الحروف العربية الحديثة والحروف اللاتينية المعتمدة أكاديمياً.
 * المعنى السطري: ضع تحت كل سطر قمت بنقله، المعنى والترجمة الدقيقة له بناءً على السياق.
 * البحث الأكاديمي الشامل لمحتوى النقش (Macro-Level Inscription Search):
 * ابحث عن محتوى النقش كاملاً في قواعد البيانات الأكاديمية العالمية ومدونات النقوش المتخصصة (DASI، و CSAI).
 * صياغة التقرير الأكاديمي النهائي: مقدمة تحليلية وتاريخية، النص والترجمة، التحليل المعجمي والصرفي، الخاتمة والاستنتاج التاريخي، وقائمة المراجع والمصادر.
التزم بالموضوعية التامة، ويُمنع منعاً باتاً اختراع روابط وهمية."""

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # عرض الرسائل السابقة للمستخدم
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # خانة رفع صور النقوش والآثار
    uploaded_image = st.file_uploader("قم برفع صورة النقش التاريخي لتحليله (اختياري):", type=["png", "jpg", "jpeg"])

    # خانة إدخال النص والأسئلة الخاصة بالمستخدم
    if user_prompt := st.chat_input("اكتب استفسارك أو انسخ حروف النقش هنا..."):
        with st.chat_message("user"):
            st.markdown(user_prompt)
        
        # تجهيز محتوى الرسالة المتوافق مع معيار الرؤية للنماذج المختلفة
        message_content = [{"type": "text", "text": user_prompt}]
        
        if uploaded_image:
            base64_image = encode_image(uploaded_image)
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
            })
            
        st.session_state.messages.append({"role": "user", "content": user_prompt})

        # إرسال الرسالة إلى الـ API وعرض الاستجابة الفورية
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            with st.spinner("جاري الاتصال بالنموذج والتحليل الأكاديمي الشامل..."):
                try:
                    api_messages = [{"role": "system", "content": system_prompt}]
                    for m in st.session_state.messages:
                        api_messages.append({"role": m["role"], "content": m["content"]})
                    
                    if uploaded_image and api_messages[-1]["role"] == "user":
                        api_messages[-1]["content"] = message_content

                    completion = client.chat.completions.create(
                        model=user_model,
                        messages=api_messages
                    )
                    output_text = completion.choices.message.content
                    response_placeholder.markdown(output_text)
                    st.session_state.messages.append({"role": "assistant", "content": output_text})
                except Exception as e:
                    st.error(f"حدث خطأ أثناء الاتصال بالـ API: {e}\nتأكد من صحة الرابط (Base URL)، المفتاح، واسم الموديل المختار.")
