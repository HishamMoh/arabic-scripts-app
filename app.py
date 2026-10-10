import streamlit as st
import openai
import base64

# إعداد واجهة المستخدم لتطبيق الشات العالمي المفتوح
st.set_page_config(page_title="محلل النقوش العربية القديمة العالمي", page_icon="📜", layout="centered")
st.title("📜 مساعد وباحث النقوش والخطوط العربية القديمة العالمي")
st.write("مرحباً بك! تطبيق ويب مفتوح يدعم جميع المنصات والنماذج المجانية والمدفوعة لتحليل وقراءة نقوش خط المسند بمنهجية أكاديمية.")

# القائمة الجانبية المرنة لاستيعاب أي منصة ذكاء اصطناعي في العالم
st.sidebar.title("🔑 إعدادات منصة الـ AI")

# خيار مخصص لـ OpenRouter لسهولة الاستخدام المجاني، وخيار يدوي مفتوح لأي منصة أخرى
provider_type = st.sidebar.selectbox("اختر طريقة الربط:", ["منصة OpenRouter (توفر نماذج مجانية)", "إدخال منصة أخرى يدوياً (Custom API)"])

if provider_type == "منصة OpenRouter (توفر نماذج مجانية)":
    base_url = "https://openrouter.ai"
    default_model = "google/gemini-2.5-flash:free"  # نموذج مجاني وقوي جداً متوفر على المنصة
else:
    base_url = st.sidebar.text_input("أدخل رابط المنصة (Base URL):", value="https://openai.com")
    default_model = st.sidebar.text_input("اسم النموذج (Model Name):", value="gpt-4o")

if provider_type == "منصة OpenRouter (توفر نماذج مجانية)":
    user_model = st.sidebar.text_input("اسم النموذج المستهدف:", value=default_model)
else:
    user_model = default_model

user_api_key = st.sidebar.text_input("أدخل مفتاح الـ API الخاص بك:", type="password")

# دالة لتحويل الصور المرفوعة إلى صيغة Base64 المفهومة لجميع الـ APIs
def encode_image(uploaded_file):
    return base64.b64encode(uploaded_file.read()).decode('utf-8')

if not user_api_key:
    st.info("من فضلك، أكمل إعدادات المنصة وأدخل مفتاح الـ API الخاص بك في القائمة الجانبية لتشغيل التطبيق.", icon="🔑")
else:
    # تهيئة اتصال العميل الموحد المفتوح لأي سيرفر في العالم
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

    # خانة رفع صور النقوش والآثار (تم إصلاح المكون البرمجي ليعمل بشكل صحيح كصندوق رفع ملفات)
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
