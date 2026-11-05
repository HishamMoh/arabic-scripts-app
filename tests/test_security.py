"""
اختبارات آلية للوظائف الأمنية في تطبيق المختبر الرقمي لدراسات المسند.
يغطي: حماية XSS، التشفير/fك التشفير للمفاتيح، التحقق من رمز المرور، التطبيع العربي.
"""
import os
import sys
import tempfile

# التأكد من استخدام قاعدة بيانات مؤقتة للاختبارات
os.environ["MUSNAD_DB_PATH"] = ":memory:"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402  (يتم الاستيراد بعد ضبط المتغير البيئي)


def test_escape_html_prevents_xss():
    """التحقق من أن escape_html تحولacre السكريبتات الخبيثة إلى نص عادي."""
    malicious = "<img src=x onerror=alert(1)>.jpg"
    escaped = app.escape_html(malicious)
    # الأهم: علامات HTML الخطرة يجب أن تُحَوَّل (لا يمكن تنفيذ السكريبت)
    assert "<" not in escaped
    assert ">" not in escaped
    assert "&lt;img" in escaped
    assert "&gt;" in escaped
    print("✅ test_escape_html_prevents_xss نجح")


def test_encrypt_decrypt_roundtrip():
    """التحقق من أن النص المشفر يُعاد إلى أصله عبر نفس كلمة السر."""
    secret = "sk-1234567890abcdef"
    pin = "1234"
    encrypted = app.encrypt_secret(secret, pin)
    assert encrypted != secret  # يجب أن يكون مختلفاً عن الأصل
    assert encrypted.startswith("v1:")
    decrypted = app.decrypt_secret(encrypted, pin)
    assert decrypted == secret
    print("✅ test_encrypt_decrypt_roundtrip نجح")


def test_decrypt_with_wrong_pin_fails():
    """التحقق من أن فك التشفير برمز خاطئ يفشل أو يعيد قيمة مختلفة."""
    secret = "sk-1234567890abcdef"
    encrypted = app.encrypt_secret(secret, "pin1")
    # فك التشفير برمز مختلف يجب أن يفشل أو يعيد نصاً غير صحيح
    decrypted = app.decrypt_secret(encrypted, "pin2")
    assert decrypted != secret
    print("✅ test_decrypt_with_wrong_pin_fails نجح")


def test_verify_pin_correct_and_incorrect():
    """التحقق من أن verify_pin تقبل الرمز الصحيح وترفض الخاطئ."""
    pin = "abcd1234"
    stored = app.hash_pin(pin)
    assert app.verify_pin(pin, stored) is True
    assert app.verify_pin("wrongpin", stored) is False
    assert app.verify_pin(pin, None) is False
    assert app.verify_pin(pin, "") is False
    print("✅ test_verify_pin_correct_and_incorrect نجح")


def test_normalize_arabic():
    """التحقق من أن التطبيع العربي يزيل التشكيل ويوحد الأحرف."""
    assert app.normalize_ar("أَحْمَدٌ") == "احمد"
    assert app.normalize_ar("مُحَمَّدٍ") == "محمد"
    assert app.normalize_ar("") == ""
    assert app.normalize_ar(None) == ""
    print("✅ test_normalize_arabic نجح")


def test_audit_table_exists():
    """التحقق من وجود جدول السجل التدريبي في قاعدة البيانات."""
    import sqlite3
    conn = app.db_conn()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    assert "audit_log" in tables
    print("✅ test_audit_table_exists نجح")


if __name__ == "__main__":
    test_escape_html_prevents_xss()
    test_encrypt_decrypt_roundtrip()
    test_decrypt_with_wrong_pin_fails()
    test_verify_pin_correct_and_incorrect()
    test_normalize_arabic()
    test_audit_table_exists()
    print("\n🎉 جميع الاختبارات الأمنية نجحت!")
