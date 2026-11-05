"""Regression tests for storage, external requests and Streamlit responsiveness."""

# https://docs.pytest.org/en/stable/how-to/monkeypatch.html
# https://docs.streamlit.io/develop/concepts/app-testing/get-started
import ast
import base64
import concurrent.futures
import io
import logging
import textwrap
import sqlite3
import threading
import uuid
from contextlib import closing
from pathlib import Path

import pandas as pd
import pytest
import requests
import services
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def functions(tmp_path):
    """Load pure functions without executing Streamlit's top-level UI."""
    names = {
        "db_conn",
        "_cell",
        "upsert_corpus_rows",
        "claim_queue_item",
        "load_offline_queue",
        "update_queue_item",
        "get_queue_image",
        "process_offline_queue",
        "encode_b64",
        "generate_pdf",
        "matches_query",
    }
    source = ast.parse(APP.read_text(encoding="utf-8"))
    module = ast.Module(
        body=[
            node
            for node in source.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ],
        type_ignores=[],
    )
    env = {
        "sqlite3": sqlite3,
        "closing": closing,
        "pd": pd,
        "requests": requests,
        "base64": base64,
        "io": io,
        "textwrap": textwrap,
        "LOGGER": logging.getLogger("test_app"),
        "DB_PATH": str(tmp_path / "test.db"),
        "new_id": lambda: uuid.uuid4().hex[:16],
        "now_str": lambda: "2026-01-01 00:00:00",
        "SYSTEM_PROMPT_LOOKUP": "prompt",
        "SYSTEM_PROMPT_ANALYSIS": "analysis prompt",
        "GEMINI_MODELS": ["gemini-2.5-flash"],
        "GEMINI_URL": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    }
    exec(compile(module, str(APP), "exec"), env)
    with closing(sqlite3.connect(env["DB_PATH"])) as db:
        db.executescript("""
            CREATE TABLE corpus_v2 (entry_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                code TEXT, corpus TEXT, script TEXT, region TEXT, century TEXT,
                text TEXT, note TEXT, created_at TEXT);
            CREATE TABLE offline_queue (queue_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                kind TEXT, query TEXT, image_b64 TEXT, image_name TEXT, image_mime TEXT,
                status TEXT, result TEXT, created_at TEXT, processed_at TEXT);
        """)
        db.commit()
    return env


def test_corpus_owner_cannot_overwrite_other_owner(functions):
    save = functions["upsert_corpus_rows"]
    first = pd.DataFrame([{"entry_id": "known", "code": "original"}])
    assert save("alice", first) == 1
    assert save("bob", pd.DataFrame([{"entry_id": "known", "code": "changed"}])) == 0
    with closing(sqlite3.connect(functions["DB_PATH"])) as db:
        assert db.execute("SELECT owner, code FROM corpus_v2").fetchone() == (
            "alice",
            "original",
        )
    assert save("alice", pd.DataFrame([{"entry_id": "known", "code": "updated"}])) == 1


def test_claim_is_atomic_and_owner_scoped(functions):
    with closing(sqlite3.connect(functions["DB_PATH"])) as db:
        db.execute(
            "INSERT INTO offline_queue (queue_id, owner, status) VALUES ('q', 'alice', 'pending')"
        )
        db.commit()
    claim = functions["claim_queue_item"]
    assert not claim("bob", "q")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(lambda _: claim("alice", "q"), range(20))) == 1


def test_queue_failure_does_not_store_secret(functions):
    with closing(sqlite3.connect(functions["DB_PATH"])) as db:
        db.execute(
            "INSERT INTO offline_queue (queue_id, owner, kind, query, status) VALUES ('q', 'alice', 'search', 'test', 'pending')"
        )
        db.commit()

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET API KEY")

    functions["gemini_generate"] = fail
    assert functions["process_offline_queue"]("alice", "SECRET API KEY") == 0
    with closing(sqlite3.connect(functions["DB_PATH"])) as db:
        status, result = db.execute(
            "SELECT status, result FROM offline_queue"
        ).fetchone()
    assert status == "failed"
    assert "SECRET" not in result


