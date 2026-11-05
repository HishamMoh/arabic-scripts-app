# -*- coding: utf-8 -*-
"""
المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة
Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics
الإصدار 3.0 — إعادة بناء الهوية والتنقل إلى أربع مساحات عمل أكاديمية واضحة.
"""

import base64
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import sqlite3
import time
import textwrap
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime

import pandas as pd
import streamlit as st

from academic_prompts import SYSTEM_PROMPT_ANALYSIS, SYSTEM_PROMPT_LOOKUP
from services import (
    check_catalogs,
    fetch_provider_models,
    gemini_generate,
    openai,
    openai_chat,
)

# =====================================================================================
# 1) إعداد الصفحة والهوية البصرية
# =====================================================================================
APP_TITLE = "المختبر الرقمي لدراسات المسند ونقوش جنوب الجزيرة العربية القديمة"
APP_SUBTITLE = "Laboratory of South Arabian Epigraphy & Semitic Paleo-Linguistics"

DB_PATH = "musnad_lab_v2.db"
LEGACY_DB_PATH = "chats_archive.db"
SHARED_OWNER = "__shared_index__"
LOGGER = logging.getLogger(__name__)

st.set_page_config(
    page_title="مختبر المسند الرقمي",
    page_icon="🗿",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =====================================================================================
# 2) أدوات مساعدة عامة
# =====================================================================================
# https://docs.python.org/3/library/datetime.html#datetime.datetime.strftime
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# https://docs.python.org/3/library/uuid.html#uuid.uuid4
def new_id() -> str:
    return uuid.uuid4().hex[:16]


# https://docs.python.org/3/library/re.html
# هذا التطبيع قاعدة بحث محلية مبسطة، وليس معياراً لغوياً أو إبيغرافياً.
def normalize_ar(text: str) -> str:
    """تطبيع عربي/لاتيني مبسّط لأغراض البحث المحلي دون مفتاح."""
    if not text:
        return ""
    t = str(text).lower()
    t = re.sub(r"[\u064B-\u0652\u0670\u06D6-\u06ED]", "", t)  # تشكيل
    t = t.replace("ـ", "")
    for a, b in (
        ("أ", "ا"),
        ("إ", "ا"),
        ("آ", "ا"),
        ("ٱ", "ا"),
        ("ى", "ي"),
        ("ئ", "ي"),
        ("ؤ", "و"),
        ("ة", "ه"),
    ):
        t = t.replace(a, b)
    t = re.sub(r"[^\w\u0600-\u06FF<>/\[\]\- ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# https://docs.python.org/3/library/base64.html#base64.b64encode
def encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


# https://docs.python.org/3/library/string.html#format-string-syntax
def bytes_to_kb(n: int) -> str:
    return f"{n/1024:.0f} KB"


# https://docs.python.org/3/library/datetime.html#datetime.datetime.strptime
def fmt_dt(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime(
            "%Y/%m/%d · %H:%M"
        )
    except (ValueError, TypeError):
        return value or "—"


# https://docs.streamlit.io/develop/api-reference/execution-flow/st.rerun
def goto(view_key: str) -> None:
    """تبديل العرض مع مزامنة شريط التنقل (بدون أي معاملات في الرابط)."""
    st.session_state.view = view_key
    st.session_state.pop("nav_segmented", None)
    st.session_state.pop("nav_top", None)
    st.rerun()


# https://docs.python.org/3/library/hashlib.html#hashlib.pbkdf2_hmac
def hash_pin(pin: str) -> str:
    """اشتقاق تجزئة مملحة لرمز المرور (PBKDF2-HMAC-SHA256)."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 240_000)
    return f"{salt.hex()}:{digest.hex()}"


# https://docs.python.org/3/library/hmac.html#hmac.compare_digest
def verify_pin(pin: str, stored: str | None) -> bool:
    """التحقق من رمز المرور دون مقارنة نصية مباشرة."""
    try:
        salt_hex, digest_hex = (stored or "").split(":", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), 240_000
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# =====================================================================================
# 3) قاعدة البيانات — كل صف مرتبط بمالك (user_token) + لا تُخزَّن أي مفاتيح API
# =====================================================================================
# https://docs.python.org/3/library/sqlite3.html#sqlite3.connect
def db_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, timeout=10)


# https://docs.python.org/3/library/sqlite3.html
def init_db() -> None:
    with closing(db_conn()) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS chats_v2 (
                   chat_id TEXT PRIMARY KEY,
                   owner   TEXT NOT NULL,
                   title   TEXT,
                   messages TEXT,
                   created_at TEXT,
                   updated_at TEXT
               )""")
        c.execute("""CREATE TABLE IF NOT EXISTS providers_v2 (
                   owner TEXT NOT NULL,
                   name TEXT NOT NULL,
                   api_style TEXT,
                   url TEXT,
                   path TEXT,
                   network_opt INTEGER,
                   models TEXT,
                   PRIMARY KEY (owner, name)
               )""")
        c.execute("""CREATE TABLE IF NOT EXISTS corpus_v2 (
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
               )""")
        # جدول التخزين المؤقت الميداني (Offline Queue)
        c.execute("""CREATE TABLE IF NOT EXISTS offline_queue (
                   queue_id TEXT PRIMARY KEY,
                   owner TEXT NOT NULL,
                   kind TEXT NOT NULL,           -- 'search' | 'analysis'
                   query TEXT,
                   image_b64 TEXT,
                   image_name TEXT,
                   image_mime TEXT,
                   status TEXT DEFAULT 'pending', -- pending | processing | done | failed
                   result TEXT,
                   created_at TEXT,
                   processed_at TEXT
               )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chats_owner ON chats_v2(owner)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_corpus_owner ON corpus_v2(owner)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_owner ON offline_queue(owner, status)"
        )
        conn.commit()
    purge_legacy_secrets()
    seed_reference_index()


# https://docs.python.org/3/library/sqlite3.html
def purge_legacy_secrets() -> None:
    """حذف أي مفاتيح API قديمة كانت محفوظة في قاعدة البيانات المشتركة (الإصدار السابق)."""
    try:
        if not os.path.exists(LEGACY_DB_PATH):
            return
        with closing(sqlite3.connect(LEGACY_DB_PATH)) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(providers)")]
            if "api_key" in cols:
                conn.execute("UPDATE providers SET api_key = ''")
                conn.commit()
    except sqlite3.Error:
        st.warning("تعذّر تنظيف المفاتيح القديمة؛ تحقق من قاعدة البيانات السابقة.")


# ---------- المحادثات ----------
# https://docs.python.org/3/library/json.html#json.loads
def load_chats(owner: str) -> dict:
    with closing(db_conn()) as conn:
        rows = conn.execute(
            "SELECT chat_id, title, messages, created_at, updated_at FROM chats_v2 "
            "WHERE owner = ? ORDER BY updated_at DESC, created_at DESC",
            (owner,),
        ).fetchall()
    out: dict = {}
    for chat_id, title, msgs, created, updated in rows:
        try:
            out[chat_id] = {
                "title": title or "بدون عنوان",
                "messages": json.loads(msgs or "[]"),
                "created_at": created or "",
                "updated_at": updated or "",
            }
        except (json.JSONDecodeError, TypeError):
            LOGGER.warning("Skipped a malformed chat record.")
    return out


# https://www.sqlite.org/lang_upsert.html
def save_chat(owner: str, chat_id: str, title: str, messages: list) -> None:
    with closing(db_conn()) as conn:
        row = conn.execute(
            "SELECT created_at FROM chats_v2 WHERE chat_id = ? AND owner = ?",
            (chat_id, owner),
        ).fetchone()
        created = row[0] if row and row[0] else now_str()
        conn.execute(
            "INSERT INTO chats_v2 (chat_id, owner, title, messages, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(chat_id) DO UPDATE SET "
            "title=excluded.title, messages=excluded.messages, updated_at=excluded.updated_at "
            "WHERE chats_v2.owner=excluded.owner",
            (
                chat_id,
                owner,
                title,
                json.dumps(messages, ensure_ascii=False),
                created,
                now_str(),
            ),
        )
        conn.commit()


# https://docs.python.org/3/library/sqlite3.html
def delete_chat(owner: str, chat_id: str) -> None:
    with closing(db_conn()) as conn:
        conn.execute(
            "DELETE FROM chats_v2 WHERE chat_id = ? AND owner = ?", (chat_id, owner)
        )
        conn.commit()


# https://docs.python.org/3/library/sqlite3.html
def delete_all_user_data(owner: str) -> None:
    with closing(db_conn()) as conn:
        for table in ("chats_v2", "providers_v2", "corpus_v2", "offline_queue"):
            conn.execute(f"DELETE FROM {table} WHERE owner = ?", (owner,))
        conn.commit()


# ---------- المزودون (بدون مفاتيح) ----------
DEFAULT_PROVIDERS = {
    "Google Gemini (مجاني)": {
        "api_style": "Google Gemini API",
        "url": "https://generativelanguage.googleapis.com/v1beta",
        "path": "",
        "network_opt": True,
        "models": {
            "gemini-2.5-flash": {
                "alias": "Gemini 2.5 Flash (مجاني)",
                "type": "دردشة",
                "vision": True,
                "tools": True,
                "reasoning": False,
                "context": 1000000,
                "max_tokens": 8192,
            },
            "gemini-2.5-flash-lite": {
                "alias": "Gemini 2.5 Flash Lite (مجاني)",
                "type": "دردشة",
                "vision": True,
                "tools": True,
                "reasoning": False,
                "context": 1000000,
                "max_tokens": 8192,
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
                "alias": "Gemini 2.5 Flash المجاني (OpenRouter)",
                "type": "دردشة",
                "vision": True,
                "tools": True,
                "reasoning": False,
                "context": 1000000,
                "max_tokens": 8192,
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
                "alias": "Qwen 2.5 7B Instruct",
                "type": "دردشة",
                "vision": False,
                "tools": True,
                "reasoning": False,
                "context": 32768,
                "max_tokens": 4096,
            },
            "deepseek-ai/DeepSeek-V3": {
                "alias": "DeepSeek V3",
                "type": "دردشة",
                "vision": False,
                "tools": True,
                "reasoning": False,
                "context": 64000,
                "max_tokens": 4096,
            },
        },
    },
}


# https://docs.python.org/3/library/json.html#json.loads
def load_providers(owner: str) -> dict:
    with closing(db_conn()) as conn:
        rows = conn.execute(
            "SELECT name, api_style, url, path, network_opt, models FROM providers_v2 WHERE owner = ?",
            (owner,),
        ).fetchall()

    if not rows:
        for name, data in DEFAULT_PROVIDERS.items():
            save_provider(owner, name, data)
        return json.loads(json.dumps(DEFAULT_PROVIDERS))

    out = {}
    for name, style, url, path, net, models_json in rows:
        try:
            models = (
                json.loads(models_json)
                if isinstance(models_json, str)
                else (models_json or {})
            )
            if not isinstance(models, dict):
                models = {}
        except (json.JSONDecodeError, TypeError):
            LOGGER.warning("Skipped malformed provider model data.")
            models = {}
        out[name] = {
            "api_style": style or "OpenAI API",
            "url": url or "",
            "path": path or "",
            "network_opt": bool(net),
            "models": models,
        }
    return out


# https://docs.python.org/3/library/sqlite3.html
def save_provider(owner: str, name: str, data: dict) -> None:
    models = data.get("models", {})
    models_str = (
        models if isinstance(models, str) else json.dumps(models, ensure_ascii=False)
    )
    with closing(db_conn()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO providers_v2 (owner, name, api_style, url, path, network_opt, models) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                owner,
                name,
                data.get("api_style", "OpenAI API"),
                data.get("url", ""),
                data.get("path", ""),
                1 if data.get("network_opt", True) else 0,
                models_str,
            ),
        )
        conn.commit()


# https://docs.python.org/3/library/sqlite3.html
def delete_provider(owner: str, name: str) -> None:
    with closing(db_conn()) as conn:
        conn.execute(
            "DELETE FROM providers_v2 WHERE owner = ? AND name = ?", (owner, name)
        )
        conn.commit()


# ---------- الفهرس المرجعي للنقوش (بحث بدون مفتاح) ----------
# هذه عناوين استرشادية غير متحققة، وليست سجلات علمية موثقة.
# https://dasi.cnr.it/
REFERENCE_SEED = [
    (
        "CIH 352",
        "CIH — Corpus Inscriptionum Semiticarum IV",
        "مسند",
        "—",
        "—",
        "",
        "رأس مدخل فهرسي للاستدلال السريع؛ تُستكمل التفاصيل العلمية بعد التحقق من DASI/CSAI.",
    ),
    (
        "RES 3945",
        "RES — Répertoire d'Épigraphie Sémitique",
        "مسند",
        "—",
        "—",
        "",
        "رأس مدخل فهرسي؛ النقش من أشهر النقوش السبئية المدروسة — يُستكمل النقل الحرفي بعد التحقق.",
    ),
    (
        "CIH 6",
        "CIH — Corpus Inscriptionum Semiticarum IV",
        "مسند",
        "—",
        "—",
        "",
        "رأس مدخل فهرسي.",
    ),
    (
        "Ja 576",
        "Ja — Jamme, Sabaean Inscriptions",
        "مسند",
        "—",
        "—",
        "",
        "رأس مدخل فهرسي.",
    ),
    (
        "CSAI I",
        "CSAI — Corpus of South Arabian Inscriptions",
        "مسند",
        "—",
        "—",
        "",
        "سلسلة مدونات النقوش العربية الجنوبية؛ تُفهرس تحتها رموز عديدة.",
    ),
    (
        "Ry / Ir / Gl",
        "مجموعات Ryckmans / al-Iryani / Glaser",
        "مسند",
        "—",
        "—",
        "",
        "رموز مرجعية لمجموعات نقوش؛ يُضاف الرمز الدقيق عند التحقق.",
    ),
]

SEED_COLUMNS = [
    "entry_id",
    "code",
    "corpus",
    "script",
    "region",
    "century",
    "text",
    "note",
]


# https://docs.python.org/3/library/sqlite3.html
def seed_reference_index() -> None:
    with closing(db_conn()) as conn:
        exists = conn.execute(
            "SELECT COUNT(*) FROM corpus_v2 WHERE owner = ?", (SHARED_OWNER,)
        ).fetchone()[0]
        if not exists:
            for idx, row in enumerate(REFERENCE_SEED):
                code, corpus, script, region, century, text, note = row
                conn.execute(
                    "INSERT OR IGNORE INTO corpus_v2 (entry_id, owner, code, corpus, script, region, century, text, note, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"seed_{idx}",
                        SHARED_OWNER,
                        code,
                        corpus,
                        script,
                        region,
                        century,
                        text,
                        note,
                        now_str(),
                    ),
                )
        conn.commit()


# https://docs.python.org/3/library/sqlite3.html
def load_corpus(owner: str) -> list:
    with closing(db_conn()) as conn:
        rows = conn.execute(
            "SELECT entry_id, owner, code, corpus, script, region, century, text, note FROM corpus_v2 "
            "WHERE owner IN (?, ?) ORDER BY owner, code",
            (owner, SHARED_OWNER),
        ).fetchall()
    keys = [
        "entry_id",
        "owner",
        "code",
        "corpus",
        "script",
        "region",
        "century",
        "text",
        "note",
    ]
    return [dict(zip(keys, r)) for r in rows]


# https://pandas.pydata.org/docs/reference/api/pandas.isna.html
def _cell(value) -> str:
    """تحويل آمن لخلية من data_editor إلى نص (يتعامل مع NaN/None)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


# https://www.sqlite.org/lang_upsert.html
def upsert_corpus_rows(owner: str, df: pd.DataFrame) -> int:
    with closing(db_conn()) as conn:
        count = 0
        for _, row in df.iterrows():
            code = _cell(row.get("code"))
            if not code:
                continue
            entry_id = _cell(row.get("entry_id"))
            if (
                not entry_id
                or entry_id.startswith("seed_")
                or entry_id.lower() in ("nan", "none")
            ):
                entry_id = new_id()
            cursor = conn.execute(
                "INSERT INTO corpus_v2 (entry_id, owner, code, corpus, script, region, century, text, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(entry_id) DO UPDATE SET code=excluded.code, corpus=excluded.corpus, "
                "script=excluded.script, region=excluded.region, century=excluded.century, "
                "text=excluded.text, note=excluded.note WHERE corpus_v2.owner=excluded.owner",
                (
                    entry_id,
                    owner,
                    code,
                    _cell(row.get("corpus")),
                    _cell(row.get("script")),
                    _cell(row.get("region")),
                    _cell(row.get("century")),
                    _cell(row.get("text")),
                    _cell(row.get("note")),
                    now_str(),
                ),
            )
            count += cursor.rowcount
        conn.commit()
    return count


# https://docs.python.org/3/library/sqlite3.html
def delete_corpus_entry(owner: str, entry_id: str) -> None:
    with closing(db_conn()) as conn:
        conn.execute(
            "DELETE FROM corpus_v2 WHERE entry_id = ? AND owner = ?", (entry_id, owner)
        )
        conn.commit()


# ---------- قائمة الانتظار الميدانية (Offline Queue) ----------
# https://docs.python.org/3/library/sqlite3.html
def enqueue_offline(owner: str, kind: str, query: str, image: dict | None) -> str:
    """إضافة طلب إلى قائمة الانتظار المؤقتة."""
    qid = new_id()
    with closing(db_conn()) as conn:
        conn.execute(
            "INSERT INTO offline_queue (queue_id, owner, kind, query, image_b64, image_name, image_mime, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (
                qid,
                owner,
                kind,
                query,
                encode_b64(image["bytes"]) if image and image.get("bytes") else None,
                image.get("name") if image else None,
                image.get("mime") if image else None,
                now_str(),
            ),
        )
        conn.commit()
    return qid


# https://docs.python.org/3/library/sqlite3.html
def load_offline_queue(owner: str, status: str | None = None) -> list:
    with closing(db_conn()) as conn:
        if status:
            rows = conn.execute(
                "SELECT queue_id, kind, query, image_name, status, result, created_at, processed_at "
                "FROM offline_queue WHERE owner = ? AND status = ? ORDER BY created_at DESC",
                (owner, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT queue_id, kind, query, image_name, status, result, created_at, processed_at "
                "FROM offline_queue WHERE owner = ? ORDER BY created_at DESC",
                (owner,),
            ).fetchall()
    keys = [
        "queue_id",
        "kind",
        "query",
        "image_name",
        "status",
        "result",
        "created_at",
        "processed_at",
    ]
    return [dict(zip(keys, r)) for r in rows]


# https://docs.python.org/3/library/sqlite3.html
def update_queue_item(
    owner: str, queue_id: str, status: str, result: str | None = None
) -> None:
    with closing(db_conn()) as conn:
        conn.execute(
            "UPDATE offline_queue SET status = ?, result = ?, processed_at = ? WHERE queue_id = ? AND owner = ?",
            (
                status,
                result,
                now_str() if status in ("done", "failed") else None,
                queue_id,
                owner,
            ),
        )
        conn.commit()


# https://www.sqlite.org/lang_update.html
def recover_queue_item(owner: str, queue_id: str) -> bool:
    with closing(db_conn()) as conn:
        cursor = conn.execute(
            "UPDATE offline_queue SET status = 'pending', result = NULL, processed_at = NULL "
            "WHERE owner = ? AND queue_id = ? AND status = 'processing'",
            (owner, queue_id),
        )
        conn.commit()
        return cursor.rowcount == 1


# https://docs.python.org/3/library/sqlite3.html
def delete_queue_item(owner: str, queue_id: str) -> None:
    with closing(db_conn()) as conn:
        conn.execute(
            "DELETE FROM offline_queue WHERE queue_id = ? AND owner = ?",
            (queue_id, owner),
        )
        conn.commit()


# https://docs.python.org/3/library/base64.html#base64.b64decode
def get_queue_image(owner: str, queue_id: str) -> dict | None:
    with closing(db_conn()) as conn:
        row = conn.execute(
            "SELECT image_b64, image_name, image_mime FROM offline_queue WHERE queue_id = ? AND owner = ?",
            (queue_id, owner),
        ).fetchone()
    if row and row[0]:
        return {
            "bytes": base64.b64decode(row[0]),
            "name": row[1] or "queued.jpg",
            "mime": row[2] or "image/jpeg",
        }
    return None


# https://www.sqlite.org/lang_update.html
# https://docs.python.org/3/library/sqlite3.html#sqlite3.Cursor.rowcount
def claim_queue_item(owner: str, queue_id: str) -> bool:
    """Claim a pending item atomically so concurrent workers cannot duplicate it."""
    with closing(db_conn()) as conn:
        cursor = conn.execute(
            "UPDATE offline_queue SET status = 'processing' "
            "WHERE owner = ? AND queue_id = ? AND status = 'pending'",
            (owner, queue_id),
        )
        conn.commit()
        return cursor.rowcount == 1


# https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ThreadPoolExecutor
def process_offline_queue(owner: str, gemini_key: str) -> int:
    """معالجة عناصر قائمة الانتظار عند توفر الاتصال."""
    pending = load_offline_queue(owner, "pending")
    processed = 0
    for item in pending:
        try:
            if not claim_queue_item(owner, item["queue_id"]):
                continue
            image = get_queue_image(owner, item["queue_id"])
            instruction = (
                SYSTEM_PROMPT_ANALYSIS
                if item["kind"] == "analysis"
                else SYSTEM_PROMPT_LOOKUP
            )
            prompt = f"{instruction}\n\n---\n**الاستعلام:** {item['query'] or '[صورة نقش مرفقة]'}\n"
            text = gemini_generate(gemini_key, GEMINI_MODELS[0], prompt, image=image)
            update_queue_item(owner, item["queue_id"], "done", text)
            processed += 1
        except Exception as exc:
            LOGGER.warning("Queue job failed: %s", type(exc).__name__)
            update_queue_item(
                owner,
                item["queue_id"],
                "failed",
                "تعذّرت المعالجة؛ تحقق من الاتصال والمفتاح ثم أعد المحاولة.",
            )
    return processed


# =====================================================================================
# 4) حالة الجلسة: هوية مؤقتة لكل مستخدم + مفاتيح لا تُحفظ ولا تُنقل عبر الرابط
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/caching-and-state/st.query_params
def strip_sensitive_query_params() -> None:
    """منع أي انتقال لبيانات حساسة عبر رابط الصفحة (?key=... / ?chat_id=...)."""
    try:
        qp = st.query_params
        removed = [
            k
            for k in list(qp.keys())
            if normalize_ar(k)
            in {
                "key",
                "api_key",
                "apikey",
                "token",
                "chat",
                "chat_id",
                "provider",
                "model",
                "session",
                "user",
            }
        ]
        for k in removed:
            del qp[k]
    except Exception:
        pass


strip_sensitive_query_params()

# https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
if st.session_state.pop("clear_secret_widgets", False):
    for widget_key in list(st.session_state):
        if widget_key in {
            "wizard_api_key",
            "gem_key_input",
            "new_provider_key",
            "lock_pin_input",
            "lock_pin_confirm",
            "unlock_pin_input",
        } or widget_key.startswith(("st_key_", "chat_key_")):
            st.session_state.pop(widget_key, None)

if "user_token" not in st.session_state:
    st.session_state.user_token = uuid.uuid4().hex
OWNER = st.session_state.user_token

if "secret_keys" not in st.session_state:
    st.session_state.secret_keys = {}
if "gemini_free_key" not in st.session_state:
    st.session_state.gemini_free_key = ""
if "pending_image" not in st.session_state:
    st.session_state.pending_image = None
if "search_result" not in st.session_state:
    st.session_state.search_result = None
if "view" not in st.session_state:
    st.session_state.view = "eye"
if "global_subview" not in st.session_state:
    st.session_state.global_subview = "🌐 البحث والمدونات"
if "global_catalog_pings" not in st.session_state:
    st.session_state.global_catalog_pings = {}
if "confirm_wipe" not in st.session_state:
    st.session_state.confirm_wipe = False

# حالة المظهر الميداني الداكن
if "field_dark_mode" not in st.session_state:
    st.session_state.field_dark_mode = False

# حالة تأمين المفاتيح
if "session_locked" not in st.session_state:
    st.session_state.session_locked = False
if "session_pin_hash" not in st.session_state:
    st.session_state.session_pin_hash = None

# حالة المعالج الذكي
if "wizard_active" not in st.session_state:
    st.session_state.wizard_active = False

# حالة مقارنة النص الحي
if "split_view_enabled" not in st.session_state:
    st.session_state.split_view_enabled = False
if "last_comparison_image" not in st.session_state:
    st.session_state.last_comparison_image = None
if "mock_mode" not in st.session_state:
    st.session_state.mock_mode = not bool(
        st.session_state.secret_keys or st.session_state.gemini_free_key
    )

try:
    init_db()
except sqlite3.Error:
    st.error("تعذّر فتح قاعدة البيانات أو تهيئتها؛ تحقق من صلاحيات التخزين.")
    st.stop()

if "providers" not in st.session_state:
    st.session_state.providers = load_providers(OWNER)
if "archive" not in st.session_state:
    st.session_state.archive = load_chats(OWNER)

ARCHIVE: dict = st.session_state.archive
if not ARCHIVE:
    first_id = new_id()
    ARCHIVE[first_id] = {
        "title": "محادثة جديدة",
        "messages": [],
        "created_at": now_str(),
        "updated_at": now_str(),
    }
    save_chat(OWNER, first_id, "محادثة جديدة", [])
    st.session_state.archive = ARCHIVE

if (
    "current_chat_id" not in st.session_state
    or st.session_state.current_chat_id not in ARCHIVE
):
    st.session_state.current_chat_id = list(ARCHIVE.keys())[0]
CURRENT_CHAT = st.session_state.current_chat_id
MESSAGES: list = ARCHIVE[CURRENT_CHAT]["messages"]
PROVIDERS: dict = st.session_state.providers


# =====================================================================================
# 5) أسماء النماذج الافتراضية؛ خدمات الشبكة في services.py
# =====================================================================================
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]


# =====================================================================================
# 6) جدولة المهام الخلفية
# =====================================================================================
# https://docs.streamlit.io/develop/concepts/architecture/caching
# https://docs.python.org/3/library/concurrent.futures.html
@st.cache_resource
def background_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=4, thread_name_prefix="musnad")


# https://docs.streamlit.io/develop/concepts/design/multithreading
# The submitted functions use only their arguments and never Streamlit APIs.
def start_background_job(kind: str, function, *args, **metadata) -> bool:
    jobs = st.session_state.setdefault("background_jobs", {})
    if kind in jobs:
        return False
    jobs[kind] = {
        "future": background_executor().submit(function, *args),
        "metadata": metadata,
    }
    return True


# https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
@st.fragment(run_every="2s")
def poll_background_jobs() -> None:
    jobs = st.session_state.get("background_jobs", {})
    changed = False
    for kind, job in list(jobs.items()):
        future = job["future"]
        if not future.done():
            continue
        del jobs[kind]
        changed = True
        try:
            result = future.result()
        except Exception as exc:
            LOGGER.warning("Background %s job failed: %s", kind, type(exc).__name__)
            result = None
        if kind == "search":
            st.session_state.search_result = (
                {
                    "mode": "gemini",
                    "text": result,
                    "query": job["metadata"]["query"],
                    "at": now_str(),
                }
                if result is not None
                else {
                    "mode": "error",
                    "error": "تعذّر تنفيذ الطلب؛ تحقق من الاتصال والمفتاح.",
                    "at": now_str(),
                }
            )
        elif kind == "chat":
            chat = st.session_state.archive.get(job["metadata"]["chat_id"])
            if chat is not None:
                text = (
                    result
                    if result is not None
                    else "⚠️ تعذّر تنفيذ الطلب؛ تحقق من الاتصال وإعدادات المزود."
                )
                chat["messages"].append({"role": "assistant", "content": text})
                try:
                    save_chat(
                        OWNER,
                        job["metadata"]["chat_id"],
                        chat["title"],
                        chat["messages"],
                    )
                except sqlite3.Error:
                    LOGGER.warning("Unable to save the completed chat response.")
                    st.session_state.storage_warning = (
                        "تعذّر حفظ الرد في الأرشيف؛ ما زال متاحاً في الجلسة الحالية."
                    )
        elif kind == "catalog":
            if result is not None:
                st.session_state.global_catalog_pings = result
        elif kind in ("provider_ping", "provider_models"):
            if result is None:
                st.session_state.provider_notice = (
                    "تعذّر فحص المزود؛ تحقق من الاتصال والإعدادات."
                )
            elif kind == "provider_ping":
                st.session_state.provider_notice = "تم الاتصال بالمزود."
            else:
                provider_name = job["metadata"]["provider"]
                provider = st.session_state.providers.get(provider_name)
                if provider is not None and result:
                    provider["models"] = result
                    try:
                        save_provider(OWNER, provider_name, provider)
                        st.session_state.provider_notice = (
                            f"تم جلب {len(result)} نموذجاً."
                        )
                    except sqlite3.Error:
                        st.session_state.provider_notice = (
                            "جُلبت النماذج لكن تعذّر حفظها في قاعدة البيانات."
                        )
                else:
                    st.session_state.provider_notice = (
                        "لم تُرجع الخدمة نماذج، أو أُزيل المزود."
                    )
        elif kind == "queue":
            st.session_state.queue_notice = (
                f"تمت معالجة {result} عنصراً."
                if result is not None
                else "تعذّرت مزامنة قائمة الانتظار؛ تحقق من قاعدة البيانات والاتصال."
            )
    if changed:
        st.rerun()


# =====================================================================================
# 7) التصدير
# =====================================================================================
# https://python-docx.readthedocs.io/en/latest/user/quickstart.html
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


# https://docs.reportlab.com/reportlab/userguide/ch2_graphics/#fonts
# https://docs.python.org/3/library/textwrap.html#textwrap.wrap
def generate_pdf(text: str) -> bytes | None:
    # Built-in Helvetica cannot faithfully render Arabic or other non-ASCII text.
    if not text.isascii():
        return None
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
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
        for part in textwrap.wrap(line, width=90, replace_whitespace=False) or [""]:
            if y < 45:
                c.showPage()
                y = height - 45
                c.setFont("Helvetica", 9)
            c.drawString(40, y, part)
            y -= 13
    c.save()
    return bio.getvalue()


# https://docs.streamlit.io/develop/api-reference/widgets/st.download_button
def download_row(text: str, key_suffix: str, base_name: str = "تقرير_إبيغرافي") -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "📄 Word (.docx)",
            data=generate_docx(text),
            file_name=f"{base_name}_{stamp}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch",
            key=f"docx_{key_suffix}",
        )
    with c2:
        st.download_button(
            "📝 Markdown (.md)",
            data=text.encode("utf-8"),
            file_name=f"{base_name}_{stamp}.md",
            mime="text/markdown",
            width="stretch",
            key=f"md_{key_suffix}",
        )
    with c3:
        pdf = generate_pdf(text)
        if pdf:
            st.download_button(
                "📑 PDF (.pdf)",
                data=pdf,
                file_name=f"{base_name}_{stamp}.pdf",
                mime="application/pdf",
                width="stretch",
                key=f"pdf_{key_suffix}",
            )
        else:
            st.caption(
                "PDF غير متاح للنصوص غير اللاتينية أو عند غياب reportlab؛ استخدم Word أو Markdown."
            )


