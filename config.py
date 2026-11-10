import os
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Membaca variabel lingkungan dari file .env (jika tersedia).
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _upload_folder():
    value = os.getenv("UPLOAD_FOLDER", os.path.join("static", "uploads"))
    if os.path.isabs(value):
        return value
    return os.path.abspath(os.path.join(BASE_DIR, value))


class Config:
    """Konfigurasi aplikasi. Tidak berisi logika bisnis."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-ganti-di-production")

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "sistem_garansi_qr")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))

    UPLOAD_FOLDER = _upload_folder()
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(12 * 1024 * 1024)))
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(5 * 1024 * 1024)))
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

    # URL publik untuk pembuatan QR Code (opsional, berguna di balik proxy).
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.getenv("SESSION_COOKIE_SECURE"), False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_HOURS", "8")))

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5000"))
    DEBUG = _bool(os.getenv("FLASK_DEBUG"), False)