def test_gemini_uses_header_and_hides_error_body(functions, monkeypatch):
    calls = []

    class Response:
        ok = True
        status_code = 200

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "result"}]}}]}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(requests, "post", post)
    generate = services.gemini_generate
    assert (
        generate(
            "secret",
            "gemini-2.5-flash",
            "prompt",
            {"bytes": b"img", "mime": "image/png"},
        )
        == "result"
    )
    url, kwargs = calls[0]
    assert "secret" not in url and "params" not in kwargs
    assert kwargs["headers"]["x-goog-api-key"] == "secret"
    assert kwargs["json"]["contents"][0]["parts"][1]["inline_data"]["data"] == "aW1n"
    Response.ok = False
    Response.status_code = 400
    Response.text = "secret response"
    with pytest.raises(RuntimeError, match="HTTP 400") as exc:
        generate("secret", "model", "prompt")
    assert "secret" not in str(exc.value)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not at.exception
    return at


def test_mock_chat_works(app):
    app.button(key="eye_go_assistant").click().run()
    app.chat_input[0].set_value("اختبار نقش").run()
    assert not app.exception
    assert "محاكاة" in app.chat_message[-1].markdown[0].value


def test_chat_network_does_not_block_navigation(app, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    class Response:
        ok = True

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "مسودة تجريبية"}]}}]}

    def post(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return Response()

    monkeypatch.setattr(requests, "post", post)
    app.session_state["gemini_free_key"] = "test-key"
    app.session_state["mock_mode"] = False
    app.button(key="eye_go_assistant").click().run()
    try:
        app.chat_input[0].set_value("افحص النص").run()
        assert entered.wait(3)
        assert not app.exception
        assert "chat" in app.session_state["background_jobs"]
        app.button(key="sb_offline_queue").click().run()
        assert not app.exception
        assert app.session_state["global_subview"] == "⏳ التخزين الميداني"
        release.set()
        app.session_state["background_jobs"]["chat"]["future"].result(timeout=5)
        app.run()
        assert not app.exception
        archive = app.session_state["archive"]
        assert any(
            m["content"] == "مسودة تجريبية"
            for chat in archive.values()
            for m in chat["messages"]
        )
    finally:
        release.set()


def test_local_search_and_queue_ui(app):
    app.button(key="sb_offline_queue").click().run()
    app.text_area[0].set_value("وصف للاختبار")
    app.button(
        key="FormSubmitter:offline_enqueue_form-⏳ حفظ في قائمة الميدان"
    ).click().run()
    assert not app.exception
    with closing(sqlite3.connect("musnad_lab_v2.db")) as db:
        assert db.execute("SELECT query, status FROM offline_queue").fetchone() == (
            "وصف للاختبار",
            "pending",
        )


def test_gemini_search_runs_in_background(app, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    class Response:
        ok = True

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "نتيجة بحث"}]}}]}

    def post(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return Response()

    monkeypatch.setattr(requests, "post", post)
    app.session_state["gemini_free_key"] = "test-key"
    app.get("segmented_control")[0].set_value("🌐 البوابة العالمية").run()
    app.radio(key="search_engine").set_value("✨ بحث وتحليل بـ Gemini المجاني")
    app.text_area(key="search_query").set_value("CIH 352")
    try:
        app.button(key="search_run").click().run()
        assert entered.wait(3)
        assert not app.exception
        app.button(key="sb_offline_queue").click().run()
        assert not app.exception
    finally:
        release.set()
    app.session_state["background_jobs"]["search"]["future"].result(timeout=5)
    app.run()
    assert not app.exception
    assert app.session_state["search_result"]["text"] == "نتيجة بحث"


def test_queue_sync_runs_in_background(app, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    class Response:
        ok = True

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "نتيجة طابور"}]}}]}

    def post(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return Response()

    monkeypatch.setattr(requests, "post", post)
    app.button(key="sb_offline_queue").click().run()
    app.text_area[0].set_value("وصف")
    app.button(
        key="FormSubmitter:offline_enqueue_form-⏳ حفظ في قائمة الميدان"
    ).click().run()
    app.session_state["gemini_free_key"] = "test-key"
    try:
        app.run()
        assert entered.wait(3)
        assert "queue" in app.session_state["background_jobs"]
        app.get("segmented_control")[0].set_value("المساعد الإبيغرافي").run()
        assert not app.exception
        release.set()
        app.session_state["background_jobs"]["queue"]["future"].result(timeout=5)
        app.run()
        assert not app.exception
        with closing(sqlite3.connect("musnad_lab_v2.db")) as db:
            assert db.execute(
                "SELECT status, result FROM offline_queue"
            ).fetchone() == ("done", "نتيجة طابور")
    finally:
        release.set()


def test_pdf_does_not_silently_corrupt_arabic(functions):
    generate = functions["generate_pdf"]
    assert generate("نص عربي") is None
    assert generate("A" * 200).startswith(b"%PDF")


def test_corrupt_database_displays_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "musnad_lab_v2.db").write_bytes(b"not a sqlite database")
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    assert any("قاعدة البيانات" in error.value for error in app.error)


