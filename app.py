# -*- coding: utf-8 -*-
"""
المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة
Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics
الإصدار 2.0 — واجهة احترافية + خصوصية كاملة لكل مستخدم + بحث عن النقش بمفتاح Gemini المجاني.
"""

import base64
import io
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

try:
    import openai
except Exception:  # pragma: no cover
    openai = None

# =====================================================================================
# 1) إعداد الصفحة والهوية البصرية
# =====================================================================================
APP_TITLE = "المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة"
APP_SUBTITLE = "Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics"

DB_PATH = "musnad_lab_v2.db"
LEGACY_DB_PATH = "chats_archive.db"
SHARED_OWNER = "__shared_index__"

st.set_page_config(
    page_title="مختبر المسند الرقمي",
    page_icon="🗿",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Kufi+Arabic:wght@400;600;700&display=swap');

:root{
  --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
  --brand:#7c3aed; --brand2:#0ea5e9; --gold:#b45309;
  --card:#ffffff; --soft:#f8fafc;
}

html, body, [class*="css"] { font-family: 'Noto Kufi Arabic', 'Segoe UI', Tahoma, sans-serif; }
.stApp { background: linear-gradient(180deg,#f6f8fc 0%, #eef2f9 100%); }

.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1250px; }

/* ---------- الترويسة ---------- */
.hero {
  position: relative; overflow: hidden;
  border-radius: 22px; padding: 26px 28px; margin-bottom: 18px;
  background: radial-gradient(1200px 300px at 90% -20%, #a78bfa33, transparent),
              linear-gradient(135deg,#1e1b4b 0%, #312e81 45%, #1e3a8a 100%);
  color:#fff; border:1px solid #312e8133;
  box-shadow: 0 18px 40px -24px #1e1b4b80;
}
.hero h1 { font-size: 1.30rem; line-height:1.75; margin:0 0 6px 0; font-weight:700; }
.hero p  { margin:0; color:#c7d2fe; font-size:.82rem; letter-spacing:.3px; }
.hero .chips { margin-top:14px; display:flex; gap:8px; flex-wrap:wrap; }
.chip {
  background:#ffffff1f; border:1px solid #ffffff33; color:#e0e7ff;
  padding:5px 12px; border-radius:999px; font-size:.72rem; backdrop-filter: blur(4px);
}

/* ---------- البطاقات ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 18px !important;
  border: 1px solid var(--line) !important;
  background: #fff !important;
  box-shadow: 0 10px 26px -20px #0f172a80;
}
.sec-title { font-size:1rem; font-weight:700; color:#1e293b; margin:0 0 4px 0; }
.sec-sub   { font-size:.75rem; color:#64748b; margin:0 0 10px 0; }
.kv { font-size:.75rem; color:#475569; }
.kv b { color:#0f172a; }

/* ---------- الشرائح والوسوم ---------- */
.pill {
  display:inline-block; padding:3px 10px; border-radius:999px;
  font-size:.70rem; font-weight:600; border:1px solid;
}
.pill-ok   { color:#047857; background:#ecfdf5; border-color:#a7f3d0; }
.pill-warn { color:#b45309; background:#fffbeb; border-color:#fde68a; }
.pill-info { color:#1d4ed8; background:#eff6ff; border-color:#bfdbfe; }
.pill-off  { color:#475569; background:#f1f5f9; border-color:#e2e8f0; }

/* ---------- الأزرار ---------- */
.stButton>button, .stDownloadButton>button { border-radius: 12px !important; font-weight:600; }
.stButton>button[kind="primary"] {
  background: linear-gradient(135deg,#7c3aed,#2563eb) !important;
  border: none !important; color:#fff !important;
  box-shadow: 0 10px 22px -14px #4338ca;
}

/* ---------- الدردشة ---------- */
div[data-testid="stChatMessage"] {
  border-radius: 16px; border:1px solid var(--line); background:#fff;
  box-shadow: 0 8px 20px -18px #0f172a99;
}

/* ---------- الشريط الجانبي ---------- */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg,#0f172a 0%, #1e1b4b 100%);
  border-left: 1px solid #1e293b;
}
section[data-testid="stSidebar"] * { color:#e2e8f0 !important; }
section[data-testid="stSidebar"] .stButton>button {
  background:#ffffff10 !important; border:1px solid #ffffff1f !important;
  color:#e2e8f0 !important; text-align:right; justify-content:flex-start;
}
section[data-testid="stSidebar"] .stButton>button:hover { background:#ffffff22 !important; }
section[data-testid="stSidebar"] .stButton>button[kind="primary"] {
  background: linear-gradient(135deg,#7c3aed,#2563eb) !important; border:none !important;
}
section[data-testid="stSidebar"] input { background:#ffffff10 !important; }
section[data-testid="stSidebar"] .brand {
  display:flex; align-items:center; gap:10px; padding:10px 4px 14px 4px;
  border-bottom:1px solid #ffffff1f; margin-bottom:14px;
}
section[data-testid="stSidebar"] .brand .mark {
  width:38px; height:38px; border-radius:12px; display:grid; place-items:center;
  background:linear-gradient(135deg,#7c3aed,#0ea5e9); font-size:1.1rem;
}
section[data-testid="stSidebar"] .brand .t1 { font-weight:700; font-size:.86rem; }
section[data-testid="stSidebar"] .brand .t2 { font-size:.66rem; color:#94a3b8 !important; }
section[data-testid="stSidebar"] .side-label {
  font-size:.70rem; color:#94a3b8 !important; margin:14px 2px 6px 2px; letter-spacing:.6px;
}
section[data-testid="stSidebar"] .privacy-box {
  background:#ffffff0d; border:1px solid #ffffff1f; border-radius:14px;
  padding:10px 12px; font-size:.70rem; color:#cbd5e1 !important; line-height:1.9;
}

/* ---------- اتجاه من اليمين إلى اليسار ---------- */
.block-container, section[data-testid="stSidebar"] { direction: rtl; }
.block-container [data-testid="stMarkdownContainer"], .block-container p,
.block-container li, .block-container h1, .block-container h2,
.block-container h3, .block-container h4 { text-align: right; }
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea { text-align: right; direction: rtl; }
[data-testid="stChatInput"] textarea { text-align: right; direction: rtl; }
[data-testid="stFileUploaderDropzone"] { direction: rtl; }
code, pre { direction: ltr; text-align: left; unicode-bidi: embed; }

/* ---------- إخفاء الزخارف الافتراضية ---------- */
#MainMenu, footer, div[data-testid="stDecoration"] { visibility:hidden; }
[data-testid="stStatusWidget"] { visibility:hidden; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# =====================================================================================
# 2) أدوات مساعدة عامة
# =====================================================================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def normalize_ar(text: str) -> str:
    """تطبيع عربي/لاتيني مبسّط لأغراض البحث المحلي دون مفتاح."""
    if not text:
        return ""
    t = str(text).lower()
    t = re.sub(r"[\u064B-\u0652\u0670\u06D6-\u06ED]", "", t)  # تشكيل
    t = t.replace("ـ", "")
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"), ("ى", "ي"), ("ئ", "ي"), ("ؤ", "و"), ("ة", "ه")):
        t = t.replace(a, b)
    t = re.sub(r"[^\w\u0600-\u06FF<>/\[\]\- ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def bytes_to_kb(n: int) -> str:
    return f"{n/1024:.0f} KB"


def fmt_dt(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%Y/%m/%d · %H:%M")
    except Exception:
        return value or "—"


def goto(view_key: str) -> None:
    """تبديل العرض مع مزامنة شريط التنقل (بدون أي معاملات في الرابط)."""
    st.session_state.view = view_key
    st.session_state.pop("nav_segmented", None)
    st.rerun()


# =====================================================================================
# 3) قاعدة البيانات — كل صف مرتبط بمالك (user_token) + لا تُخزَّن أي مفاتيح API
# =====================================================================================
def db_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db() -> None:
    conn = db_conn()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS chats_v2 (
               chat_id TEXT PRIMARY KEY,
               owner   TEXT NOT NULL,
               title   TEXT,
               messages TEXT,
               created_at TEXT,
               updated_at TEXT
           )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS providers_v2 (
               owner TEXT NOT NULL,
               name TEXT NOT NULL,
               api_style TEXT,
               url TEXT,
               path TEXT,
               network_opt INTEGER,
               models TEXT,
               PRIMARY KEY (owner, name)
           )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS corpus_v2 (
               entry_id TEXT PRIMARY KEY,
               owner TEXT NOT NULL,
               code TEXT,
               corpus TEXT,
               script TEXT,
               region TEXT,
               century TEXT,
               text TEXT,
               note TEXT,
               created_at TEXT
           )"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_chats_owner ON chats_v2(owner)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_corpus_owner ON corpus_v2(owner)")
    conn.commit()
    conn.close()
    purge_legacy_secrets()
    seed_reference_index()


def purge_legacy_secrets() -> None:
    """حذف أي مفاتيح API قديمة كانت محفوظة في قاعدة البيانات المشتركة (الإصدار السابق)."""
    try:
        if not os.path.exists(LEGACY_DB_PATH):
            return
        conn = sqlite3.connect(LEGACY_DB_PATH, check_same_thread=False)
        c = conn.cursor()
        cols = [r[1] for r in c.execute("PRAGMA table_info(providers)").fetchall()]
        if "api_key" in cols:
            c.execute("UPDATE providers SET api_key = ''")
            conn.commit()
        conn.close()
    except Exception:
        pass


# ---------- المحادثات ----------
def load_chats(owner: str) -> dict:
    conn = db_conn()
    rows = conn.execute(
        "SELECT chat_id, title, messages, created_at, updated_at FROM chats_v2 "
        "WHERE owner = ? ORDER BY updated_at DESC, created_at DESC",
        (owner,),
    ).fetchall()
    conn.close()
    out: dict = {}
    for chat_id, title, msgs, created, updated in rows:
        try:
            out[chat_id] = {
                "title": title or "بدون عنوان",
                "messages": json.loads(msgs or "[]"),
                "created_at": created or "",
                "updated_at": updated or created or "",
            }
        except Exception:
            pass
    return out


def save_chat(owner: str, chat_id: str, title: str, messages: list) -> None:
    conn = db_conn()
    row = conn.execute(
        "SELECT created_at FROM chats_v2 WHERE chat_id = ? AND owner = ?", (chat_id, owner)
    ).fetchone()
    created = (row[0] if row and row[0] else now_str())
    conn.execute(
        "INSERT OR REPLACE INTO chats_v2 (chat_id, owner, title, messages, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, owner, title, json.dumps(messages, ensure_ascii=False), created, now_str()),
    )
    conn.commit()
    conn.close()


def delete_chat(owner: str, chat_id: str) -> None:
    conn = db_conn()
    conn.execute("DELETE FROM chats_v2 WHERE chat_id = ? AND owner = ?", (chat_id, owner))
    conn.commit()
    conn.close()


def delete_all_user_data(owner: str) -> None:
    conn = db_conn()
    for table in ("chats_v2", "providers_v2", "corpus_v2"):
        conn.execute(f"DELETE FROM {table} WHERE owner = ?", (owner,))
    conn.commit()
    conn.close()


# ---------- المزودون (بدون مفاتيح) ----------
DEFAULT_PROVIDERS = {
    "Google Gemini (مجاني)": {
        "api_style": "Google Gemini API",
        "url": "https://generativelanguage.googleapis.com/v1beta",
        "path": "",
        "network_opt": True,
        "models": {
            "gemini-2.5-flash": {
                "alias": "Gemini 2.5 Flash (مجاني)", "type": "دردشة",
                "vision": True, "tools": True, "reasoning": False,
                "context": 1000000, "max_tokens": 8192,
            },
            "gemini-2.5-flash-lite": {
                "alias": "Gemini 2.5 Flash Lite (مجاني)", "type": "دردشة",
                "vision": True, "tools": True, "reasoning": False,
                "context": 1000000, "max_tokens": 8192,
            },
        },
    },
    "OpenRouter": {
        "api_style": "OpenAI API",
        "url": "https://openrouter.ai/api/v1",
        "path": "/chat/completions",
        "network_opt": True,
        "models": {
            "google/gemini-2.5-flash:free": {
                "alias": "Gemini 2.5 Flash المجاني (OpenRouter)", "type": "دردشة",
                "vision": True, "tools": True, "reasoning": False,
                "context": 1000000, "max_tokens": 8192,
            }
        },
    },
    "SiliconFlow": {
        "api_style": "OpenAI API",
        "url": "https://api.siliconflow.com/v1",
        "path": "/chat/completions",
        "network_opt": True,
        "models": {
            "Qwen/Qwen2.5-7B-Instruct": {
                "alias": "Qwen 2.5 7B Instruct", "type": "دردشة",
                "vision": False, "tools": True, "reasoning": False,
                "context": 32768, "max_tokens": 4096,
            },
            "deepseek-ai/DeepSeek-V3": {
                "alias": "DeepSeek V3", "type": "دردشة",
                "vision": False, "tools": True, "reasoning": False,
                "context": 64000, "max_tokens": 4096,
            },
        },
    },
}


def load_providers(owner: str) -> dict:
    conn = db_conn()
    rows = conn.execute(
        "SELECT name, api_style, url, path, network_opt, models FROM providers_v2 WHERE owner = ?",
        (owner,),
    ).fetchall()
    conn.close()

    if not rows:
        for name, data in DEFAULT_PROVIDERS.items():
            save_provider(owner, name, data)
        return json.loads(json.dumps(DEFAULT_PROVIDERS))

    out = {}
    for name, style, url, path, net, models_json in rows:
        try:
            models = json.loads(models_json) if isinstance(models_json, str) else (models_json or {})
            if not isinstance(models, dict):
                models = {}
        except Exception:
            models = {}
        out[name] = {
            "api_style": style or "OpenAI API",
            "url": url or "",
            "path": path or "",
            "network_opt": bool(net),
            "models": models,
        }
    return out


def save_provider(owner: str, name: str, data: dict) -> None:
    models = data.get("models", {})
    models_str = models if isinstance(models, str) else json.dumps(models, ensure_ascii=False)
    conn = db_conn()
    conn.execute(
        "INSERT OR REPLACE INTO providers_v2 (owner, name, api_style, url, path, network_opt, models) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            owner, name, data.get("api_style", "OpenAI API"),
            data.get("url", ""), data.get("path", ""),
            1 if data.get("network_opt", True) else 0, models_str,
        ),
    )
    conn.commit()
    conn.close()


def delete_provider(owner: str, name: str) -> None:
    conn = db_conn()
    conn.execute("DELETE FROM providers_v2 WHERE owner = ? AND name = ?", (owner, name))
    conn.commit()
    conn.close()


# ---------- الفهرس المرجعي للنقوش (بحث بدون مفتاح) ----------
REFERENCE_SEED = [
    ("CIH 352", "CIH — Corpus Inscriptionum Semiticarum IV", "مسند", "—", "—",
     "", "رأس مدخل فهرسي للاستدلال السريع؛ تُستكمل التفاصيل العلمية بعد التحقق من DASI/CSAI."),
    ("RES 3945", "RES — Répertoire d'Épigraphie Sémitique", "مسند", "—", "—",
     "", "رأس مدخل فهرسي؛ النقش من أشهر النقوش السبئية المدروسة — يُستكمل النقل الحرفي بعد التحقق."),
    ("CIH 6", "CIH — Corpus Inscriptionum Semiticarum IV", "مسند", "—", "—",
     "", "رأس مدخل فهرسي."),
    ("Ja 576", "Ja — Jamme, Sabaean Inscriptions", "مسند", "—", "—",
     "", "رأس مدخل فهرسي."),
    ("CSAI I", "CSAI — Corpus of South Arabian Inscriptions", "مسند", "—", "—",
     "", "سلسلة مدونات النقوش العربية الجنوبية؛ تُفهرس تحتها رموز عديدة."),
    ("Ry / Ir / Gl", "مجموعات Ryckmans / al-Iryani / Glaser", "مسند", "—", "—",
     "", "رموز مرجعية لمجموعات نقوش؛ يُضاف الرمز الدقيق عند التحقق."),
]

SEED_COLUMNS = ["entry_id", "code", "corpus", "script", "region", "century", "text", "note"]


def seed_reference_index() -> None:
    conn = db_conn()
    exists = conn.execute(
        "SELECT COUNT(*) FROM corpus_v2 WHERE owner = ?", (SHARED_OWNER,)
    ).fetchone()[0]
    if not exists:
        for idx, row in enumerate(REFERENCE_SEED):
            code, corpus, script, region, century, text, note = row
            conn.execute(
                "INSERT OR IGNORE INTO corpus_v2 (entry_id, owner, code, corpus, script, region, century, text, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"seed_{idx}", SHARED_OWNER, code, corpus, script, region, century, text, note, now_str()),
            )
    conn.commit()
    conn.close()


def load_corpus(owner: str) -> list:
    conn = db_conn()
    rows = conn.execute(
        "SELECT entry_id, owner, code, corpus, script, region, century, text, note FROM corpus_v2 "
        "WHERE owner IN (?, ?) ORDER BY owner, code",
        (owner, SHARED_OWNER),
    ).fetchall()
    conn.close()
    keys = ["entry_id", "owner", "code", "corpus", "script", "region", "century", "text", "note"]
    return [dict(zip(keys, r)) for r in rows]


def _cell(value) -> str:
    """تحويل آمن لخلية من data_editor إلى نص (يتعامل مع NaN/None)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def upsert_corpus_rows(owner: str, df: pd.DataFrame) -> int:
    conn = db_conn()
    count = 0
    for _, row in df.iterrows():
        code = _cell(row.get("code"))
        if not code:
            continue
        entry_id = _cell(row.get("entry_id"))
        if not entry_id or entry_id.startswith("seed_") or entry_id.lower() in ("nan", "none"):
            entry_id = new_id()
        conn.execute(
            "INSERT OR REPLACE INTO corpus_v2 (entry_id, owner, code, corpus, script, region, century, text, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry_id, owner, code,
                _cell(row.get("corpus")), _cell(row.get("script")),
                _cell(row.get("region")), _cell(row.get("century")),
                _cell(row.get("text")), _cell(row.get("note")), now_str(),
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def delete_corpus_entry(owner: str, entry_id: str) -> None:
    conn = db_conn()
    conn.execute("DELETE FROM corpus_v2 WHERE entry_id = ? AND owner = ?", (entry_id, owner))
    conn.commit()
    conn.close()


# =====================================================================================
# 4) حالة الجلسة: هوية مؤقتة لكل مستخدم + مفاتيح لا تُحفظ ولا تُنقل عبر الرابط
# =====================================================================================
def strip_sensitive_query_params() -> None:
    """منع أي انتقال لبيانات حساسة عبر رابط الصفحة (?key=... / ?chat_id=...)."""
    try:
        qp = st.query_params
        removed = [k for k in list(qp.keys()) if normalize_ar(k) in {
            "key", "api_key", "apikey", "token", "chat", "chat_id", "provider", "model", "session", "user"
        }]
        for k in removed:
            del qp[k]
    except Exception:
        pass


strip_sensitive_query_params()

if "user_token" not in st.session_state:
    # هوية عشوائية لجلسة المتصفح الحالية فقط: لا تُحفظ في الرابط ولا تُشارك مع مستخدم آخر.
    st.session_state.user_token = uuid.uuid4().hex
OWNER = st.session_state.user_token

if "secret_keys" not in st.session_state:
    st.session_state.secret_keys = {}          # {provider_name: key} — ذاكرة الجلسة فقط
if "gemini_free_key" not in st.session_state:
    st.session_state.gemini_free_key = ""      # ذاكرة الجلسة فقط
if "pending_image" not in st.session_state:
    st.session_state.pending_image = None
if "search_result" not in st.session_state:
    st.session_state.search_result = None
if "view" not in st.session_state:
    st.session_state.view = "search"
if "confirm_wipe" not in st.session_state:
    st.session_state.confirm_wipe = False

init_db()

if "providers" not in st.session_state:
    st.session_state.providers = load_providers(OWNER)
if "archive" not in st.session_state:
    st.session_state.archive = load_chats(OWNER)

ARCHIVE: dict = st.session_state.archive
if not ARCHIVE:
    first_id = new_id()
    ARCHIVE[first_id] = {
        "title": "محادثة جديدة", "messages": [],
        "created_at": now_str(), "updated_at": now_str(),
    }
    save_chat(OWNER, first_id, "محادثة جديدة", [])
    st.session_state.archive = ARCHIVE

if "current_chat_id" not in st.session_state or st.session_state.current_chat_id not in ARCHIVE:
    st.session_state.current_chat_id = list(ARCHIVE.keys())[0]
CURRENT_CHAT = st.session_state.current_chat_id
MESSAGES: list = ARCHIVE[CURRENT_CHAT]["messages"]
PROVIDERS: dict = st.session_state.providers


# =====================================================================================
# 5) محرّكا الاستدعاء: OpenAI-متوافق + Google Gemini REST (مجاني)
# =====================================================================================
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_generate(api_key: str, model: str, prompt: str, image: dict | None = None,
                    temperature: float = 0.15, max_tokens: int = 8192) -> str:
    """استدعاء Gemini بمفتاح المستخدم المجاني من Google AI Studio (لا يحتاج أي مزود آخر)."""
    if not api_key:
        raise ValueError("لا يوجد مفتاح Gemini. أضف مفتاحك المجاني من Google AI Studio أولاً.")
    parts: list = [{"text": prompt}]
    if image and image.get("bytes"):
        parts.append({
            "inline_data": {
                "mime_type": image.get("mime", "image/jpeg"),
                "data": encode_b64(image["bytes"]),
            }
        })
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    resp = requests.post(
        GEMINI_URL.format(model=model),
        params={"key": api_key},
        json=payload,
        timeout=240,
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code != 200:
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except Exception:
            detail = resp.text[:300]
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {detail}")
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


def openai_chat(provider: dict, api_key: str, model: str, messages: list,
                image: dict | None = None) -> str:
    """استدعاء أي مزود متوافق مع OpenAI (SiliconFlow / OpenRouter / غيرهم)."""
    if openai is None:
        raise RuntimeError("حزمة openai غير مثبتة: نفّذ pip install openai")
    if not api_key:
        raise ValueError("لا يوجد مفتاح API لهذا المزود. أضفه من لوحة الإعدادات (يبقى في جلستك فقط).")
    base = (provider.get("url") or "").rstrip("/")
    client = openai.OpenAI(api_key=api_key, base_url=base, timeout=180.0)
    payload = [dict(m) for m in messages]
    if image and image.get("bytes") and payload and payload[-1]["role"] == "user":
        last_text = payload[-1]["content"] if isinstance(payload[-1]["content"], str) else ""
        payload[-1]["content"] = [
            {"type": "text", "text": last_text},
            {"type": "image_url",
             "image_url": {"url": f"data:{image.get('mime','image/jpeg')};base64,{encode_b64(image['bytes'])}"}},
        ]
    completion = client.chat.completions.create(model=model, messages=payload)
    return (completion.choices[0].message.content or "").strip()


# =====================================================================================
# 6) المطالبات الأكاديمية
# =====================================================================================
SYSTEM_PROMPT_ANALYSIS = """[أنت خبير إبيغرافي وعالم آثار رقمي في "المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة" (Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics). مهمتك هي تحليل وتوثيق النقوش وفق أعلى وأحدث معايير التحقيق الأكاديمي الصارم المعتمَد في مدونات DASI و CSAI والدراسات السامية الدولية (مثل نموذج CIH 352)].

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
- إذا كان النص المرفوع غير مسندي أو غير واضح، صرّح بذلك بأمانة علمية مع تقديم البديل الأكاديمي المتاح."""

SYSTEM_PROMPT_LOOKUP = """[أنت مساعد بحث إبيغرافي في "المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة".
مهمتك هنا **البحث الاستدلالي عن النقش وتعريفه** لا إصدار الوثيقة الكاملة إلا إذا طُلب.

المطلوب منك إخراج "بطاقة تعريف بحثية" بهذا الترتيب:
### 1) هوية النقش المحتملة
- الرمز/الرموز المرشحة (CIH / RES / Ja / Ir / Ry / Gl / CSAI) مع بيان درجة الثقة لكل ترشيح (نسبة مئوية).
- مجموعة النقوش (Corpus) والمدونة المرجعية التي فُهرس فيها.
- الموقع الأثري الأرجح والقبيلة/المملكة (سبأ، معين، قتبان، حضرموت، حمير، أوسان).
- الحقبة التقديرية مع مرجعية التأريخ.

### 2) القراءة السريعة
- نقل حرفي عربي مختصر للأسطر (أو أهم المفردات إن كان النقش مبتوراً).
- Transliteration لاتيني بمعايير Beeston مع التمييز s1/s2/s3.

### 3) المطابقة المرجعية
- إن تعرّفت على نقش منشور: اذكر رمزه ومرجعه المنشور بدقة.
- إن لم تكن متأكداً: صرّح بذلك حرفياً بعبارة «لم أتحقق» ولا تخترع رموزاً أو مراجع.

### 4) خطة بحث مقترحة
- ثلاث خطوات تحقّق عملية (مدونات DASI/CSAI، المعاجم: Beeston 1982 / Biella 1982، دراسات مطابقة).

⚠️ قواعد صارمة: لا تُنشئ مراجع أو روابط وهمية. ميّز بوضوح بين المحقق والمرجّح. اكتب بالعربية الفصحى مع المصطلحات الإنجليزية بين قوسين."""


# =====================================================================================
# 7) التصدير
# =====================================================================================
def generate_docx(text: str) -> bytes:
    from docx import Document
    doc = Document()
    doc.add_heading(APP_TITLE, level=1)
    doc.add_paragraph(APP_SUBTITLE)
    for line in text.split("\n"):
        if line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        else:
            doc.add_paragraph(line)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


def generate_pdf(text: str) -> bytes | None:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception:
        return None
    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=letter)
    _, height = letter
    y = height - 45
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "South Arabian Epigraphy Laboratory")
    y -= 22
    c.setFont("Helvetica", 9)
    for line in text.split("\n"):
        if y < 45:
            c.showPage()
            y = height - 45
            c.setFont("Helvetica", 9)
        c.drawString(40, y, line[:100])
        y -= 13
    c.save()
    return bio.getvalue()


def download_row(text: str, key_suffix: str, base_name: str = "تقرير_إبيغرافي") -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "📄 Word (.docx)", data=generate_docx(text),
            file_name=f"{base_name}_{stamp}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch", key=f"docx_{key_suffix}",
        )
    with c2:
        st.download_button(
            "📝 Markdown (.md)", data=text.encode("utf-8"),
            file_name=f"{base_name}_{stamp}.md", mime="text/markdown",
            width="stretch", key=f"md_{key_suffix}",
        )
    with c3:
        pdf = generate_pdf(text)
        if pdf:
            st.download_button(
                "📑 PDF (.pdf)", data=pdf, file_name=f"{base_name}_{stamp}.pdf",
                mime="application/pdf", width="stretch", key=f"pdf_{key_suffix}",
            )
        else:
            st.caption("PDF غير متاح (reportlab غير مثبت).")


# =====================================================================================
# 8) نافذة رفع النقش (Dialog)
# =====================================================================================
def set_pending_image(data: bytes, name: str, mime: str) -> None:
    st.session_state.pending_image = {
        "bytes": data,
        "name": name or "inscription.jpg",
        "mime": mime or "image/jpeg",
        "size": len(data),
    }


@st.dialog("🖼️ نافذة رفع صورة النقش", width="large", icon="🖼️")
def upload_inscription_dialog() -> None:
    st.caption("ارفع صورة واضحة للنقش (مسند / حجر أثري) أو التقطها بالكاميرا. تبقى الصورة داخل جلسة هذا المستخدم فقط ولا تُرفع إلى أي خادم إلا عند إرسالها للنموذج.")
    tab_file, tab_cam = st.tabs(["📁 رفع ملف", "📷 التقاط بالكاميرا"])
    with tab_file:
        up = st.file_uploader("صورة النقش", type=["png", "jpg", "jpeg", "webp"], key="dlg_file_upload")
    with tab_cam:
        cam = st.camera_input("التقاط صورة النقش", key="dlg_camera")

    source = cam or up
    if source is not None:
        data = source.getvalue() if hasattr(source, "getvalue") else source.read()
        name = getattr(source, "name", "camera.jpg") or "camera.jpg"
        mime = getattr(source, "type", None) or "image/jpeg"
        st.image(data, caption=f"{name} · {bytes_to_kb(len(data))}", width="stretch")
        if st.button("✅ تثبيت الصورة على الجلسة", type="primary", width="stretch"):
            set_pending_image(data, name, mime)
            st.rerun()
    else:
        st.info("لم تُختر صورة بعد — اختر ملفاً أو التقط صورة.", icon="ℹ️")

    if st.session_state.pending_image:
        st.divider()
        st.image(st.session_state.pending_image["bytes"],
                 caption=f"الصورة المثبتة حالياً: {st.session_state.pending_image['name']}", width=260)
        if st.button("🗑️ إزالة الصورة المثبتة", width="stretch"):
            st.session_state.pending_image = None
            st.rerun()


def upload_icon_button(key: str, label: str = "رفع نقش") -> None:
    """زر أيقوني يفتح نافذة الرفع."""
    if st.button(f"🖼️ {label}", key=key, help="فتح نافذة رفع صورة النقش"):
        upload_inscription_dialog()


def attachment_status() -> None:
    img = st.session_state.pending_image
    if img:
        c1, c2 = st.columns([1, 3], vertical_alignment="center")
        with c1:
            st.image(img["bytes"], width=96)
        with c2:
            st.markdown(
                f"<div class='kv'><span class='pill pill-ok'>مرفق</span> "
                f"<b>{img['name']}</b><br>{bytes_to_kb(img['size'])} · سيُرسل مع الطلب التالي</div>",
                unsafe_allow_html=True,
            )
            if st.button("إزالة المرفق ✕", key="rm_pending_img"):
                st.session_state.pending_image = None
                st.rerun()
    else:
        st.markdown(
            "<div class='kv'><span class='pill pill-off'>لا يوجد مرفق</span> "
            "استخدم أيقونة الرفع 🖼️ لإضافة صورة النقش.</div>",
            unsafe_allow_html=True,
        )


# =====================================================================================
# 9) الشريط الجانبي
# =====================================================================================
with st.sidebar:
    st.markdown(
        f"""<div class="brand">
              <div class="mark">🗿</div>
              <div>
                <div class="t1">مختبر المسند الرقمي</div>
                <div class="t2">South Arabian Epigraphy Lab · v2.0</div>
              </div>
            </div>""",
        unsafe_allow_html=True,
    )

    if st.button("➕ محادثة جديدة", type="primary", width="stretch"):
        nid = new_id()
        title = f"محادثة {datetime.now().strftime('%H:%M')}"
        st.session_state.archive[nid] = {
            "title": title, "messages": [], "created_at": now_str(), "updated_at": now_str()
        }
        save_chat(OWNER, nid, title, [])
        st.session_state.current_chat_id = nid
        goto("chat")

    upload_icon_button("sb_upload_btn", "رفع نقش")

    st.markdown("<div class='side-label'>🕒 أرشيفي (خاص بي)</div>", unsafe_allow_html=True)
    chat_query = st.text_input("بحث في المحادثات", placeholder="🔎 فلترة العناوين…",
                               label_visibility="collapsed", key="sb_chat_filter").strip()

    shown = 0
    for cid, cdata in list(st.session_state.archive.items()):
        title = cdata["title"]
        if chat_query and normalize_ar(chat_query) not in normalize_ar(title):
            continue
        if shown >= 25:
            break
        shown += 1
        active = (cid == CURRENT_CHAT)
        label = f"{'▸' if active else '💬'} {title[:32]}"
        if st.button(label, key=f"sb_chat_{cid}",
                     type="primary" if active else "secondary", width="stretch"):
            st.session_state.current_chat_id = cid
            goto("chat")

    if shown == 0:
        st.caption("لا توجد نتائج مطابقة.")

    st.markdown("<div class='side-label'>🔒 الخصوصية</div>", unsafe_allow_html=True)
    st.markdown(
        """<div class="privacy-box">
             جلسة معزولة تماماً: مفاتيح API وسجل المحادثات والصورة المرفقة
             مرتبطة بهذا المتصفح/الجلسة فقط، ولا تُكتب في الرابط ولا تظهر لمستخدم آخر.
             تُمسح المفاتيح تلقائياً عند إغلاق التبويب.
           </div>""",
        unsafe_allow_html=True,
    )
    with st.expander("كيف تُحمى بياناتي؟"):
        st.markdown(
            "- هوية عشوائية مؤقتة لكل جلسة متصفح (لا تسجيل دخول، لا Cookie تتبّع).\n"
            "- مفاتيح API في `session_state` فقط — **لا** في قاعدة البيانات و**لا** في الرابط.\n"
            "- المحادثات تُخزَّن موسومة بهويتك المؤقتة؛ لا يستطيع غيرك قراءتها.\n"
            "- أي معامل حساس في الرابط (`?key=`، `?chat_id=`) يُحذف تلقائياً عند التحميل.\n"
            "- زر الحذف النهائي أدناه يمحو كل صفوفك من قاعدة البيانات."
        )

    if st.button("🗑️ حذف بياناتي نهائياً", key="sb_wipe"):
        st.session_state.confirm_wipe = True
    if st.session_state.confirm_wipe:
        st.warning("سيتم حذف محادثاتك وفهرسك وإعدادات مزوديك (المفاتيح تُحذف تلقائياً). لا يمكن التراجع.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("نعم، احذف", type="primary", key="sb_wipe_yes"):
                delete_all_user_data(OWNER)
                for k in ("archive", "current_chat_id", "providers", "search_result"):
                    st.session_state.pop(k, None)
                st.session_state.secret_keys = {}
                st.session_state.gemini_free_key = ""
                st.session_state.pending_image = None
                st.session_state.confirm_wipe = False
                st.rerun()
        with cc2:
            if st.button("إلغاء", key="sb_wipe_no"):
                st.session_state.confirm_wipe = False
                st.rerun()


# =====================================================================================
# 10) الترويسة + التنقل
# =====================================================================================
head_left, head_right = st.columns([3.2, 1], vertical_alignment="center")
with head_left:
    st.markdown(
        f"""<div class="hero">
              <h1>{APP_TITLE}</h1>
              <p>{APP_SUBTITLE}</p>
              <div class="chips">
                <span class="chip">🔎 بحث بدون مفتاح</span>
                <span class="chip">✨ Gemini المجاني</span>
                <span class="chip">🔒 جلسة خاصة</span>
                <span class="chip">📜 DASI / CSAI</span>
              </div>
            </div>""",
        unsafe_allow_html=True,
    )
with head_right:
    upload_icon_button("head_upload_btn", "رفع النقش")
    key_state = "✅ مفتاح Gemini جاهز" if st.session_state.gemini_free_key else "🔑 لا مفتاح Gemini"
    prov_key_state = "مفتاح مزود رئيسي مضبوط" if any(st.session_state.secret_keys.values()) else "بلا مفتاح مزود"
    st.markdown(
        f"<div style='text-align:center;margin-top:6px'>"
        f"<span class='pill {'pill-ok' if st.session_state.gemini_free_key else 'pill-warn'}'>"
        f"{key_state}</span><br><br>"
        f"<span class='pill pill-info'>{prov_key_state}</span></div>",
        unsafe_allow_html=True,
    )

VIEWS = {
    "🔎 البحث عن النقش": "search",
    "💬 المساعد الإبيغرافي": "chat",
    "📚 الأرشيف": "archive",
    "⚙️ الإعدادات": "settings",
}
VIEW_KEYS = list(VIEWS.values())
VIEW_LABELS = list(VIEWS.keys())
if st.session_state.view not in VIEW_KEYS:
    st.session_state.view = "search"
current_label = VIEW_LABELS[VIEW_KEYS.index(st.session_state.view)]
if "nav_segmented" not in st.session_state:
    st.session_state.nav_segmented = current_label
choice = st.segmented_control(
    "التنقل", VIEW_LABELS, label_visibility="collapsed",
    key="nav_segmented", width="stretch",
)
if choice and VIEWS[choice] != st.session_state.view:
    goto(VIEWS[choice])
VIEW = st.session_state.view

st.write("")


# =====================================================================================
# 11) عرض البحث عن النقش (بدون مفتاح مزود + Gemini المجاني)
# =====================================================================================
def run_local_search(query: str, region_filter: str, corpus_filter: str) -> dict:
    q = normalize_ar(query)
    rows = load_corpus(OWNER)
    hits = []
    for r in rows:
        if r["owner"] == SHARED_OWNER:
            r = dict(r)
            r["scope"] = "فهرس مرجعي مدمج"
        else:
            r = dict(r)
            r["scope"] = "فهرس المستخدم"
        if corpus_filter != "الكل" and corpus_filter.lower() not in (r["corpus"] or "").lower():
            continue
        if region_filter.strip() and normalize_ar(region_filter) not in normalize_ar(r["region"] or ""):
            continue
        haystack = normalize_ar(" ".join([
            r.get("code", ""), r.get("corpus", ""), r.get("script", ""),
            r.get("region", ""), r.get("century", ""), r.get("text", ""), r.get("note", ""),
        ]))
        if q and q not in haystack:
            # مطابقة مرنة: كل كلمات الاستعلام موجودة
            if not all(tok in haystack for tok in q.split() if len(tok) > 1):
                continue
        hits.append(r)

    archive_hits = []
    if q:
        for cid, cdata in st.session_state.archive.items():
            blob = normalize_ar(cdata["title"] + " " + " ".join(
                m.get("content", "") for m in cdata["messages"]))
            if q in blob or all(tok in blob for tok in q.split() if len(tok) > 1):
                archive_hits.append({"chat_id": cid, "title": cdata["title"], "updated_at": cdata.get("updated_at", "")})
    return {"query": query, "corpus": hits, "archive": archive_hits}


def render_search_view() -> None:
    st.markdown("<div class='sec-title'>🔎 بوابة البحث عن النقش</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sec-sub'>محرّكان مستقلان: (١) بحث محلي فوري **بدون أي مفتاح** في فهرسك وأرشيفك، "
        "(٢) بحث استدلالي/تحليلي بمفتاح **Gemini المجاني** الخاص بحسابك (Google AI Studio) — لا يستهلك أي مفتاح مزود آخر.</div>",
        unsafe_allow_html=True,
    )

    col_q, col_side = st.columns([2.15, 1], gap="medium")

    with col_q:
        with st.container(border=True):
            engine = st.radio(
                "محرّك البحث",
                ["🔍 بحث محلي (بدون مفتاح)", "✨ بحث وتحليل بـ Gemini المجاني"],
                horizontal=True, key="search_engine",
            )
            query = st.text_area(
                "رمز النقش أو كلمة مفتاحية أو نص النقش",
                placeholder="مثال: CIH 352 — أو — bʿl — أو — «نقش سبئي من مأرب»",
                height=110, key="search_query",
            )
            f1, f2 = st.columns(2)
            with f1:
                corpus_filter = st.selectbox(
                    "المجموعة / المدونة", ["الكل", "CIH", "RES", "Ja", "CSAI", "Ry", "Ir", "Gl"],
                    key="search_corpus_filter",
                )
            with f2:
                region_filter = st.text_input("الموقع/المنطقة (اختياري)", key="search_region_filter",
                                              placeholder="مأرب، صرواح، ظفار…")

            st.markdown("**مرفق الصورة (اختياري)**")
            attachment_status()
            a1, a2 = st.columns(2)
            with a1:
                upload_icon_button("search_upload_btn", "فتح نافذة الرفع")
            with a2:
                run = st.button("🚀 ابدأ البحث", type="primary", width="stretch", key="search_run")

        if run:
            if not query.strip() and not st.session_state.pending_image:
                st.warning("أدخل رمز النقش أو نصه، أو أرفق صورة النقش.")
            elif engine.startswith("🔍"):
                with st.spinner("جارٍ البحث في الفهرس المحلي والأرشيف…"):
                    st.session_state.search_result = {
                        "mode": "local",
                        "data": run_local_search(query, region_filter, corpus_filter),
                        "at": now_str(),
                    }
            else:
                key = st.session_state.gemini_free_key
                if not key:
                    st.error("أضف مفتاح Gemini المجاني من اللوحة الجانبية للاستعلام (يُحفظ في جلستك فقط).")
                else:
                    prompt = (
                        f"{SYSTEM_PROMPT_LOOKUP}\n\n"
                        f"---\n**الاستعلام:** {query or '[صورة نقش مرفقة]'}\n"
                        f"**فلتر المدونة:** {corpus_filter} — **فلتر الموقع:** {region_filter or 'غير محدد'}\n"
                    )
                    try:
                        with st.spinner("جارٍ الاستدلال عبر Gemini المجاني…"):
                            text = gemini_generate(
                                key, st.session_state.get("gemini_model_choice", GEMINI_MODELS[0]),
                                prompt, image=st.session_state.pending_image,
                            )
                        st.session_state.search_result = {
                            "mode": "gemini", "text": text,
                            "query": query, "at": now_str(),
                        }
                    except Exception as exc:
                        st.session_state.search_result = {"mode": "error", "error": str(exc), "at": now_str()}

    with col_side:
        with st.container(border=True):
            st.markdown("<div class='sec-title'>🔑 مفتاح Gemini المجاني</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='sec-sub'>مفتاح من حسابك المجاني في Google AI Studio — منفصل تماماً عن مزودي التحليل.</div>",
                unsafe_allow_html=True,
            )
            if st.session_state.gemini_free_key:
                masked = st.session_state.gemini_free_key[:6] + "…" + st.session_state.gemini_free_key[-4:]
                st.markdown(f"<span class='pill pill-ok'>مضبوط</span> <code>{masked}</code>",
                            unsafe_allow_html=True)
                if st.button("إزالة المفتاح من الجلسة", width="stretch", key="gem_clear"):
                    st.session_state.gemini_free_key = ""
                    st.rerun()
            else:
                new_key = st.text_input("مفتاح Gemini", type="password", key="gem_key_input",
                                        placeholder="AIza…", label_visibility="collapsed")
                if st.button("حفظ في الجلسة فقط", type="primary", width="stretch", key="gem_save"):
                    if new_key.strip():
                        st.session_state.gemini_free_key = new_key.strip()
                        st.success("تم الحفظ في الجلسة (لن يُكتب في قاعدة البيانات).")
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.warning("أدخل المفتاح أولاً.")
                st.caption("الحصول على مفتاح مجاني: aistudio.google.com/app/apikey")

            if st.session_state.get("gem_model_select") not in GEMINI_MODELS:
                st.session_state.gem_model_select = GEMINI_MODELS[0]
            st.session_state.gemini_model_choice = st.selectbox(
                "نموذج Gemini", GEMINI_MODELS, key="gem_model_select",
            )
            st.divider()
            st.markdown(
                "<div class='kv'>🔒 <b>خصوصية:</b> يُرسل المفتاح من متصفحك إلى Google مباشرة عند الضغط على "
                "«ابدأ البحث» فقط، ولا يُخزَّن خارج جلستك.</div>",
                unsafe_allow_html=True,
            )

    # ---------- النتائج ----------
    res = st.session_state.search_result
    st.write("")
    with st.container(border=True):
        st.markdown("<div class='sec-title'>📑 النتائج</div>", unsafe_allow_html=True)
        if not res:
            st.markdown("<div class='kv'>لا توجد نتائج بعد — ابدأ بحثاً من اللوحة أعلاه.</div>",
                        unsafe_allow_html=True)
        elif res["mode"] == "local":
            data = res["data"]
            st.markdown(
                f"<div class='kv'>استعلام: <b>{data['query'] or '—'}</b> · "
                f"مطابقات الفهرس: <b>{len(data['corpus'])}</b> · "
                f"مطابقات أرشيفي: <b>{len(data['archive'])}</b> · {fmt_dt(res['at'])}</div>",
                unsafe_allow_html=True,
            )
            if data["corpus"]:
                df = pd.DataFrame(data["corpus"])[["code", "corpus", "script", "region", "century", "scope"]]
                df.columns = ["الرمز", "المجموعة", "الخط", "الموقع", "الحقبة", "النطاق"]
                st.dataframe(df, width="stretch", hide_index=True)
                with st.expander("تفاصيل المداخل المطابقة (نص/ملاحظات)"):
                    for r in data["corpus"][:20]:
                        st.markdown(
                            f"**{r['code']}** — {r['corpus']}\n\n"
                            f"- الخط: {r['script'] or '—'} · الموقع: {r['region'] or '—'} · الحقبة: {r['century'] or '—'}\n"
                            f"- نص/تحليل: {r['text'] or '—'}\n- ملاحظة: {r['note'] or '—'}"
                        )
                        st.divider()
            if data["archive"]:
                st.markdown("**من أرشيف محادثاتي:**")
                for h in data["archive"][:10]:
                    st.markdown(f"- [{h['title']}](?) · آخر تحديث {fmt_dt(h['updated_at'])}")
            if not data["corpus"] and not data["archive"]:
                st.info("لا مطابقات محلية. جرّب صياغة أخرى، أو شغّل «بحث وتحليل بـ Gemini المجاني».")
        elif res["mode"] == "gemini":
            st.markdown("<span class='pill pill-ok'>نتيجة Gemini المجاني</span>", unsafe_allow_html=True)
            st.markdown(res["text"])
            download_row(res["text"], "search_gemini", "بطاقة_تعريف_نقش")
            if st.button("💾 حفظ النتيجة في الأرشيف", key="save_search_result"):
                nid = new_id()
                title = (res.get("query") or "نتيجة بحث")[:40]
                msgs = [{"role": "assistant", "content": res["text"]}]
                st.session_state.archive[nid] = {
                    "title": title, "messages": msgs, "created_at": now_str(), "updated_at": now_str()
                }
                save_chat(OWNER, nid, title, msgs)
                st.success("تم الحفظ في الأرشيف.")
        else:
            st.error(f"تعذّر إتمام البحث: {res.get('error')}")

    # ---------- إدارة الفهرس ----------
    with st.expander("🗂️ إدارة فهرس النقوش الخاص بي (يبني البحث المحلي بدون مفتاح)"):
        st.caption("أضف أو عدّل مداخل فهرسك: الرمز، المدونة، الخط، الموقع، الحقبة، النص، ملاحظات. المداخل المدمجة مرجعية للقراءة فقط.")
        rows = [r for r in load_corpus(OWNER) if r["owner"] == OWNER]
        if rows:
            df = pd.DataFrame(rows)[SEED_COLUMNS]
        else:
            df = pd.DataFrame(columns=SEED_COLUMNS)
        edited = st.data_editor(
            df, num_rows="dynamic", width="stretch", key="corpus_editor",
            column_config={
                "entry_id": st.column_config.TextColumn("ID", disabled=True, width="small"),
                "code": st.column_config.TextColumn("الرمز*", required=True),
                "corpus": st.column_config.TextColumn("المجموعة"),
                "script": st.column_config.TextColumn("الخط"),
                "region": st.column_config.TextColumn("الموقع"),
                "century": st.column_config.TextColumn("الحقبة"),
                "text": st.column_config.TextColumn("النص/الملخص", width="large"),
                "note": st.column_config.TextColumn("ملاحظة", width="large"),
            },
        )
        e1, e2 = st.columns([1, 1])
        with e1:
            if st.button("💾 حفظ/تحديث الفهرس", type="primary", width="stretch", key="corpus_save"):
                n = upsert_corpus_rows(OWNER, edited)
                st.success(f"تم حفظ {n} مدخلاً في فهرسك الخاص.")
                time.sleep(0.3)
                st.rerun()
        with e2:
            if rows:
                to_del = st.selectbox("حذف مدخل", ["—"] + [f"{r['code']}" for r in rows],
                                      key="corpus_del_select")
                if to_del != "—":
                    if st.button("🗑️ حذف المدخل", width="stretch", key="corpus_del_btn"):
                        target = next(r for r in rows if r["code"] == to_del)
                        delete_corpus_entry(OWNER, target["entry_id"])
                        st.success("تم الحذف.")
                        time.sleep(0.2)
                        st.rerun()


# =====================================================================================
# 12) عرض المساعد الإبيغرافي (مزود + نموذج)
# =====================================================================================
def provider_key(name: str) -> str:
    return st.session_state.secret_keys.get(name, "")


def render_chat_view() -> None:
    prov_names = list(PROVIDERS.keys())
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.3, 1.7, 1, 1], vertical_alignment="bottom")
        with c1:
            sel_prov = st.selectbox("🔌 المزود", prov_names, key="chat_provider_select")
        prov = PROVIDERS[sel_prov]
        models = list(prov.get("models", {}).keys())
        with c2:
            if models:
                sel_model = st.selectbox(
                    "🤖 النموذج", models, key="chat_model_select",
                    format_func=lambda x: f"{prov['models'][x].get('alias', x)}",
                )
            else:
                sel_model = None
                st.warning("لا نماذج لهذا المزود — اجلبها من الإعدادات.", icon="⚠️")
        with c3:
            cur_key = provider_key(sel_prov)
            st.markdown(
                f"<div class='kv' style='padding-bottom:8px'>"
                f"<span class='pill {'pill-ok' if cur_key else 'pill-warn'}'>"
                f"{'مفتاح الجلسة مضبوط' if cur_key else 'لا مفتاح'}</span></div>",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f"<div class='kv' style='padding-bottom:8px'>"
                f"<span class='pill pill-info'>📂 {ARCHIVE[CURRENT_CHAT]['title'][:22]}</span></div>",
                unsafe_allow_html=True,
            )

        if not cur_key:
            k = st.text_input("مفتاح API لهذا المزود (يبقى في جلستك فقط)", type="password",
                              key=f"chat_key_{sel_prov}", placeholder="sk-… / AIza…")
            kc1, kc2 = st.columns([1, 3])
            with kc1:
                if st.button("حفظ المفتاح", type="primary", width="stretch", key=f"chat_key_save_{sel_prov}"):
                    if k.strip():
                        st.session_state.secret_keys[sel_prov] = k.strip()
                        st.rerun()
                    else:
                        st.warning("أدخل المفتاح.")
            with kc2:
                st.caption("يُستخدم هذا الاتصال للتحليل فقط. للمفاتيح المزعجة استخدم مفتاح Gemini المجاني في تبويب البحث.")

    st.write("")

    # ---------- الرسائل ----------
    if not MESSAGES:
        st.markdown(
            """<div class='kv' style='text-align:center;padding:26px 0'>
                 ابدأ بكتابة استفسار إبيغرافي، أو ارفع صورة نقش عبر 🖼️ ثم أرسل الطلب.<br>
                 <span style='color:#94a3b8'>وإن أردت بحثاً سريعاً بلا مفتاح مزود: تبويب «🔎 البحث عن النقش».</span>
               </div>""",
            unsafe_allow_html=True,
        )
    for idx, msg in enumerate(MESSAGES):
        avatar = "🗿" if msg["role"] == "assistant" else "🧑‍🔬"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and len(msg["content"]) > 400:
                with st.expander("⬇️ تصدير هذه الوثيقة"):
                    download_row(msg["content"], f"msg_{idx}", "وثيقة_إبيغرافية")

    st.write("")
    with st.container(border=True):
        attachment_status()
        prompt = st.chat_input("اكتب سؤالك الأكاديمي أو الصق حروف النقش…")
        st.caption("🔒 تُحفظ المحادثة في أرشيفك الخاص بهذه الجلسة فقط، ولا تُرسل إلا لمزوّد النموذج الذي اخترته.")

    if prompt:
        image = st.session_state.pending_image
        if len(MESSAGES) == 0:
            ARCHIVE[CURRENT_CHAT]["title"] = prompt[:38]
        MESSAGES.append({
            "role": "user",
            "content": prompt if not image else f"[صورة نقش مرفوعة: {image['name']}] {prompt}",
        })
        with st.chat_message("user", avatar="🧑‍🔬"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🗿"):
            try:
                if not sel_model:
                    raise RuntimeError("اختر نموذجاً أولاً (أو اجلب النماذج من الإعدادات).")
                with st.status("جارٍ إنجاز الدراسة الإبيغرافية…", expanded=True) as status:
                    st.write("① فحص باليوجرافي وتحليل خط المسند")
                    st.write("② نقل حرفي صوتي وفق معايير Beeston")
                    st.write("③ تحليل صرفي ومعجمي ومطابقة DASI/CSAI")
                    st.write("④ صياغة وثيقة التوثيق والختم الرقمي")
                    api_messages = [{"role": "system", "content": SYSTEM_PROMPT_ANALYSIS}] + [
                        {"role": m["role"], "content": m["content"]} for m in MESSAGES
                    ]
                    text = openai_chat(prov, cur_key, sel_model, api_messages, image=image)
                    status.update(label="✅ تم إنجاز الوثيقة", state="complete", expanded=False)
                st.markdown(text)
                MESSAGES.append({"role": "assistant", "content": text})
                st.session_state.pending_image = None
            except Exception as exc:
                note = (
                    f"⚠️ **تعذّر إتمام الطلب:** `{exc}`\n\n"
                    "تحقّق من المفتاح/الرابط في الإعدادات، أو استخدم **«بحث وتحليل بـ Gemini المجاني»** "
                    "من تبويب «🔎 البحث عن النقش» — فهو لا يحتاج مفتاح المزود الرئيسي."
                )
                st.error(note)
                MESSAGES.append({"role": "assistant", "content": note})
        save_chat(OWNER, CURRENT_CHAT, ARCHIVE[CURRENT_CHAT]["title"], MESSAGES)
        st.rerun()


# =====================================================================================
# 13) الأرشيف
# =====================================================================================
def render_archive_view() -> None:
    with st.container(border=True):
        h1, h2 = st.columns([3, 1], vertical_alignment="bottom")
        with h1:
            st.markdown("<div class='sec-title'>📚 أرشيفي الخاص</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='sec-sub'>{len(st.session_state.archive)} محادثة · مرتبطة بهويتك المؤقتة "
                f"<code>{OWNER[:8]}</code> ولا يراها غيرك.</div>", unsafe_allow_html=True,
            )
        with h2:
            export = json.dumps(
                [{"title": c["title"], "messages": c["messages"], "updated_at": c.get("updated_at", "")}
                 for c in st.session_state.archive.values()],
                ensure_ascii=False, indent=2,
            )
            st.download_button("⬇️ تصدير الأرشيف (JSON)", data=export.encode("utf-8"),
                               file_name=f"archive_{datetime.now():%Y%m%d}.json",
                               mime="application/json", width="stretch", key="exp_archive")

    filt = st.text_input("🔎 فلترة", placeholder="عنوان أو نص داخل المحادثات…", key="archive_filter")
    rows = []
    for cid, c in st.session_state.archive.items():
        blob = normalize_ar(c["title"] + " " + " ".join(m.get("content", "") for m in c["messages"]))
        if filt.strip() and normalize_ar(filt) not in blob:
            continue
        rows.append((cid, c))

    if not rows:
        st.info("لا محادثات مطابقة.")
        return

    for cid, c in rows:
        with st.container(border=True):
            cc1, cc2, cc3, cc4 = st.columns([3, 1.2, 1, 1], vertical_alignment="center")
            with cc1:
                st.markdown(f"**{c['title']}**")
                st.caption(f"{len(c['messages'])} رسالة · آخر تحديث {fmt_dt(c.get('updated_at',''))}")
            with cc2:
                if st.button("فتح", key=f"arch_open_{cid}", width="stretch"):
                    st.session_state.current_chat_id = cid
                    goto("chat")
            with cc3:
                md = "\n\n---\n\n".join(f"### {m['role']}\n{m['content']}" for m in c["messages"]) or "—"
                st.download_button("⬇️ MD", data=md.encode("utf-8"),
                                   file_name=f"{c['title'][:20]}.md", mime="text/markdown",
                                   width="stretch", key=f"arch_dl_{cid}")
            with cc4:
                if st.button("🗑️", key=f"arch_del_{cid}", help="حذف المحادثة"):
                    delete_chat(OWNER, cid)
                    st.session_state.archive.pop(cid, None)
                    if st.session_state.current_chat_id == cid:
                        st.session_state.current_chat_id = list(st.session_state.archive.keys())[0] if st.session_state.archive else ""
                    st.rerun()


# =====================================================================================
# 14) الإعدادات
# =====================================================================================
def render_settings_view() -> None:
    st.markdown("<div class='sec-title'>⚙️ لوحة التحكم المركزية</div>", unsafe_allow_html=True)
    st.markdown("<div class='sec-sub'>إدارة المزودين والنماذج وإعدادات الشبكة — كل شيء معزول لهذا المستخدم.</div>",
                unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["🔌 المزودون والنماذج", "🔑 المفاتيح والخصوصية", "🌐 الشبكة والمهل"])

    # ---- المزودون ----
    with tab1:
        with st.expander("➕ إضافة مزود مخصص"):
            with st.form("add_provider", clear_on_submit=True):
                f1, f2 = st.columns(2)
                with f1:
                    name = st.text_input("اسم المزود", placeholder="مثال: OpenRouter")
                    style = st.selectbox("نمط API", ["OpenAI API", "OpenAI Responses API",
                                                     "Anthropic Claude API", "Google Gemini API"])
                with f2:
                    url = st.text_input("Base URL", value="https://openrouter.ai/api/v1")
                    path = st.text_input("المسار", value="/chat/completions")
                nk = st.text_input("مفتاح API (للجلسة فقط — لن يُحفظ)", type="password")
                net = st.checkbox("تحسين توافق الشبكة", value=True)
                if st.form_submit_button("حفظ المزود", type="primary"):
                    nm = name.strip()
                    if not nm:
                        st.error("أدخل اسم المزود.")
                    elif nm in st.session_state.providers:
                        st.error("اسم المزود موجود.")
                    else:
                        st.session_state.providers[nm] = {
                            "api_style": style, "url": url.strip(), "path": path.strip(),
                            "network_opt": net, "models": {},
                        }
                        save_provider(OWNER, nm, st.session_state.providers[nm])
                        if nk.strip():
                            st.session_state.secret_keys[nm] = nk.strip()
                        st.success(f"أُضيف المزود «{nm}».")
                        st.rerun()

        pnames = list(st.session_state.providers.keys())
        sel = st.selectbox("اختر المزود للتعديل", pnames, key="settings_provider_select")
        prov = st.session_state.providers[sel]

        c1, c2 = st.columns(2)
        with c1:
            style_opts = ["OpenAI API", "OpenAI Responses API", "Anthropic Claude API", "Google Gemini API"]
            if st.session_state.get(f"st_style_{sel}") not in style_opts:
                st.session_state[f"st_style_{sel}"] = (
                    prov.get("api_style") if prov.get("api_style") in style_opts else "OpenAI API"
                )
            style = st.selectbox("نمط API", style_opts, key=f"st_style_{sel}")
            if f"st_url_{sel}" not in st.session_state:
                st.session_state[f"st_url_{sel}"] = prov.get("url", "")
            url = st.text_input("Base URL", key=f"st_url_{sel}")
        with c2:
            if f"st_path_{sel}" not in st.session_state:
                st.session_state[f"st_path_{sel}"] = prov.get("path", "")
            path = st.text_input("المسار", key=f"st_path_{sel}")
            key_val = st.text_input("مفتاح API (جلسة فقط)", type="password", key=f"st_key_{sel}")
        if f"st_net_{sel}" not in st.session_state:
            st.session_state[f"st_net_{sel}"] = bool(prov.get("network_opt", True))
        net = st.toggle("تحسين توافق الشبكة", key=f"st_net_{sel}")

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("💾 حفظ", type="primary", width="stretch", key=f"st_save_{sel}"):
                prov.update({"api_style": style, "url": url, "path": path, "network_opt": net})
                save_provider(OWNER, sel, prov)
                if key_val.strip():
                    st.session_state.secret_keys[sel] = key_val.strip()
                st.success("تم الحفظ (المفتاح في الجلسة فقط).")
                st.rerun()
        with b2:
            if st.button("🧪 اختبار الاتصال", width="stretch", key=f"st_test_{sel}"):
                k = key_val.strip() or provider_key(sel)
                if not k:
                    st.warning("أدخل المفتاح.")
                elif openai is None:
                    st.error("حزمة openai غير مثبتة.")
                else:
                    try:
                        openai.OpenAI(api_key=k, base_url=url.rstrip("/"), timeout=30.0).models.list()
                        st.success("✅ الاتصال سليم.")
                    except Exception as exc:
                        st.error(f"❌ {exc}")
        with b3:
            if st.button("🔄 جلب النماذج", width="stretch", key=f"st_fetch_{sel}"):
                k = key_val.strip() or provider_key(sel)
                if not k:
                    st.warning("أدخل المفتاح أولاً.")
                elif "gemini" in url.lower():
                    prov["models"] = {m: {"alias": m, "type": "دردشة", "vision": True, "tools": True,
                                          "reasoning": False, "context": 1000000, "max_tokens": 8192}
                                      for m in GEMINI_MODELS}
                    save_provider(OWNER, sel, prov)
                    st.success(f"تم ضبط {len(prov['models'])} نموذج Gemini.")
                    st.rerun()
                else:
                    try:
                        with st.spinner("جارٍ الجلب…"):
                            remote = openai.OpenAI(api_key=k, base_url=url.rstrip("/"), timeout=40.0).models.list()
                            fetched = {m.id: {"alias": m.id, "type": "دردشة", "vision": True, "tools": True,
                                              "reasoning": False, "context": 64000, "max_tokens": 4096}
                                       for m in remote}
                        if fetched:
                            prov["models"] = fetched
                            save_provider(OWNER, sel, prov)
                            st.success(f"تم جلب {len(fetched)} نموذجاً.")
                            st.rerun()
                        else:
                            st.warning("لم تُرجِع السيرفر نماذج.")
                    except Exception as exc:
                        st.error(f"❌ {exc}")
        with b4:
            if len(pnames) > 1 and st.button("🗑️ حذف المزود", width="stretch", key=f"st_del_{sel}"):
                st.session_state.providers.pop(sel, None)
                st.session_state.secret_keys.pop(sel, None)
                delete_provider(OWNER, sel)
                st.success("تم الحذف.")
                st.rerun()

        with st.expander(f"🧠 نماذج المزود الحالي ({len(prov.get('models', {}))})"):
            if prov.get("models"):
                st.dataframe(
                    pd.DataFrame([{"model_id": k, "alias": v.get("alias", k),
                                   "vision": v.get("vision", False), "context": v.get("context", "")}
                                  for k, v in prov["models"].items()]),
                    width="stretch", hide_index=True,
                )
            else:
                st.caption("لا نماذج — استخدم «🔄 جلب النماذج».")

    # ---- المفاتيح والخصوصية ----
    with tab2:
        st.markdown("#### 🔑 مفاتيح الجلسة")
        st.caption("هذه المفاتيح موجودة في ذاكرة جلسة المتصفح فقط: لا تُكتب في قاعدة البيانات ولا تُضمَّن في الرابط، وتُمسح بإغلاق التبويب.")
        items = list(st.session_state.secret_keys.items())
        if items:
            for name, k in items:
                st.markdown(f"- **{name}**: `{k[:6]}…{k[-4:]}`")
        else:
            st.info("لا مفاتيح مزودين في الجلسة.")
        gk = st.session_state.gemini_free_key
        st.markdown(f"- **Gemini المجاني (بحث)**: `{gk[:6]}…{gk[-4:]}`" if gk else "- **Gemini المجاني (بحث)**: غير مضبوط")
        if st.button("🧹 مسح كل المفاتيح من الجلسة", key="wipe_keys"):
            st.session_state.secret_keys = {}
            st.session_state.gemini_free_key = ""
            st.success("تم مسح المفاتيح.")
            st.rerun()

        st.divider()
        st.markdown("#### 🔒 عزل المستخدمين")
        st.markdown(
            f"""
- معرّف جلستك: `{OWNER}` (عشوائي، مؤقت، لا يُنقل عبر الرابط).
- المحادثات تُخزَّن في جدول `chats_v2` بعمود `owner` — لا يمكن لمستخدم آخر استعلام صفوفك.
- المفاتيح لا تُخزَّن مطلقاً في قاعدة البيانات (أُلغي عمود المفاتيح، ونُظّفت أي قيم قديمة).
- معاملات الرابط الحساسة (`?key=`, `?chat_id=` …) تُحذف تلقائياً عند كل تحميل.
- زر «حذف بياناتي نهائياً» في الشريط الجانبي يمحو كل صفوفك.
            """
        )
        st.download_button("⬇️ تصدير بياناتي (JSON)", data=json.dumps(
            {"owner": OWNER, "chats": list(st.session_state.archive.values()),
             "corpus": [r for r in load_corpus(OWNER) if r["owner"] == OWNER]},
            ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"my_data_{datetime.now():%Y%m%d}.json", mime="application/json",
            key="exp_my_data")

    # ---- الشبكة ----
    with tab3:
        st.markdown("#### 🌐 الشبكة والمهل")
        if "net_timeout" not in st.session_state:
            st.session_state.net_timeout = 120
        if "net_compat" not in st.session_state:
            st.session_state.net_compat = True
        st.slider("مهلة الاتصال العامة (ثانية)", 10, 300, key="net_timeout")
        st.toggle("تحسين توافق الشبكة للمزودين المخصصين", key="net_compat")
        st.caption("تُطبَّق المهلة على استدعاءات النماذج في هذه الجلسة.")
        st.divider()
        st.markdown("#### ℹ️ عن المنصة")
        st.markdown(
            "الإصدار **2.0** — واجهة معاد ترتيبها، نافذة رفع نقش مستقلة، عزل كامل لكل مستخدم، "
            "وبحث عن النقش يعمل بمفتاح **Gemini المجاني** أو محلياً **بدون أي مفتاح**."
        )


# =====================================================================================
# 15) التوجيه
# =====================================================================================
if VIEW == "search":
    render_search_view()
elif VIEW == "chat":
    render_chat_view()
elif VIEW == "archive":
    render_archive_view()
else:
    render_settings_view()

st.markdown(
    "<div style='text-align:center;color:#94a3b8;font-size:.7rem;padding-top:26px'>"
    "مختبر المسند الرقمي · جلسة خاصة معزولة · لا تُشارَك المفاتيح ولا السجلات مع أي مستخدم آخر"
    "</div>",
    unsafe_allow_html=True,
)