# =====================================================================================
# 8) نافذة رفع النقش (Dialog)
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
def set_pending_image(data: bytes, name: str, mime: str) -> None:
    st.session_state.pending_image = {
        "bytes": data,
        "name": name or "inscription.jpg",
        "mime": mime or "image/jpeg",
        "size": len(data),
    }


# https://docs.streamlit.io/develop/api-reference/execution-flow/st.dialog
@st.dialog("🖼️ نافذة رفع صورة النقش", width="large", icon="🖼️")
def upload_inscription_dialog() -> None:
    st.caption(
        "ارفع صورة واضحة للنقش أو التقطها بالكاميرا. تُعالج داخل جلسة التطبيق، ولا تُرسل إلى مزود خارجي إلا عند تشغيل البحث أو التحليل؛ ويمكن حفظها في مخزن الجلسة الميداني."
    )
    tab_file, tab_cam = st.tabs(["📁 رفع ملف", "📷 التقاط بالكاميرا"])
    with tab_file:
        up = st.file_uploader(
            "صورة النقش", type=["png", "jpg", "jpeg", "webp"], key="dlg_file_upload"
        )
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
        st.image(
            st.session_state.pending_image["bytes"],
            caption=f"الصورة المثبتة حالياً: {st.session_state.pending_image['name']}",
            width=260,
        )
        if st.button("🗑️ إزالة الصورة المثبتة", width="stretch"):
            st.session_state.pending_image = None
            st.rerun()