def test_openai_chat_uses_image_and_closes_client(monkeypatch):
    from types import SimpleNamespace

    calls = {}

    class Client:
        def __init__(self, **kwargs):
            calls["config"] = kwargs
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls["closed"] = True

        def create(self, **kwargs):
            calls["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=" reply "))]
            )

    monkeypatch.setattr(services.openai, "OpenAI", Client)
    messages = [{"role": "user", "content": "question"}]
    result = services.openai_chat(
        {"url": "https://example.test/v1/"},
        "secret",
        "model",
        messages,
        {"bytes": b"img", "mime": "image/png"},
    )
    assert result == "reply"
    assert calls["closed"]
    assert calls["config"]["base_url"] == "https://example.test/v1"
    assert calls["request"]["messages"][0]["content"][1]["image_url"]["url"].endswith(
        ",aW1n"
    )
    assert messages == [{"role": "user", "content": "question"}]


def test_search_does_not_match_everything_for_single_character(functions):
    matches = functions["matches_query"]
    assert not matches("x", "abc")
    assert matches("x", "box")
    assert matches("first second", "second and first")
    assert not matches("first absent", "first")


def test_queued_analysis_uses_analysis_prompt(functions):
    with closing(sqlite3.connect(functions["DB_PATH"])) as db:
        db.execute(
            "INSERT INTO offline_queue (queue_id, owner, kind, query, status) "
            "VALUES ('q', 'alice', 'analysis', 'test', 'pending')"
        )
        db.commit()
    captured = []

    def generate(key, model, prompt, image=None):
        captured.append(prompt)
        return "result"

    functions["gemini_generate"] = generate
    assert functions["process_offline_queue"]("alice", "key") == 1
    assert captured[0].startswith("analysis prompt")


def test_pin_cannot_be_removed_while_session_is_locked(app):
    app.session_state["session_pin_hash"] = "present"
    app.session_state["session_locked"] = True
    app.get("segmented_control")[0].set_value("⚙️ الإعدادات المتقدمة").run()
    assert not app.exception
    assert all(button.key != "remove_pin" for button in app.button)


# https://docs.streamlit.io/develop/concepts/app-testing/get-started
def test_field_camera_removed_but_upload_and_dialog_remain(app):
    assert not app.get("camera_input")
    assert len(app.get("file_uploader")) == 1

    app.button(key="sb_upload_btn").click().run()
    assert not app.exception
    assert len(app.get("camera_input")) == 1


# https://docs.streamlit.io/develop/concepts/app-testing/get-started
def test_field_image_upload_still_works(app):
    from PIL import Image

    uploader = app.get("file_uploader")[0]
    if not hasattr(uploader, "upload"):
        pytest.skip("FileUploader testing is unavailable in this Streamlit version")
    content = io.BytesIO()
    Image.new("RGB", (3, 3), "white").save(content, format="PNG")
    uploader.upload("inscription.png", content.getvalue(), "image/png").run()

    assert not app.exception
    assert app.session_state["pending_image"]["name"] == "inscription.png"
    assert app.session_state["pending_image"]["bytes"] == content.getvalue()
