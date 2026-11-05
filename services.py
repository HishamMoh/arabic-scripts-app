"""Network services that do not access Streamlit session state."""

import base64

import requests

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


# https://docs.python.org/3/library/base64.html#base64.b64encode
def encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


# https://ai.google.dev/gemini-api/docs/api-key
# https://ai.google.dev/api/generate-content
def gemini_generate(
    api_key: str,
    model: str,
    prompt: str,
    image: dict | None = None,
    temperature: float = 0.15,
    max_tokens: int = 8192,
) -> str:
    """استدعاء Gemini بمفتاح المستخدم المجاني من Google AI Studio."""
    if not api_key:
        raise ValueError(
            "لا يوجد مفتاح Gemini. أضف مفتاحك المجاني من Google AI Studio أولاً."
        )
    parts: list = [{"text": prompt}]
    if image and image.get("bytes"):
        parts.append(
            {
                "inline_data": {
                    "mime_type": image.get("mime", "image/jpeg"),
                    "data": encode_b64(image["bytes"]),
                }
            }
        )
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    resp = requests.post(
        GEMINI_URL.format(model=model),
        json=payload,
        timeout=240,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    if not resp.ok:
        # Do not expose provider bodies or request URLs, which can contain secrets.
        raise RuntimeError(f"تعذّر الاتصال بخدمة Gemini (HTTP {resp.status_code}).")
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        fb = data.get("promptFeedback", {})
        raise RuntimeError(f"لم يُرجِع النموذج أي نص. ({fb})")
    out = []
    for part in candidates[0].get("content", {}).get("parts", []):
        if "text" in part:
            out.append(part["text"])
    text = "".join(out).strip()
    if not text:
        raise RuntimeError("استجابة فارغة من النموذج.")
    return text


# https://github.com/openai/openai-python#usage
def openai_chat(
    provider: dict, api_key: str, model: str, messages: list, image: dict | None = None
) -> str:
    """استدعاء أي مزود متوافق مع OpenAI (SiliconFlow / OpenRouter / غيرهم)."""
    if openai is None:
        raise RuntimeError("حزمة openai غير مثبتة: نفّذ pip install openai")
    if not api_key:
        raise ValueError(
            "لا يوجد مفتاح API لهذا المزود. أضفه من لوحة الإعدادات (يبقى في جلستك فقط)."
        )
    base = (provider.get("url") or "").rstrip("/")
    payload = [dict(m) for m in messages]
    if image and image.get("bytes") and payload and payload[-1]["role"] == "user":
        last_text = (
            payload[-1]["content"] if isinstance(payload[-1]["content"], str) else ""
        )
        payload[-1]["content"] = [
            {"type": "text", "text": last_text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image.get('mime','image/jpeg')};base64,{encode_b64(image['bytes'])}"
                },
            },
        ]
    with openai.OpenAI(api_key=api_key, base_url=base, timeout=180.0) as client:
        completion = client.chat.completions.create(model=model, messages=payload)
    if not completion.choices:
        raise RuntimeError("لم يُرجع المزود أي استجابة.")
    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("استجابة فارغة من المزود.")
    return text


# https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts
def check_catalogs(catalogs: list[tuple[str, str]]) -> dict[str, bool]:
    results = {}
    for name, url in catalogs:
        try:
            response = requests.get(url, timeout=(4, 4), allow_redirects=True)
            results[name] = 200 <= response.status_code < 400
        except requests.RequestException:
            results[name] = False
    return results


# https://github.com/openai/openai-python#usage
def fetch_provider_models(api_key: str, url: str) -> dict:
    if openai is None:
        raise RuntimeError("حزمة openai غير مثبتة.")
    with openai.OpenAI(
        api_key=api_key, base_url=url.rstrip("/"), timeout=40.0
    ) as client:
        return {
            model.id: {"alias": model.id, "type": "دردشة"}
            for model in client.models.list()
        }