# https://docs.streamlit.io/develop/api-reference/widgets/st.button
def upload_icon_button(key: str, label: str = "رفع نقش") -> None:
    """زر أيقوني يفتح نافذة الرفع."""
    if st.button(f"🖼️ {label}", key=key, help="فتح نافذة رفع صورة النقش"):
        upload_inscription_dialog()


# https://docs.streamlit.io/develop/api-reference/media/st.image
def attachment_status() -> None:
    img = st.session_state.pending_image
    if img:
        c1, c2 = st.columns([1, 3], vertical_alignment="center")
        with c1:
            st.image(img["bytes"], width=96)
        with c2:
            st.markdown(
                f"<div class='kv'><span class='pill pill-ok'>مرفق</span> "
                f"<b>{html.escape(img['name'])}</b><br>{bytes_to_kb(img['size'])} · سيُرسل مع الطلب التالي</div>",
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
# 9) CSS الديناميكي (يدعم الوضع العادي والمظهر الميداني الداكن)
# =====================================================================================
# https://developer.mozilla.org/en-US/docs/Web/CSS
def get_css(field_dark: bool) -> str:
    """نظام تصميم موحّد: رمل دافئ، نيلي ملكي، وبرونز أثري؛ مع وضع ميداني عالي التباين."""
    if field_dark:
        bg, panel, ink, muted, line = (
            "#111827",
            "#1f2937",
            "#f8fafc",
            "#cbd5e1",
            "#475569",
        )
        accent, gold, sidebar = "#a9b4e5", "#e2bd72", "#0b1220"
    else:
        bg, panel, ink, muted, line = (
            "#f4efe4",
            "#fffdf8",
            "#20283b",
            "#667085",
            "#e4dac7",
        )
        accent, gold, sidebar = "#23365d", "#a77b38", "#1d2d4e"
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@400;500;600;700&family=Noto+Naskh+Arabic:wght@400;600;700&display=swap');
:root {{ --sand:{bg}; --panel:{panel}; --ink:{ink}; --muted:{muted}; --line:{line}; --navy:#1d2d4e; --gold:{gold}; --accent:{accent}; }}
html, body, [class*="css"] {{ font-family:'Noto Sans Arabic','Segoe UI',Tahoma,sans-serif; }}
.stApp {{ background:radial-gradient(ellipse at 90% 0%, {gold}12, transparent 34%), {bg}; color:{ink}; }}
.block-container {{ max-width:1320px; padding:1.4rem 2rem 3rem; direction:rtl; }}
[data-testid="stMarkdownContainer"], p, h1, h2, h3, h4, li {{ text-align:right; }}
.hero {{ background:linear-gradient(125deg,#1d2d4e 0%,#2d426c 64%,#4b526b 100%); color:#fff; border:1px solid #bd9a5b66; border-radius:22px; padding:25px 30px; margin-bottom:15px; box-shadow:0 16px 38px -25px #17233fcc; position:relative; overflow:hidden; }}
.hero:after {{ content:'𐩣'; position:absolute; left:24px; top:-30px; font-size:8rem; color:#ffffff0c; font-family:'Noto Naskh Arabic',serif; }}
.hero h1 {{ margin:0 0 3px; color:white; font-size:1.38rem; line-height:1.7; }}
.hero p {{ margin:0; color:#e6dfd1; font-size:.83rem; }}
.hero .chips {{ display:flex; gap:7px; flex-wrap:wrap; margin-top:13px; }}
.chip {{ border:1px solid #ffffff3a; background:#ffffff12; border-radius:999px; color:#fff; padding:4px 11px; font-size:.7rem; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background:{panel} !important; border:1px solid {line} !important; border-radius:17px !important; box-shadow:0 8px 24px -21px #101828aa; }}
.sec-title {{ color:{accent}; font-weight:700; font-size:1.02rem; margin:.1rem 0 .25rem; }}
.sec-sub {{ color:{muted}; font-size:.81rem; line-height:1.8; margin:0 0 .75rem; }}
.kv {{ color:{muted}; font-size:.8rem; line-height:1.8; }}
.stButton>button, .stDownloadButton>button {{ border-radius:11px !important; min-height:2.55rem; font-weight:650 !important; border:1px solid {line} !important; transition:all .16s ease; }}
.stButton>button[kind="primary"], .stDownloadButton>button[kind="primary"] {{ background:#1d2d4e !important; color:white !important; border:1px solid #1d2d4e !important; box-shadow:0 8px 18px -12px #152440; }}
.stButton>button[kind="primary"]:hover {{ background:#2c426a !important; transform:translateY(-1px); }}
.stButton>button:hover, .stDownloadButton>button:hover {{ border-color:{gold} !important; transform:translateY(-1px); }}
[data-testid="stSegmentedControl"] {{ background:{panel}; border:1px solid {line}; border-radius:15px; padding:5px; box-shadow:0 6px 20px -18px #101828; }}
[data-testid="stSegmentedControl"] button {{ border-radius:11px !important; color:{ink} !important; min-height:2.8rem; font-weight:650 !important; }}
[data-testid="stSegmentedControl"] button[aria-pressed="true"] {{ background:#1d2d4e !important; color:#fff !important; }}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea, [data-baseweb="select"] {{ direction:rtl; text-align:right; border-radius:10px !important; }}
[data-testid="stChatInput"] textarea {{ direction:rtl; text-align:right; }}
[data-testid="stChatMessage"] {{ border:1px solid {line}; border-radius:14px; background:{panel}; }}
[data-testid="stMetric"] {{ background:{panel}; border:1px solid {line}; border-radius:14px; padding:13px 15px; }}
[data-testid="stMetricLabel"] {{ color:{muted} !important; }}
[data-testid="stMetricValue"] {{ color:{accent} !important; }}
[data-testid="stSidebar"] {{ background:{sidebar}; border-left:1px solid #ffffff14; }}
[data-testid="stSidebar"] * {{ color:#f4f2ed; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{ color:#f4f2ed; }}
[data-testid="stSidebar"] .stButton>button {{ background:#ffffff0d; color:#f4f2ed !important; border:1px solid #ffffff20 !important; text-align:right; }}
[data-testid="stSidebar"] .stButton>button[kind="primary"] {{ background:#b18a4b !important; color:#fff !important; border:0 !important; }}
.brand {{ display:flex; gap:10px; align-items:center; padding:8px 3px 16px; border-bottom:1px solid #ffffff22; margin-bottom:15px; }}
.brand .mark {{ display:grid; place-items:center; width:40px; height:40px; border-radius:13px; background:linear-gradient(140deg,#b18a4b,#6d603e); font-size:1.2rem; }}
.brand .t1 {{ font-weight:700; font-size:.84rem; }} .brand .t2 {{ color:#c7c8d0; font-size:.63rem; }}
.side-label {{ color:#c5b58f; font-size:.7rem; margin:14px 2px 6px; }}
.privacy-box {{ background:#ffffff0c; border:1px solid #ffffff20; border-radius:12px; padding:10px; font-size:.7rem; line-height:1.85; }}
.pill {{ display:inline-block; border-radius:99px; padding:3px 10px; border:1px solid {line}; background:{panel}; color:{ink}; font-size:.7rem; font-weight:650; }}
.pill-ok {{ color:#176b4c; background:#e7f3ec; border-color:#b8d8c3; }} .pill-warn {{ color:#805f22; background:#f5ecd8; border-color:#dfc68f; }} .pill-info {{ color:#304c79; background:#e9eef8; border-color:#c2cde0; }} .pill-off {{ color:{muted}; }}
[data-testid="stFileUploaderDropzone"] {{ direction:rtl; border:1px dashed {line}; border-radius:14px; background:{panel}; }}
code, pre {{ direction:ltr; text-align:left; }}
:focus-visible {{ outline:3px solid {gold} !important; outline-offset:2px; }}
#MainMenu, footer, [data-testid="stDecoration"] {{ visibility:hidden; }}
@media(max-width:800px) {{ .block-container {{ padding:1rem 1rem 2rem; }} .hero {{ padding:19px; }} .hero h1 {{ font-size:1.05rem; }} }}
</style>"""


# تطبيق CSS حسب الوضع الحالي
st.markdown(get_css(st.session_state.field_dark_mode), unsafe_allow_html=True)


# =====================================================================================
# 10) نافذة تأمين الجلسة (Dialog)
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/execution-flow/st.dialog
@st.dialog("🔐 تأمين الجلسة برمز مرور", icon="🔐")
def lock_session_dialog() -> None:
    st.caption(
        "أدخل رمزاً سرياً (4-8 أحرف). لا يوقف القفل الطلبات الخارجية التي بدأت بالفعل."
    )
    pin = st.text_input(
        "الرمز السري", type="password", max_chars=8, key="lock_pin_input"
    )
    pin_confirm = st.text_input(
        "تأكيد الرمز", type="password", max_chars=8, key="lock_pin_confirm"
    )

    if st.button("🔒 تفعيل التأمين", type="primary", width="stretch"):
        if not pin or len(pin) < 4:
            st.error("الرمز يجب أن يكون 4 أحرف على الأقل.")
        elif pin != pin_confirm:
            st.error("الرمزان غير متطابقين.")
        else:
            st.session_state.session_pin_hash = hash_pin(pin)
            st.session_state.session_locked = True
            st.success("تم تأمين الجلسة.")
            st.rerun()


# https://docs.streamlit.io/develop/api-reference/execution-flow/st.dialog
@st.dialog("🔓 فتح الجلسة", icon="🔓")
def unlock_session_dialog() -> None:
    st.caption("أدخل رمز المرور لعرض المفاتيح واستخدامها.")
    pin = st.text_input(
        "الرمز السري", type="password", max_chars=8, key="unlock_pin_input"
    )

    if st.button("🔓 فتح", type="primary", width="stretch"):
        if verify_pin(pin, st.session_state.session_pin_hash):
            st.session_state.session_locked = False
            st.success("تم فتح الجلسة.")
            st.rerun()
        else:
            st.error("رمز خاطئ.")


# https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
def require_unlock() -> bool:
    """التحقق من حالة القفل وعرض نافذة الفتح إذا لزم."""
    if st.session_state.session_locked:
        unlock_session_dialog()
        return False
    return True


# =====================================================================================
# 11) نافذة المعالج الذكي للإعداد الذاتي (Setup Wizard)
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/execution-flow/st.dialog
@st.dialog("🧙 المعالج الذكي للإعداد الذاتي", width="large", icon="🧙")
def setup_wizard_dialog() -> None:
    st.caption(
        "إعداد تلقائي بضغطة زر للأكاديميين غير التقنيين — فقط أدخل المفتاح وسنضبط الباقي."
    )

    step = st.session_state.get("wizard_step", 1)

    if step == 1:
        st.markdown("### الخطوة 1: اختر نوع المفتاح")
        provider_type = st.selectbox(
            "نوع المزود",
            ["Google Gemini (مجاني)", "OpenRouter", "SiliconFlow", "مزود مخصص"],
            key="wizard_provider_type",
        )

        if st.button("التالي ⬅", type="primary", width="stretch"):
            st.session_state.wizard_step = 2
            st.session_state.wizard_provider_type = provider_type
            st.rerun()

    elif step == 2:
        st.markdown(f"### الخطوة 2: أدخل مفتاح API")
        st.caption(f"المزود المختار: **{st.session_state.wizard_provider_type}**")

        api_key = st.text_input(
            "مفتاح API",
            type="password",
            key="wizard_api_key",
            placeholder="AIza... / sk-...",
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅ رجوع"):
                st.session_state.wizard_step = 1
                st.rerun()
        with col2:
            if st.button("🚀 إعداد تلقائي", type="primary", width="stretch"):
                if not api_key.strip():
                    st.error("أدخل المفتاح أولاً.")
                else:
                    with st.spinner("جارٍ الإعداد التلقائي..."):
                        success = auto_configure_provider(
                            st.session_state.wizard_provider_type, api_key.strip()
                        )
                    if success:
                        st.session_state.wizard_step = 3
                        st.rerun()
                    else:
                        st.error("فشل الإعداد. تحقق من المفتاح.")

    elif step == 3:
        st.markdown("### ✅ تم الإعداد بنجاح!")
        st.success("تم حفظ الإعدادات؛ لم تُتحقق صلاحية المفتاح أو توفر النماذج بعد.")

        provider_name = st.session_state.wizard_provider_type
        if provider_name in st.session_state.providers:
            models = list(
                st.session_state.providers[provider_name].get("models", {}).keys()
            )
            st.markdown(f"**النماذج المتاحة:** {len(models)}")
            for m in models[:5]:
                st.markdown(f"- `{m}`")

        if st.button("إغلاق", type="primary", width="stretch"):
            st.session_state.wizard_step = 1
            st.session_state.wizard_active = False
            st.rerun()


# https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
def auto_configure_provider(provider_type: str, api_key: str) -> bool:
    """إعداد تلقائي للمزود بناءً على النوع."""
    try:
        if provider_type == "Google Gemini (مجاني)":
            st.session_state.gemini_free_key = api_key
            if "Google Gemini (مجاني)" not in st.session_state.providers:
                st.session_state.providers["Google Gemini (مجاني)"] = DEFAULT_PROVIDERS[
                    "Google Gemini (مجاني)"
                ].copy()
                save_provider(
                    OWNER,
                    "Google Gemini (مجاني)",
                    st.session_state.providers["Google Gemini (مجاني)"],
                )
            return True

        elif provider_type == "OpenRouter":
            st.session_state.providers["OpenRouter"] = {
                "api_style": "OpenAI API",
                "url": "https://openrouter.ai/api/v1",
                "path": "/chat/completions",
                "network_opt": True,
                "models": DEFAULT_PROVIDERS["OpenRouter"]["models"].copy(),
            }
            save_provider(OWNER, "OpenRouter", st.session_state.providers["OpenRouter"])
            st.session_state.secret_keys["OpenRouter"] = api_key
            return True

        elif provider_type == "SiliconFlow":
            st.session_state.providers["SiliconFlow"] = {
                "api_style": "OpenAI API",
                "url": "https://api.siliconflow.com/v1",
                "path": "/chat/completions",
                "network_opt": True,
                "models": DEFAULT_PROVIDERS["SiliconFlow"]["models"].copy(),
            }
            save_provider(
                OWNER, "SiliconFlow", st.session_state.providers["SiliconFlow"]
            )
            st.session_state.secret_keys["SiliconFlow"] = api_key
            return True

        else:  # مزود مخصص
            st.warning(
                "اضبط عنوان المزود المخصص يدوياً من الإعدادات؛ لا يمكن استنتاجه من المفتاح."
            )
            return False

    except sqlite3.Error:
        st.error("تعذّر حفظ إعدادات المزود في قاعدة البيانات.")
        return False


# =====================================================================================
# 12) الشريط الجانبي
# =====================================================================================
with st.sidebar:
    st.markdown(
        f"""<div class="brand">
              <div class="mark">🗿</div>
              <div>
                <div class="t1">مختبر المسند الرقمي</div>
                <div class="t2">South Arabian Epigraphy Lab · v3.0</div>
              </div>
            </div>""",
        unsafe_allow_html=True,
    )

    if st.button("➕ محادثة جديدة", type="primary", width="stretch"):
        nid = new_id()
        title = f"محادثة {datetime.now().strftime('%H:%M')}"
        st.session_state.archive[nid] = {
            "title": title,
            "messages": [],
            "created_at": now_str(),
            "updated_at": now_str(),
        }
        save_chat(OWNER, nid, title, [])
        st.session_state.current_chat_id = nid
        st.session_state.last_comparison_image = None
        goto("chat")

    upload_icon_button("sb_upload_btn", "رفع نقش")

    # زر التخزين المؤقت الميداني في الشريط الجانبي
    pending_count = len(load_offline_queue(OWNER, "pending"))
    offline_label = (
        f"⏳ قائمة الانتظار الميدانية ({pending_count})"
        if pending_count > 0
        else "⏳ قائمة الانتظار الميدانية"
    )
    if st.button(offline_label, width="stretch", key="sb_offline_queue"):
        st.session_state.global_subview = "⏳ التخزين الميداني"
        goto("global")
    if st.button("📚 عرض الأرشيف الكامل", width="stretch", key="sb_open_archive"):
        st.session_state.global_subview = "📚 الأرشيف"
        goto("global")

    st.markdown(
        "<div class='side-label'>🕒 محادثاتي الأخيرة</div>", unsafe_allow_html=True
    )
    chat_query = st.text_input(
        "بحث في المحادثات",
        placeholder="🔎 فلترة العناوين…",
        label_visibility="collapsed",
        key="sb_chat_filter",
    ).strip()

    shown = 0
    for cid, cdata in list(st.session_state.archive.items()):
        title = cdata["title"]
        if chat_query and normalize_ar(chat_query) not in normalize_ar(title):
            continue
        if shown >= 25:
            break
        shown += 1
        active = cid == CURRENT_CHAT
        label = f"{'▸' if active else '💬'} {title[:32]}"
        if st.button(
            label,
            key=f"sb_chat_{cid}",
            type="primary" if active else "secondary",
            width="stretch",
        ):
            st.session_state.current_chat_id = cid
            st.session_state.last_comparison_image = None
            goto("chat")

    if shown == 0:
        st.caption("لا توجد نتائج مطابقة.")

    st.markdown(
        "<div class='side-label'>🔒 الخصوصية والأمان</div>", unsafe_allow_html=True
    )

    # زر تأمين الجلسة
    if st.session_state.session_locked:
        if st.button("🔓 فتح الجلسة", width="stretch", key="sb_unlock"):
            unlock_session_dialog()
    else:
        if st.button("🔒 تأمين الجلسة", width="stretch", key="sb_lock"):
            lock_session_dialog()

    st.markdown(
        """<div class="privacy-box">
             جلسة معزولة تماماً: مفاتيح API وسجل المحادثات والصورة المرفقة
             مرتبطة بهذا المتصفح/الجلسة فقط، ولا تُكتب في الرابط ولا تظهر لمستخدم آخر.
             تبقى المفاتيح في ذاكرة جلسة التطبيق ولا تدخل قاعدة البيانات؛ قد يستمر الاتصال فترة قصيرة بعد إغلاق التبويب حتى ينتهي اتصال Streamlit.
           </div>""",
        unsafe_allow_html=True,
    )
    with st.expander("كيف تُحمى بياناتي؟"):
        st.markdown(
            "- هوية عشوائية مؤقتة لكل جلسة متصفح (لا تسجيل دخول، لا Cookie تتبّع).\n"
            "- مفاتيح API في `session_state` فقط — **لا** في قاعدة البيانات و**لا** في الرابط.\n"
            "- المحادثات تُخزَّن موسومة بهويتك المؤقتة؛ لا يستطيع غيرك قراءتها.\n"
            "- أي معامل حساس في الرابط (`?key=`، `?chat_id=`) يُحذف تلقائياً عند التحميل.\n"
            "- زر الحذف النهائي أدناه يمحو كل صفوفك.\n"
            "- **تأمين الجلسة**: يتطلب رمز مرور لعرض المفاتيح أو استخدامها."
        )

    if st.button("🗑️ حذف بياناتي نهائياً", key="sb_wipe"):
        st.session_state.confirm_wipe = True
    if st.session_state.confirm_wipe:
        st.warning(
            "سيتم حذف محادثاتك وفهرسك وإعدادات مزوديك (المفاتيح تُحذف تلقائياً). لا يمكن التراجع."
        )
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button(
                "نعم، احذف",
                type="primary",
                key="sb_wipe_yes",
                disabled=bool(st.session_state.get("background_jobs")),
            ):
                delete_all_user_data(OWNER)
                for k in ("archive", "current_chat_id", "providers", "search_result"):
                    st.session_state.pop(k, None)
                st.session_state.secret_keys = {}
                st.session_state.gemini_free_key = ""
                st.session_state.clear_secret_widgets = True
                st.session_state.mock_mode = True
                st.session_state.pending_image = None
                st.session_state.last_comparison_image = None
                st.session_state.confirm_wipe = False
                st.session_state.session_locked = False
                st.session_state.session_pin_hash = None
                st.rerun()
        if st.session_state.get("background_jobs"):
            st.info(
                "انتظر انتهاء المهام الخارجية قبل حذف بيانات الجلسة؛ لا يمكن إلغاء طلب أُرسل بالفعل."
            )
        with cc2:
            if st.button("إلغاء", key="sb_wipe_no"):
                st.session_state.confirm_wipe = False
                st.rerun()


# =====================================================================================
# 13) الترويسة والتنقل الرئيسي — أربع مساحات عمل منفصلة
# =====================================================================================
legacy_views = {"search": "global", "archive": "global", "offline": "global"}
if st.session_state.view in legacy_views:
    old_view = st.session_state.view
    st.session_state.view = legacy_views[old_view]
    if old_view == "offline":
        st.session_state.global_subview = "⏳ التخزين الميداني"
    elif old_view == "archive":
        st.session_state.global_subview = "📚 الأرشيف"

header_title, header_controls = st.columns([4.4, 1.35], vertical_alignment="center")
with header_title:
    st.markdown(
        f"""<div class="hero">
          <h1>مختبر المسند الرقمي</h1>
          <p>{APP_SUBTITLE}</p>
          <div class="chips">
            <span class="chip">𐩣 دراسات جنوب الجزيرة</span>
            <span class="chip">🗂️ فهرسة محلية</span>
            <span class="chip">🧪 محاكاة آمنة عند غياب المفتاح</span>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )
with header_controls:
    dark_mode = st.session_state.field_dark_mode
    mode_label = "☀️ المظهر العادي" if dark_mode else "🌙 الوضع الداكن الميداني"
    if st.button(mode_label, width="stretch", key="toggle_dark_mode"):
        st.session_state.field_dark_mode = not dark_mode
        st.rerun()
    lock_label = (
        "🔒 الجلسة مؤمّنة" if st.session_state.session_locked else "🔓 تأمين المفاتيح"
    )
    if st.button(lock_label, width="stretch", key="head_lock"):
        (
            unlock_session_dialog()
            if st.session_state.session_locked
            else lock_session_dialog()
        )
    has_active_key = bool(
        st.session_state.gemini_free_key or any(st.session_state.secret_keys.values())
    )
    st.caption(
        "🧪 محاكاة بلا اتصال خارجي"
        if st.session_state.mock_mode
        else ("🔑 مفتاح في الجلسة" if has_active_key else "⚠️ لا يوجد مفتاح")
    )

VIEWS = {
    "🗿 عين المسند": "eye",
    "📜 المساعد الإبيغرافي": "chat",
    "🌐 البوابة العالمية": "global",
    "⚙️ الإعدادات المتقدمة": "settings",
}
VIEW_KEYS = list(VIEWS.values())
VIEW_LABELS = list(VIEWS.keys())
if st.session_state.view not in VIEW_KEYS:
    st.session_state.view = "eye"
current_label = VIEW_LABELS[VIEW_KEYS.index(st.session_state.view)]
if st.session_state.get("nav_top") not in VIEW_LABELS:
    st.session_state.nav_top = current_label
choice = st.segmented_control(
    "مساحات العمل الرئيسية",
    VIEW_LABELS,
    label_visibility="collapsed",
    key="nav_top",
    width="stretch",
)
if choice and VIEWS[choice] != st.session_state.view:
    goto(VIEWS[choice])
VIEW = st.session_state.view
st.write("")


# =====================================================================================
# 13.1) عين المسند — التقاط، رفع، ومعاينة الصورة
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/layout/st.columns
def render_eye_view() -> None:
    st.markdown("<div class='sec-title'>🗿 عين المسند</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sec-sub'>مساحة ميدانية هادئة لتوثيق النقش قبل قراءته. التقط صورة أو ارفعها، ثم انتقل مباشرة إلى التحليل المقارن.</div>",
        unsafe_allow_html=True,
    )
    capture_col, preview_col = st.columns([1, 1.45], gap="large")
    with capture_col:
        with st.container(border=True):
            st.markdown("### 📷 التقاط أو رفع")
            st.caption(
                "استخدم صورة واضحة، مستقيمة قدر الإمكان، مع إضاءة جانبية لطيفة لإبراز الحفر."
            )
            upload = st.file_uploader(
                "رفع صورة من الجهاز",
                type=["png", "jpg", "jpeg", "webp"],
                key="eye_file_upload",
            )
            camera = st.camera_input("التقاط صورة ميدانية", key="eye_camera_capture")
            source = camera or upload
            if source is not None:
                raw = source.getvalue()
                name = getattr(source, "name", None) or "camera.jpg"
                mime = getattr(source, "type", None) or "image/jpeg"
                current = st.session_state.pending_image
                if (
                    not current
                    or current.get("name") != name
                    or current.get("size") != len(raw)
                ):
                    set_pending_image(raw, name, mime)
            if st.session_state.pending_image:
                if st.button("إزالة الصورة المثبتة", key="eye_remove_image"):
                    st.session_state.pending_image = None
                    st.rerun()
    with preview_col:
        with st.container(border=True):
            st.markdown("### 🔎 معاينة ميدانية")
            image = st.session_state.pending_image
            if image:
                st.image(
                    image["bytes"],
                    caption=f"{image['name']} · {bytes_to_kb(image['size'])}",
                    width="stretch",
                )
                st.success(
                    "الصورة جاهزة للمراجعة أو التحليل؛ لن تُرسل إلى مزود خارجي إلا عند طلب ذلك."
                )
            else:
                st.markdown(
                    "<div style='min-height:245px;display:grid;place-items:center;text-align:center;border:1px dashed var(--line);border-radius:16px;padding:24px'>"
                    "<div><div style='font-size:3.5rem;color:var(--gold)'>𐩣</div>"
                    "<strong>مساحة معاينة النقش</strong><br><span style='color:var(--muted)'>ستظهر الصورة هنا بعد التقاطها أو رفعها</span></div></div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "دليل سريع: صورة كاملة ← تفاصيل مقربة ← قراءة حرفية ← ترجمة ومراجعة مرجعية."
                )
            st.write("")
            if st.button(
                "📜 فتح المساعد والتحليل الفوري",
                type="primary",
                width="stretch",
                key="eye_go_assistant",
            ):
                goto("chat")
    st.write("")
    m1, m2, m3 = st.columns(3)
    m1.metric("خطوة التوثيق", "01 · الصورة", "جاهزة للمراجعة")
    m2.metric("التحليل", "02 · قراءة", "عند الطلب")
    m3.metric("المخرجات", "03 · مقارنة", "نص وصورة")
    if st.session_state.mock_mode:
        st.info(
            "🧪 وضع المحاكاة مفعّل لعدم وجود مفتاح API. يمكنك استكشاف الواجهة وطلب استجابة تعليمية تجريبية دون إرسال ملفاتك للخارج."
        )


# https://docs.streamlit.io/develop/api-reference/text/st.markdown
def render_global_portal_intro() -> None:
    st.markdown(
        "<div class='sec-title'>🌐 البوابة العالمية للنقوش والمدونات</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='sec-sub'>مداخل مرجعية خارجية للبحث في النقوش والكتالوجات الأكاديمية؛ حالة الاتصال تُفحص عند الطلب فقط.</div>",
        unsafe_allow_html=True,
    )
    catalog_data = [
        (
            "DASI",
            "Digital Archive for the Study of pre-Islamic Arabian Inscriptions",
            "https://dasi.cnr.it/",
            "مدونة رقمية للنقوش العربية القديمة",
        ),
        (
            "CSAI",
            "Corpus of South Arabian Inscriptions",
            "https://csai.humnet.unipi.it/",
            "فهرس ودراسات نقوش جنوب الجزيرة",
        ),
        (
            "Google Scholar",
            "Academic literature search",
            "https://scholar.google.com/",
            "مقالات ودراسات علمية",
        ),
    ]
    cols = st.columns(3, gap="medium")
    for col, (name, subtitle, url, description) in zip(cols, catalog_data):
        with col:
            ping = st.session_state.global_catalog_pings.get(name)
            light = "🟢" if ping is True else ("🔴" if ping is False else "🟡")
            with st.container(border=True):
                st.markdown(f"### {light} {name}")
                st.caption(subtitle)
                st.markdown(description)
                st.markdown(f"[فتح المصدر ↗]({url})")
                state = (
                    "متاح عند آخر فحص"
                    if ping is True
                    else (
                        "تعذّر الوصول في آخر فحص" if ping is False else "لم يُفحص بعد"
                    )
                )
                st.caption(state)
    opts = st.columns([1, 2.7], vertical_alignment="center")
    with opts[0]:
        st.selectbox(
            "لغة الاستعلام",
            ["العربية", "English", "Français", "Italiano"],
            key="global_search_language",
        )
    with opts[1]:
        if st.button(
            "📡 فحص اتصال المصادر",
            key="catalog_ping",
            help="فحص HTTP سريع من خادم التطبيق؛ لا تُرسل بيانات البحث",
        ):
            start_background_job(
                "catalog",
                check_catalogs,
                [(name, url) for name, _, url, _ in catalog_data],
            )
            st.rerun()
        if "catalog" in st.session_state.get("background_jobs", {}):
            st.info("يجري فحص المصادر في الخلفية.")


# https://docs.streamlit.io/develop/api-reference/widgets/st.segmented_control
def render_global_view() -> None:
    subviews = ["🌐 البحث والمدونات", "⏳ التخزين الميداني", "📚 الأرشيف"]
    if st.session_state.get("global_subview") not in subviews:
        st.session_state.global_subview = subviews[0]
    selected = st.segmented_control(
        "أدوات البوابة", subviews, key="global_subview", width="stretch"
    )
    if selected == subviews[1]:
        render_offline_view()
    elif selected == subviews[2]:
        render_archive_view()
    else:
        render_global_portal_intro()
        st.divider()
        render_search_view()


# =====================================================================================
# 14) عرض البحث عن النقش (بدون مفتاح مزود + Gemini المجاني)
# =====================================================================================
# https://docs.python.org/3/library/functions.html#all
# مطابقة محلية تقريبية للاستكشاف، وليست معياراً علمياً للتعرّف على النقوش.
def matches_query(query: str, haystack: str) -> bool:
    if not query or query in haystack:
        return True
    tokens = [token for token in query.split() if len(token) > 1]
    return bool(tokens) and all(token in haystack for token in tokens)


# https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
def run_local_search(query: str, region_filter: str, corpus_filter: str) -> dict:
    q = normalize_ar(query)
    rows = load_corpus(OWNER)
    hits = []
    for r in rows:
        if r["owner"] == SHARED_OWNER:
            r = dict(r)
            r["scope"] = "مدخل استرشادي مدمج غير متحقق"
        else:
            r = dict(r)
            r["scope"] = "فهرس المستخدم"
        if (
            corpus_filter != "الكل"
            and corpus_filter.lower() not in (r["corpus"] or "").lower()
        ):
            continue
        if region_filter.strip() and normalize_ar(region_filter) not in normalize_ar(
            r["region"] or ""
        ):
            continue
        haystack = normalize_ar(
            " ".join(
                [
                    r.get("code", ""),
                    r.get("corpus", ""),
                    r.get("script", ""),
                    r.get("region", ""),
                    r.get("century", ""),
                    r.get("text", ""),
                    r.get("note", ""),
                ]
            )
        )
        if not matches_query(q, haystack):
            continue
        hits.append(r)

    archive_hits = []
    if q:
        for cid, cdata in st.session_state.archive.items():
            blob = normalize_ar(
                cdata["title"]
                + " "
                + " ".join(m.get("content", "") for m in cdata["messages"])
            )
            if matches_query(q, blob):
                archive_hits.append(
                    {
                        "chat_id": cid,
                        "title": cdata["title"],
                        "updated_at": cdata.get("updated_at", ""),
                    }
                )
    return {"query": query, "corpus": hits, "archive": archive_hits}


# https://docs.streamlit.io/develop/api-reference/widgets/st.text_area
def render_search_view() -> None:
    st.markdown(
        "<div class='sec-title'>🔎 بوابة البحث عن النقش</div>", unsafe_allow_html=True
    )
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
                horizontal=True,
                key="search_engine",
            )
            query = st.text_area(
                "رمز النقش أو كلمة مفتاحية أو نص النقش",
                placeholder="مثال: CIH 352 — أو — bʿl — أو — «نقش سبئي من مأرب»",
                height=110,
                key="search_query",
            )
            f1, f2 = st.columns(2)
            with f1:
                corpus_filter = st.selectbox(
                    "المجموعة / المدونة",
                    ["الكل", "CIH", "RES", "Ja", "CSAI", "Ry", "Ir", "Gl"],
                    key="search_corpus_filter",
                )
            with f2:
                region_filter = st.text_input(
                    "الموقع/المنطقة (اختياري)",
                    key="search_region_filter",
                    placeholder="مأرب، صرواح، ظفار…",
                )

            st.markdown("**مرفق الصورة (اختياري)**")
            attachment_status()

            # أزرار الإجراءات
            a1, a2, a3 = st.columns(3)
            with a1:
                upload_icon_button("search_upload_btn", "فتح نافذة الرفع")
            with a2:
                run = st.button(
                    "🚀 ابدأ البحث",
                    type="primary",
                    width="stretch",
                    key="search_run",
                    disabled="search" in st.session_state.get("background_jobs", {}),
                )
            with a3:
                # زر التخزين المؤقت للميدان
                if st.button(
                    "⏳ حفظ للميدان",
                    width="stretch",
                    key="search_offline_cache",
                    help="حفظ الطلب في قائمة الانتظار المؤقتة للمعالجة لاحقاً عند توفر الاتصال",
                    disabled=not query.strip() and not st.session_state.pending_image,
                ):
                    qid = enqueue_offline(
                        OWNER, "search", query, st.session_state.pending_image
                    )
                    st.success(f"تم حفظ الطلب في قائمة الانتظار ({qid[:8]}).")
                    time.sleep(0.5)
                    st.rerun()

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
                if st.session_state.session_locked:
                    st.warning(
                        "الجلسة مقفلة. افتحها قبل إجراء طلبات خارجية، أو استخدم البحث المحلي."
                    )
                elif not key:
                    st.error(
                        "أضف مفتاح Gemini المجاني من اللوحة الجانبية للاستعلام (يُحفظ في جلستك فقط)."
                    )
                else:
                    prompt = (
                        f"{SYSTEM_PROMPT_LOOKUP}\n\n"
                        f"---\n**الاستعلام:** {query or '[صورة نقش مرفقة]'}\n"
                        f"**فلتر المدونة:** {corpus_filter} — **فلتر الموقع:** {region_filter or 'غير محدد'}\n"
                        f"**لغة الإجابة المطلوبة:** {st.session_state.get('global_search_language', 'العربية')}\n"
                    )
                    start_background_job(
                        "search",
                        gemini_generate,
                        key,
                        st.session_state.get("gemini_model_choice", GEMINI_MODELS[0]),
                        prompt,
                        st.session_state.pending_image,
                        query=query,
                    )
                    st.session_state.search_result = None
                    st.rerun()

        if "search" in st.session_state.get("background_jobs", {}):
            st.info("جارٍ البحث في الخلفية؛ يمكنك مواصلة استخدام التطبيق.")

    with col_side:
        with st.container(border=True):
            st.markdown(
                "<div class='sec-title'>🔑 مفتاح Gemini المجاني</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div class='sec-sub'>مفتاح من حسابك المجاني في Google AI Studio — منفصل تماماً عن مزودي التحليل.</div>",
                unsafe_allow_html=True,
            )

            # التحقق من القفل قبل عرض حقل المفتاح
            if st.session_state.session_locked:
                st.markdown(
                    "<span class='pill pill-warn'>🔒 الجلسة مقفلة</span>",
                    unsafe_allow_html=True,
                )
                if st.button("🔓 فتح لعرض المفاتيح", width="stretch", key="gem_unlock"):
                    unlock_session_dialog()
            else:
                if st.session_state.gemini_free_key:
                    masked = (
                        st.session_state.gemini_free_key[:6]
                        + "…"
                        + st.session_state.gemini_free_key[-4:]
                    )
                    st.markdown(
                        f"<span class='pill pill-ok'>مضبوط</span> <code>{html.escape(masked)}</code>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "إزالة المفتاح من الجلسة", width="stretch", key="gem_clear"
                    ):
                        st.session_state.gemini_free_key = ""
                        st.session_state.clear_secret_widgets = True
                        st.rerun()
                else:
                    new_key = st.text_input(
                        "مفتاح Gemini",
                        type="password",
                        key="gem_key_input",
                        placeholder="AIza…",
                        label_visibility="collapsed",
                    )
                    if st.button(
                        "حفظ في الجلسة فقط",
                        type="primary",
                        width="stretch",
                        key="gem_save",
                    ):
                        if new_key.strip():
                            st.session_state.gemini_free_key = new_key.strip()
                            st.success(
                                "تم الحفظ في الجلسة (لن يُكتب في قاعدة البيانات)."
                            )
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.warning("أدخل المفتاح أولاً.")
                    st.caption("الحصول على مفتاح مجاني: aistudio.google.com/app/apikey")

            if st.session_state.get("gem_model_select") not in GEMINI_MODELS:
                st.session_state.gem_model_select = GEMINI_MODELS[0]
            st.session_state.gemini_model_choice = st.selectbox(
                "نموذج Gemini",
                GEMINI_MODELS,
                key="gem_model_select",
            )
            st.divider()
            st.markdown(
                "<div class='kv'>🔒 <b>خصوصية:</b> يرسل التطبيق المفتاح من جلسة الخادم إلى Google عند تنفيذ البحث فقط، "
                "ولا يُخزَّن في قاعدة البيانات.</div>",
                unsafe_allow_html=True,
            )

    # ---------- النتائج ----------
    res = st.session_state.search_result
    st.write("")
    with st.container(border=True):
        st.markdown("<div class='sec-title'>📑 النتائج</div>", unsafe_allow_html=True)
        if not res:
            st.markdown(
                "<div class='kv'>لا توجد نتائج بعد — ابدأ بحثاً من اللوحة أعلاه.</div>",
                unsafe_allow_html=True,
            )
        elif res["mode"] == "local":
            data = res["data"]
            st.markdown(
                f"<div class='kv'>استعلام: <b>{html.escape(data['query'] or '—')}</b> · "
                f"مطابقات الفهرس: <b>{len(data['corpus'])}</b> · "
                f"مطابقات أرشيفي: <b>{len(data['archive'])}</b> · {fmt_dt(res['at'])}</div>",
                unsafe_allow_html=True,
            )
            if data["corpus"]:
                df = pd.DataFrame(data["corpus"])[
                    ["code", "corpus", "script", "region", "century", "scope"]
                ]
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
                    st.markdown(
                        f"- [{h['title']}](?) · آخر تحديث {fmt_dt(h['updated_at'])}"
                    )
            if not data["corpus"] and not data["archive"]:
                st.info(
                    "لا مطابقات محلية. جرّب صياغة أخرى، أو شغّل «بحث وتحليل بـ Gemini المجاني»."
                )
        elif res["mode"] == "gemini":
            st.markdown(
                "<span class='pill pill-info'>مسودة مولدة آلياً؛ تتطلب تحققاً مستقلاً</span>",
                unsafe_allow_html=True,
            )
            st.markdown(res["text"])
            download_row(res["text"], "search_gemini", "بطاقة_تعريف_نقش")
            if st.button("💾 حفظ النتيجة في الأرشيف", key="save_search_result"):
                nid = new_id()
                title = (res.get("query") or "نتيجة بحث")[:40]
                msgs = [{"role": "assistant", "content": res["text"]}]
                st.session_state.archive[nid] = {
                    "title": title,
                    "messages": msgs,
                    "created_at": now_str(),
                    "updated_at": now_str(),
                }
                save_chat(OWNER, nid, title, msgs)
                st.success("تم الحفظ في الأرشيف.")
        else:
            st.error(f"تعذّر إتمام البحث: {res.get('error')}")

    # ---------- إدارة الفهرس ----------
    with st.expander("🗂️ إدارة فهرس النقوش الخاص بي (يبني البحث المحلي بدون مفتاح)"):
        st.caption(
            "أضف أو عدّل مداخل فهرسك: الرمز، المدونة، الخط، الموقع، الحقبة، النص، ملاحظات. المداخل المدمجة استرشادية غير متحققة وللقراءة فقط؛ راجع مصادرها قبل الاستشهاد بها."
        )
        rows = [r for r in load_corpus(OWNER) if r["owner"] == OWNER]
        if rows:
            df = pd.DataFrame(rows)[SEED_COLUMNS]
        else:
            df = pd.DataFrame(columns=SEED_COLUMNS)
        edited = st.data_editor(
            df,
            num_rows="dynamic",
            width="stretch",
            key="corpus_editor",
            column_config={
                "entry_id": st.column_config.TextColumn(
                    "ID", disabled=True, width="small"
                ),
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
            if st.button(
                "💾 حفظ/تحديث الفهرس",
                type="primary",
                width="stretch",
                key="corpus_save",
            ):
                n = upsert_corpus_rows(OWNER, edited)
                st.success(f"تم حفظ {n} مدخلاً في فهرسك الخاص.")
                time.sleep(0.3)
                st.rerun()
        with e2:
            if rows:
                to_del = st.selectbox(
                    "حذف مدخل",
                    ["—"] + [f"{r['code']}" for r in rows],
                    key="corpus_del_select",
                )
                if to_del != "—":
                    if st.button(
                        "🗑️ حذف المدخل", width="stretch", key="corpus_del_btn"
                    ):
                        target = next(r for r in rows if r["code"] == to_del)
                        delete_corpus_entry(OWNER, target["entry_id"])
                        st.success("تم الحذف.")
                        time.sleep(0.2)
                        st.rerun()


# =====================================================================================
# 15) عرض المساعد الإبيغرافي (مزود + نموذج + مقارنة حية)
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
def provider_key(name: str) -> str:
    if name == "Google Gemini (مجاني)":
        return st.session_state.gemini_free_key or st.session_state.secret_keys.get(
            name, ""
        )
    return st.session_state.secret_keys.get(name, "")


# https://docs.streamlit.io/develop/api-reference/chat/st.chat_input
def render_chat_view() -> None:
    prov_names = list(PROVIDERS.keys())
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns(
            [1.2, 1.6, 0.9, 0.9, 1], vertical_alignment="bottom"
        )
        with c1:
            sel_prov = st.selectbox("🔌 المزود", prov_names, key="chat_provider_select")
        prov = PROVIDERS[sel_prov]
        models = list(prov.get("models", {}).keys())
        with c2:
            if models:
                sel_model = st.selectbox(
                    "🤖 النموذج",
                    models,
                    key="chat_model_select",
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
                f"<span class='pill pill-info'>📂 {html.escape(ARCHIVE[CURRENT_CHAT]['title'][:18])}</span></div>",
                unsafe_allow_html=True,
            )
        with c5:
            # زر تفعيل مقارنة النص الحي
            split_enabled = st.session_state.split_view_enabled
            split_label = "🔀 إخفاء المقارنة" if split_enabled else "🔀 مقارنة حية"
            if st.button(
                split_label,
                width="stretch",
                key="toggle_split_view",
                help="عرض صورة النقش والنص المترجم جنباً إلى جنب",
            ):
                st.session_state.split_view_enabled = not split_enabled
                st.rerun()

        # حقل المفتاح مع التحقق من القفل
        if not cur_key:
            if st.session_state.session_locked:
                st.markdown(
                    "<span class='pill pill-warn'>🔒 الجلسة مقفلة — افتحها لإضافة المفتاح</span>",
                    unsafe_allow_html=True,
                )
                if st.button("🔓 فتح الجلسة", key="chat_unlock"):
                    unlock_session_dialog()
            else:
                k = st.text_input(
                    "مفتاح API لهذا المزود (يبقى في جلستك فقط)",
                    type="password",
                    key=f"chat_key_{sel_prov}",
                    placeholder="sk-… / AIza…",
                )
                kc1, kc2 = st.columns([1, 3])
                with kc1:
                    if st.button(
                        "حفظ المفتاح",
                        type="primary",
                        width="stretch",
                        key=f"chat_key_save_{sel_prov}",
                    ):
                        if k.strip():
                            st.session_state.secret_keys[sel_prov] = k.strip()
                            st.rerun()
                        else:
                            st.warning("أدخل المفتاح.")
                with kc2:
                    st.caption(
                        "يُستخدم هذا الاتصال للتحليل فقط. للمفاتيح المزعجة استخدم مفتاح Gemini المجاني في تبويب البحث."
                    )

    mock_mode = st.toggle(
        "🧪 وضع المحاكاة الآمن — لا يرسل بيانات إلى أي مزود",
        key="mock_mode",
        help="يخص المساعد الإبيغرافي فقط؛ البحث والمزامنة الخارجية مستقلان عنه. النتائج توضيحية وليست تحليلاً أثرياً فعلياً.",
    )
    if mock_mode:
        st.info(
            "أنت في وضع محاكاة المساعد: لن ترسل طلبات المحادثة بيانات لخدمة خارجية. البحث والمزامنة الخارجيان مستقلان عنه.",
            icon="🧪",
        )
    elif st.session_state.session_locked:
        st.warning("الجلسة مقفلة؛ افتحها قبل استخدام مفاتيح API.", icon="🔒")
    else:
        st.caption(
            "مخرجات النموذج مسودات غير متحققة، وليست بديلاً عن مراجعة المصادر والمتخصصين."
        )

    st.write("")

    # ---------- وضع المقارنة الحية ----------
    comparison_image = (
        st.session_state.pending_image or st.session_state.last_comparison_image
    )
    if st.session_state.split_view_enabled and comparison_image:
        st.markdown(
            "<div class='sec-title'>🔀 مقارنة النص الحي (Split-View)</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='sec-sub'>موازنة رسم الحرف الحجري بالنتيجة البرمجية فوراً</div>",
            unsafe_allow_html=True,
        )

        split_col1, split_col2 = st.columns(2, gap="medium")
        with split_col1:
            with st.container(border=True):
                st.markdown("**🖼️ صورة النقش الأصلية**")
                st.image(comparison_image["bytes"], width="stretch")
                st.caption(
                    f"{comparison_image['name']} · {bytes_to_kb(comparison_image.get('size', len(comparison_image.get('bytes', b''))))}"
                )
        with split_col2:
            with st.container(border=True):
                st.markdown("**📜 النص المنسوخ والمترجم**")
                # عرض آخر رد مساعد أو رسالة للمقارنة
                assistant_msgs = [m for m in MESSAGES if m["role"] == "assistant"]
                if assistant_msgs:
                    st.markdown(assistant_msgs[-1]["content"])
                else:
                    st.info("أرسل طلباً أولاً لعرض النص المترجم هنا.")
        st.divider()

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

        # زر حفظ للميدان بجانب حقل الإدخال
        cc1, cc2 = st.columns([1, 4])
        with cc1:
            if st.button(
                "⏳ حفظ للميدان",
                width="stretch",
                key="chat_offline_cache",
                help="حفظ الطلب الحالي في قائمة الانتظار للمعالجة لاحقاً",
                disabled=not st.session_state.pending_image,
            ):
                qid = enqueue_offline(
                    OWNER,
                    "analysis",
                    "[طلب تحليل من المساعد]",
                    st.session_state.pending_image,
                )
                st.success(f"تم الحفظ ({qid[:8]}).")
                time.sleep(0.5)
                st.rerun()
        with cc2:
            prompt = st.chat_input(
                "اكتب سؤالك الأكاديمي أو الصق حروف النقش…",
                disabled="chat" in st.session_state.get("background_jobs", {}),
            )
        st.caption(
            "🔒 تُحفظ المحادثة في أرشيفك الخاص بهذه الجلسة فقط، ولا تُرسل إلا لمزوّد النموذج الذي اخترته."
        )
    if "chat" in st.session_state.get("background_jobs", {}):
        st.info("جارٍ التحليل في الخلفية؛ يمكنك الانتقال بين الأقسام.")

    if prompt:
        image = st.session_state.pending_image
        if image:
            st.session_state.last_comparison_image = image
        if len(MESSAGES) == 0:
            ARCHIVE[CURRENT_CHAT]["title"] = prompt[:38]
        MESSAGES.append(
            {
                "role": "user",
                "content": (
                    prompt
                    if not image
                    else f"[صورة نقش مرفوعة: {image['name']}] {prompt}"
                ),
            }
        )
        with st.chat_message("user", avatar="🧑‍🔬"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🗿"):
            try:
                if st.session_state.mock_mode:
                    text = (
                        "### 🧪 استجابة محاكاة تعليمية\n\n"
                        "هذه نتيجة توضيحية لا تستخدم نموذج ذكاء اصطناعي ولا تمثل قراءة نقش حقيقية. "
                        "لا تعتمد عليها في النشر أو التوثيق الأكاديمي.\n\n"
                        f"**طلب الباحث:** {prompt or 'تحليل الصورة المرفقة'}\n\n"
                        f"**المرفق:** {image['name'] if image else 'لا توجد صورة'}\n\n"
                        "**خطوات العمل المقترحة:**\n"
                        "1. توثيق موضع النقش واتجاه القراءة وحالة السطح.\n"
                        "2. إعداد نسخة دبلوماسية للحروف الظاهرة مع تمييز الأجزاء المتضررة.\n"
                        "3. فصل النقل الحرفي عن الترجمة، ثم مراجعة القراءة مع مرجع متخصص.\n\n"
                        "أوقف وضع المحاكاة وأضف مفتاح مزود موثوق للحصول على تحليل فعلي."
                    )
                    st.markdown(text)
                    MESSAGES.append({"role": "assistant", "content": text})
                    st.session_state.pending_image = None
                    save_chat(
                        OWNER, CURRENT_CHAT, ARCHIVE[CURRENT_CHAT]["title"], MESSAGES
                    )
                    st.rerun()
                if st.session_state.session_locked:
                    raise RuntimeError(
                        "الجلسة مقفلة. افتحها قبل استخدام مفاتيح API، أو واصل في وضع المحاكاة."
                    )
                if not cur_key:
                    raise RuntimeError(
                        "لا يوجد مفتاح API لهذا المزود. أضف مفتاحاً أو فعّل وضع المحاكاة."
                    )
                if not sel_model:
                    raise RuntimeError(
                        "اختر نموذجاً أولاً (أو اجلب النماذج من الإعدادات)."
                    )
                api_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT_ANALYSIS}
                ] + [{"role": m["role"], "content": m["content"]} for m in MESSAGES]
                if prov.get("api_style") not in ("Google Gemini API", "OpenAI API"):
                    raise ValueError(
                        "نمط API المحدد غير مدعوم للتحليل؛ اختر OpenAI API أو Google Gemini API."
                    )
                if prov.get("api_style") == "Google Gemini API":
                    combined = "\n\n".join(
                        f"{message['role']}: {message['content']}"
                        for message in api_messages
                    )
                    start_background_job(
                        "chat",
                        gemini_generate,
                        cur_key,
                        sel_model,
                        combined,
                        image,
                        chat_id=CURRENT_CHAT,
                    )
                else:
                    start_background_job(
                        "chat",
                        openai_chat,
                        dict(prov),
                        cur_key,
                        sel_model,
                        api_messages,
                        image,
                        chat_id=CURRENT_CHAT,
                    )
                st.session_state.pending_image = None
            except (ValueError, RuntimeError) as exc:
                note = f"⚠️ تعذّر إتمام الطلب: {exc}"
                st.error(note)
                MESSAGES.append({"role": "assistant", "content": note})
        save_chat(OWNER, CURRENT_CHAT, ARCHIVE[CURRENT_CHAT]["title"], MESSAGES)
        st.rerun()


# =====================================================================================
# 16) عرض قائمة الانتظار الميدانية (Offline Queue)
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
def auto_sync_field_cache() -> None:
    """Schedule queue work without running network calls in the script thread."""
    if st.session_state.session_locked or not st.session_state.gemini_free_key:
        return
    if "queue" in st.session_state.get("background_jobs", {}):
        return
    if not load_offline_queue(OWNER, "pending"):
        return
    now = time.monotonic()
    if now - st.session_state.get("last_field_sync_attempt", 0) < 55:
        return
    st.session_state.last_field_sync_attempt = now
    start_background_job(
        "queue", process_offline_queue, OWNER, st.session_state.gemini_free_key
    )


# https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
@st.fragment(run_every="60s")
def render_offline_view() -> None:
    auto_sync_field_cache()
    notice = st.session_state.pop("queue_notice", None)
    if notice:
        st.info(notice)
    if "queue" in st.session_state.get("background_jobs", {}):
        st.info("تجري المزامنة في الخلفية.")
    st.markdown(
        "<div class='sec-title'>⏳ قائمة الانتظار الميدانية (Offline Caching)</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='sec-sub'>تُحفظ الطلبات محلياً في مخزن التطبيق الخاص بهذه الجلسة، ثم تُزامن تلقائياً "
        "كل دقيقة عند توفر الاتصال ومفتاح Gemini مفتوح. تعمل المزامنة التلقائية عند فتح هذا القسم وبقاء الجلسة نشطة؛ هذه ليست ذاكرة متصفح/PWA.</div>",
        unsafe_allow_html=True,
    )
    if st.session_state.session_locked:
        st.info("المزامنة التلقائية متوقفة أثناء قفل الجلسة حمايةً للمفتاح.")
    elif not st.session_state.gemini_free_key:
        st.info(
            "سيتم الاحتفاظ بالطلبات حتى إدخال مفتاح Gemini؛ يمكنك تصفح الأقسام واختبارها في وضع المحاكاة."
        )

    with st.container(border=True):
        st.markdown("**➕ حفظ طلب للعمل عليه لاحقاً**")
        with st.form("offline_enqueue_form", clear_on_submit=True):
            offline_query = st.text_area(
                "نص/وصف النقش أو المهمة",
                placeholder="اكتب وصفاً أو سؤالاً لحفظه دون إرسال الآن…",
                height=90,
            )
            cache_submit = st.form_submit_button(
                "⏳ حفظ في قائمة الميدان", type="primary", use_container_width=True
            )
            if cache_submit:
                if not offline_query.strip() and not st.session_state.pending_image:
                    st.warning("أدخل وصفاً أو أرفق صورة نقش أولاً.")
                else:
                    qid = enqueue_offline(
                        OWNER,
                        "analysis",
                        offline_query.strip(),
                        st.session_state.pending_image,
                    )
                    st.success(f"حُفظ الطلب محلياً في مخزن الجلسة ({qid[:8]}).")
                    st.rerun()

    # زر مزامنة يدوية
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 مزامنة الآن", type="primary", width="stretch", key="sync_now"):
            if st.session_state.session_locked:
                st.warning("افتح الجلسة قبل استخدام المفتاح للمزامنة.")
            elif not st.session_state.gemini_free_key:
                st.error("أضف مفتاح Gemini المجاني أولاً للمزامنة.")
            else:
                if start_background_job(
                    "queue",
                    process_offline_queue,
                    OWNER,
                    st.session_state.gemini_free_key,
                ):
                    st.info("بدأت المزامنة في الخلفية.")
                else:
                    st.info("المزامنة جارية بالفعل.")
    with col2:
        pending = len(load_offline_queue(OWNER, "pending"))
        processing = len(load_offline_queue(OWNER, "processing"))
        done = len(load_offline_queue(OWNER, "done"))
        failed = len(load_offline_queue(OWNER, "failed"))
        st.markdown(
            f"<div class='kv'>قيد الانتظار: <b>{pending}</b> · قيد المعالجة: <b>{processing}</b> · "
            f"مكتمل: <b>{done}</b> · فاشل: <b>{failed}</b></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # عرض قائمة الانتظار
    queue_items = load_offline_queue(OWNER)
    if not queue_items:
        st.info("قائمة الانتظار فارغة.")
        return

    for item in queue_items:
        status_color = {
            "pending": "pill-warn",
            "processing": "pill-info",
            "done": "pill-ok",
            "failed": "pill-off",
        }.get(item["status"], "pill-off")

        status_label = {
            "pending": "⏳ قيد الانتظار",
            "processing": "⚙️ قيد المعالجة",
            "done": "✅ مكتمل",
            "failed": "❌ فاشل",
        }.get(item["status"], item["status"])

        with st.container(border=True):
            qc1, qc2, qc3 = st.columns([3, 1, 1])
            with qc1:
                st.markdown(f"**{item['query'][:60] or '[صورة نقش]'}**")
                st.caption(f"النوع: {item['kind']} · {fmt_dt(item['created_at'])}")
                if item["image_name"]:
                    st.caption(f"📷 {item['image_name']}")
            with qc2:
                st.markdown(
                    f"<span class='pill {status_color}'>{status_label}</span>",
                    unsafe_allow_html=True,
                )
            with qc3:
                if item["status"] == "done" and item["result"]:
                    with st.expander("📄 النتيجة"):
                        st.markdown(
                            item["result"][:500] + "..."
                            if len(item["result"]) > 500
                            else item["result"]
                        )
                if item[
                    "status"
                ] == "processing" and "queue" not in st.session_state.get(
                    "background_jobs", {}
                ):
                    if st.button(
                        "↻ استعادة المتوقف",
                        key=f"recover_queue_{item['queue_id']}",
                        help="استعد العنصر فقط بعد التأكد من توقف المعالجة السابقة؛ قد يسبب تكرار الطلب.",
                    ):
                        recover_queue_item(OWNER, item["queue_id"])
                        st.rerun()
                if item["status"] == "failed":
                    if st.button(
                        "↻ إعادة",
                        key=f"retry_queue_{item['queue_id']}",
                        help="إعادته لقائمة الانتظار",
                    ):
                        update_queue_item(OWNER, item["queue_id"], "pending")
                        st.rerun()
                if item["status"] in ("pending", "failed"):
                    if st.button(
                        "🗑️", key=f"del_queue_{item['queue_id']}", help="حذف من القائمة"
                    ):
                        delete_queue_item(OWNER, item["queue_id"])
                        st.rerun()


# =====================================================================================
# 17) الأرشيف
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/layout/st.container
def render_archive_view() -> None:
    with st.container(border=True):
        h1, h2 = st.columns([3, 1], vertical_alignment="bottom")
        with h1:
            st.markdown(
                "<div class='sec-title'>📚 أرشيفي الخاص</div>", unsafe_allow_html=True
            )
            st.markdown(
                f"<div class='sec-sub'>{len(st.session_state.archive)} محادثة · مرتبطة بهويتك المؤقتة "
                f"<code>{OWNER[:8]}</code> ولا يراها غيرك.</div>",
                unsafe_allow_html=True,
            )
        with h2:
            export = json.dumps(
                [
                    {
                        "title": c["title"],
                        "messages": c["messages"],
                        "updated_at": c.get("updated_at", ""),
                    }
                    for c in st.session_state.archive.values()
                ],
                ensure_ascii=False,
                indent=2,
            )
            st.download_button(
                "⬇️ تصدير الأرشيف (JSON)",
                data=export.encode("utf-8"),
                file_name=f"archive_{datetime.now():%Y%m%d}.json",
                mime="application/json",
                width="stretch",
                key="exp_archive",
            )

    filt = st.text_input(
        "🔎 فلترة", placeholder="عنوان أو نص داخل المحادثات…", key="archive_filter"
    )
    rows = []
    for cid, c in st.session_state.archive.items():
        blob = normalize_ar(
            c["title"] + " " + " ".join(m.get("content", "") for m in c["messages"])
        )
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
                st.caption(
                    f"{len(c['messages'])} رسالة · آخر تحديث {fmt_dt(c.get('updated_at',''))}"
                )
            with cc2:
                if st.button("فتح", key=f"arch_open_{cid}", width="stretch"):
                    st.session_state.current_chat_id = cid
                    st.session_state.last_comparison_image = None
                    goto("chat")
            with cc3:
                md = (
                    "\n\n---\n\n".join(
                        f"### {m['role']}\n{m['content']}" for m in c["messages"]
                    )
                    or "—"
                )
                st.download_button(
                    "⬇️ MD",
                    data=md.encode("utf-8"),
                    file_name=f"{c['title'][:20]}.md",
                    mime="text/markdown",
                    width="stretch",
                    key=f"arch_dl_{cid}",
                )
            with cc4:
                if st.button("🗑️", key=f"arch_del_{cid}", help="حذف المحادثة"):
                    delete_chat(OWNER, cid)
                    st.session_state.archive.pop(cid, None)
                    if st.session_state.current_chat_id == cid:
                        st.session_state.current_chat_id = (
                            list(st.session_state.archive.keys())[0]
                            if st.session_state.archive
                            else ""
                        )
                    st.rerun()


# =====================================================================================
# 18) الإعدادات
# =====================================================================================
# https://docs.streamlit.io/develop/api-reference/layout/st.tabs
def render_settings_view() -> None:
    st.markdown(
        "<div class='sec-title'>⚙️ الإعدادات المتقدمة</div>", unsafe_allow_html=True
    )
    st.markdown(
        "<div class='sec-sub'>إدارة المزودين والنماذج وإعدادات الشبكة — كل شيء معزول لهذا المستخدم.</div>",
        unsafe_allow_html=True,
    )

    # زر المعالج الذكي البارز
    with st.container(border=True):
        st.markdown("### 🧙 المعالج الذكي للإعداد الذاتي")
        st.markdown(
            "<div class='sec-sub'>للأكاديميين غير التقنيين: إعداد تلقائي بضغطة زر — فقط أدخل المفتاح وسنضبط روابط الخوادم والنماذج القياسية تلقائياً.</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "🚀 الإعداد التلقائي بضغطة زر",
            type="primary",
            width="stretch",
            key="launch_wizard",
        ):
            setup_wizard_dialog()

    tab1, tab2, tab3 = st.tabs(
        ["🔌 المزودون والنماذج", "🔑 المفاتيح والخصوصية", "🌐 الشبكة والمهل"]
    )

    # ---- المزودون ----
    with tab1:
        with st.expander("➕ إضافة مزود مخصص"):
            with st.form("add_provider", clear_on_submit=True):
                f1, f2 = st.columns(2)
                with f1:
                    name = st.text_input("اسم المزود", placeholder="مثال: OpenRouter")
                    style = st.selectbox("نمط API", ["OpenAI API", "Google Gemini API"])
                with f2:
                    url = st.text_input(
                        "Base URL", value="https://openrouter.ai/api/v1"
                    )
                    path = st.text_input("المسار", value="/chat/completions")
                nk = st.text_input(
                    "مفتاح API (للجلسة فقط — لن يُحفظ)",
                    type="password",
                    key="new_provider_key",
                )
                net = st.checkbox("تحسين توافق الشبكة", value=True)
                if st.form_submit_button("حفظ المزود", type="primary"):
                    nm = name.strip()
                    if not nm:
                        st.error("أدخل اسم المزود.")
                    elif nm in st.session_state.providers:
                        st.error("اسم المزود موجود.")
                    else:
                        st.session_state.providers[nm] = {
                            "api_style": style,
                            "url": url.strip(),
                            "path": path.strip(),
                            "network_opt": net,
                            "models": {},
                        }
                        save_provider(OWNER, nm, st.session_state.providers[nm])
                        if nk.strip():
                            st.session_state.secret_keys[nm] = nk.strip()
                        st.success(f"أُضيف المزود «{nm}».")
                        st.rerun()

        pnames = list(st.session_state.providers.keys())
        sel = st.selectbox(
            "اختر المزود للتعديل", pnames, key="settings_provider_select"
        )
        prov = st.session_state.providers[sel]

        c1, c2 = st.columns(2)
        with c1:
            style_opts = ["OpenAI API", "Google Gemini API"]
            if st.session_state.get(f"st_style_{sel}") not in style_opts:
                st.session_state[f"st_style_{sel}"] = (
                    prov.get("api_style")
                    if prov.get("api_style") in style_opts
                    else "OpenAI API"
                )
            style = st.selectbox("نمط API", style_opts, key=f"st_style_{sel}")
            if f"st_url_{sel}" not in st.session_state:
                st.session_state[f"st_url_{sel}"] = prov.get("url", "")
            url = st.text_input("Base URL", key=f"st_url_{sel}")
        with c2:
            if f"st_path_{sel}" not in st.session_state:
                st.session_state[f"st_path_{sel}"] = prov.get("path", "")
            path = st.text_input("المسار", key=f"st_path_{sel}")

            # حقل المفتاح مع التحقق من القفل
            if st.session_state.session_locked:
                st.markdown(
                    "<span class='pill pill-warn'>🔒 مقفل</span>",
                    unsafe_allow_html=True,
                )
                key_val = ""
            else:
                key_val = st.text_input(
                    "مفتاح API (جلسة فقط)", type="password", key=f"st_key_{sel}"
                )

        if f"st_net_{sel}" not in st.session_state:
            st.session_state[f"st_net_{sel}"] = bool(prov.get("network_opt", True))
        net = st.toggle("تحسين توافق الشبكة", key=f"st_net_{sel}")

        notice = st.session_state.pop("provider_notice", None)
        if notice:
            st.info(notice)
        if any(
            key in st.session_state.get("background_jobs", {})
            for key in ("provider_ping", "provider_models")
        ):
            st.info("يجري طلب المزود في الخلفية.")

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button(
                "💾 حفظ", type="primary", width="stretch", key=f"st_save_{sel}"
            ):
                prov.update(
                    {"api_style": style, "url": url, "path": path, "network_opt": net}
                )
                save_provider(OWNER, sel, prov)
                if key_val.strip():
                    st.session_state.secret_keys[sel] = key_val.strip()
                st.success("تم الحفظ (المفتاح في الجلسة فقط).")
                st.rerun()
        with b2:
            if st.button(
                "💡 Auto-Ping · فحص سريع", width="stretch", key=f"st_test_{sel}"
            ):
                if st.session_state.session_locked:
                    st.warning("افتح الجلسة أولاً.")
                else:
                    k = key_val.strip() or provider_key(sel)
                    if not k:
                        st.warning("أدخل المفتاح.")
                    elif style != "Google Gemini API" and openai is None:
                        st.error("حزمة openai غير مثبتة.")
                    else:
                        if style == "Google Gemini API":
                            start_background_job(
                                "provider_ping",
                                gemini_generate,
                                k,
                                GEMINI_MODELS[0],
                                "مرحبا",
                            )
                        else:
                            start_background_job(
                                "provider_ping", fetch_provider_models, k, url
                            )
                        st.rerun()
        with b3:
            if st.button("🔄 جلب النماذج", width="stretch", key=f"st_fetch_{sel}"):
                if st.session_state.session_locked:
                    st.warning("افتح الجلسة أولاً.")
                else:
                    k = key_val.strip() or provider_key(sel)
                    if not k:
                        st.warning("أدخل المفتاح أولاً.")
                    elif style == "Google Gemini API":
                        prov["models"] = {
                            m: {"alias": m, "type": "دردشة"} for m in GEMINI_MODELS
                        }
                        save_provider(OWNER, sel, prov)
                        st.success(
                            f"تم ضبط {len(prov['models'])} أسماء محلية؛ لم يُتحقق من توفرها عن بعد."
                        )
                        st.rerun()
                    else:
                        start_background_job(
                            "provider_models",
                            fetch_provider_models,
                            k,
                            url,
                            provider=sel,
                        )
                        st.rerun()
        with b4:
            if len(pnames) > 1 and st.button(
                "🗑️ حذف المزود", width="stretch", key=f"st_del_{sel}"
            ):
                st.session_state.providers.pop(sel, None)
                st.session_state.secret_keys.pop(sel, None)
                delete_provider(OWNER, sel)
                st.success("تم الحذف.")
                st.rerun()

        with st.expander(f"🧠 نماذج المزود الحالي ({len(prov.get('models', {}))})"):
            if prov.get("models"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "model_id": k,
                                "alias": v.get("alias", k),
                                "vision": v.get("vision", "غير معروف"),
                                "context": v.get("context", ""),
                            }
                            for k, v in prov["models"].items()
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("لا نماذج — استخدم «🔄 جلب النماذج».")

    # ---- المفاتيح والخصوصية ----
    with tab2:
        st.markdown("#### 🔑 مفاتيح الجلسة")
        st.caption(
            "هذه المفاتيح في ذاكرة جلسة التطبيق على الخادم: لا تُكتب في قاعدة البيانات ولا تُضمَّن في الرابط، وتُمحى بانتهاء الجلسة. رمز المرور قفل واجهة وليس تشفيراً للمفتاح؛ لا تترك جلسة غير موثوقة مفتوحة."
        )

        # التحقق من القفل قبل عرض المفاتيح
        if st.session_state.session_locked:
            st.warning("🔒 الجلسة مقفلة — افتحها لعرض المفاتيح.")
            if st.button("🔓 فتح الجلسة", key="settings_unlock"):
                unlock_session_dialog()
        else:
            items = list(st.session_state.secret_keys.items())
            if items:
                for name, k in items:
                    st.markdown(f"- **{name}**: `{k[:6]}…{k[-4:]}`")
            else:
                st.info("لا مفاتيح مزودين في الجلسة.")
            gk = st.session_state.gemini_free_key
            st.markdown(
                f"- **Gemini المجاني (بحث)**: `{gk[:6]}…{gk[-4:]}`"
                if gk
                else "- **Gemini المجاني (بحث)**: غير مضبوط"
            )

            if st.button(
                "🧹 مسح كل المفاتيح من الجلسة",
                key="wipe_keys",
                disabled=bool(st.session_state.get("background_jobs")),
            ):
                st.session_state.secret_keys = {}
                st.session_state.gemini_free_key = ""
                st.session_state.clear_secret_widgets = True
                st.success("تم مسح المفاتيح.")
                st.rerun()

        st.divider()
        st.markdown("#### 🔒 تأمين الجلسة")
        if st.session_state.session_locked:
            st.success("الجلسة مقفلة برمز مرور.")
            if st.button("🔓 فتح الجلسة", key="settings_unlock2"):
                unlock_session_dialog()
        else:
            st.info("الجلسة غير مقفلة — أي شخص يصل للمتصفح يمكنه رؤية المفاتيح.")
            if st.button("🔒 تأمين الجلسة برمز مرور", key="settings_lock"):
                lock_session_dialog()

        if st.session_state.session_pin_hash:
            if st.button("🗑️ إزالة رمز المرور", key="remove_pin"):
                st.session_state.session_pin_hash = None
                st.session_state.session_locked = False
                st.success("تمت إزالة رمز المرور.")
                st.rerun()

        st.divider()
        st.markdown("#### 🔒 عزل المستخدمين")
        st.markdown(f"""
- معرّف جلستك: `{OWNER}` (عشوائي، مؤقت، لا يُنقل عبر الرابط).
- المحادثات تُخزَّن في جدول `chats_v2` بعمود `owner` — لا يمكن لمستخدم آخر استعلام صفوفك.
- المفاتيح لا تُخزَّن مطلقاً في قاعدة البيانات (أُلغي عمود المفاتيح، ونُظّفت أي قيم قديمة).
- معاملات الرابط الحساسة (`?key=`, `?chat_id=` …) تُحذف تلقائياً عند كل تحميل.
- زر «حذف بياناتي نهائياً» في الشريط الجانبي يمحو كل صفوفك.
- **تأمين الجلسة**: يتطلب رمز مرور لعرض المفاتيح أو استخدامها.
            """)
        st.download_button(
            "⬇️ تصدير بياناتي (JSON)",
            data=json.dumps(
                {
                    "owner": OWNER,
                    "chats": list(st.session_state.archive.values()),
                    "corpus": [r for r in load_corpus(OWNER) if r["owner"] == OWNER],
                },
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
            file_name=f"my_data_{datetime.now():%Y%m%d}.json",
            mime="application/json",
            key="exp_my_data",
        )

    # ---- الشبكة ----
    with tab3:
        st.markdown("#### 🌐 الشبكة والمهل")
        if "net_timeout" not in st.session_state:
            st.session_state.net_timeout = 120
        if "net_compat" not in st.session_state:
            st.session_state.net_compat = True
        st.slider("مهلة الاتصال العامة (ثانية)", 10, 300, key="net_timeout")
        st.toggle("تحسين توافق الشبكة للمزودين المخصصين", key="net_compat")
        st.caption("إعدادات الشبكة المعروضة هنا لا تتحكم حالياً في مهل طلبات النماذج.")
        st.divider()
        st.markdown("#### ⏳ التخزين المؤقت الميداني")
        pending = len(load_offline_queue(OWNER, "pending"))
        st.markdown(f"عناصر قيد الانتظار: **{pending}**")
        st.caption(
            "تُحفظ الطلبات محلياً في قاعدة البيانات وتُعالج تلقائياً عند رصد اتصال."
        )
        st.divider()
        st.markdown("#### ℹ️ عن المنصة")
        st.markdown(
            "الإصدار **3.0** — إعادة بناء أكاديمية كاملة، أربع مساحات عمل منفصلة، نافذة رفع نقش مستقلة، عزل لكل جلسة، "
            "بحث عن النقش يعمل بمفتاح **Gemini المجاني** أو محلياً **بدون أي مفتاح**، "
            "مع ميزات ميدانية: وضع داكن عالي التباين، مقارنة حية، تخزين مؤقت، معالج إعداد ذاتي، وتأمين مفاتيح."
        )


# =====================================================================================
# 19) التوجيه
# =====================================================================================
if VIEW == "eye":
    render_eye_view()
elif VIEW == "chat":
    render_chat_view()
elif VIEW == "global":
    render_global_view()
else:
    render_settings_view()

poll_background_jobs()
if st.session_state.get("storage_warning"):
    st.warning(st.session_state.storage_warning)

st.markdown(
    "<div style='text-align:center;color:#94a3b8;font-size:.7rem;padding-top:26px'>"
    "مختبر المسند الرقمي · جلسة خاصة معزولة · لا تُشارَك المفاتيح ولا السجلات مع أي مستخدم آخر · v3.0"
    "</div>",
    unsafe_allow_html=True,
)
