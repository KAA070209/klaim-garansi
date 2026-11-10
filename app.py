import calendar
import io
import os
import re
import secrets
import string
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

import mysql.connector
import qrcode
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask.sessions import SecureCookieSessionInterface
from mysql.connector import Error as MySQLError
from mysql.connector import IntegrityError
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config

# ---------------------------------------------------------------------------
# Konfigurasi Flask
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


class SesiRememberMe(SecureCookieSessionInterface):
    """Session cookie dengan opsi 'ingat sesi saya' selama 30 hari.

    Sesi biasa hanya valid selama ``PERMANENT_SESSION_LIFETIME``. Cookie
    dengan tanda ``_ingat_30d`` diperbolehkan bertahan hingga 30 hari.
    """

    SESSION_MAX_AGE = 60 * 60 * 24 * 30

    def open_session(self, app, request):
        serializer = self.get_signing_serializer(app)
        if serializer is None:
            return self.session_class()

        nilai = request.cookies.get(self.get_cookie_name(app))
        if not nilai:
            return self.session_class()

        max_age = int(app.permanent_session_lifetime.total_seconds())
        try:
            data = serializer.loads(nilai, max_age=max_age)
            return self.session_class(data)
        except Exception:
            try:
                data = serializer.loads(nilai, max_age=self.SESSION_MAX_AGE)
                if data.get("_ingat_30d"):
                    return self.session_class(data)
            except Exception:
                pass
            return self.session_class()

    def get_expiration_time(self, app, session):
        if not session.permanent:
            return None
        if session.get("_ingat_30d"):
            return datetime.now(timezone.utc) + timedelta(days=30)
        return datetime.now(timezone.utc) + app.permanent_session_lifetime


app.session_interface = SesiRememberMe()

# ---------------------------------------------------------------------------
# Konstanta dan label
# ---------------------------------------------------------------------------

STATUS_KLAIM_LABELS = {
    "menunggu_verifikasi": "Menunggu Verifikasi",
    "sedang_ditinjau": "Sedang Ditinjau",
    "disetujui": "Disetujui",
    "ditolak": "Ditolak",
    "dalam_perbaikan": "Dalam Perbaikan",
    "selesai": "Selesai",
}

STATUS_GARANSI_LABELS = {
    "aktif": "Aktif",
    "berakhir": "Berakhir",
    "tidak_aktif": "Belum Aktif",
    "dibatalkan": "Dibatalkan",
}

STATUS_LAIN_LABELS = {
    "tersedia": "Tersedia",
    "terdaftar": "Terdaftar",
    "nonaktif": "Nonaktif",
    "dibatalkan": "Dibatalkan",
    "aktif": "Aktif",
}

ROLE_LABELS = {
    "admin": "Admin",
    "petugas": "Petugas",
    "pelanggan": "Pelanggan",
}

STATUS_BADGES = {
    "menunggu_verifikasi": "warning",
    "sedang_ditinjau": "info",
    "disetujui": "success",
    "ditolak": "danger",
    "dalam_perbaikan": "primary",
    "selesai": "neutral",
    "aktif": "success",
    "berakhir": "danger",
    "tidak_aktif": "neutral",
    "dibatalkan": "danger",
    "tersedia": "info",
    "terdaftar": "success",
    "nonaktif": "neutral",
}

TRANSISI_STATUS = {
    "menunggu_verifikasi": ["sedang_ditinjau"],
    "sedang_ditinjau": ["disetujui", "ditolak"],
    "disetujui": ["dalam_perbaikan"],
    "dalam_perbaikan": ["selesai"],
    "ditolak": [],
    "selesai": [],
}

STATUS_AKHIR_KLAIM = {"ditolak", "selesai"}
STATUS_KLAIM_AKTIF = {
    "menunggu_verifikasi",
    "sedang_ditinjau",
    "disetujui",
    "dalam_perbaikan",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationError(Exception):
    """Kesalahan validasi yang aman ditampilkan kepada pengguna."""


# ---------------------------------------------------------------------------
# Koneksi database
# ---------------------------------------------------------------------------


def get_db():
    """Membuka satu koneksi database per request Flask."""
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=app.config["MYSQL_HOST"],
            user=app.config["MYSQL_USER"],
            password=app.config["MYSQL_PASSWORD"],
            database=app.config["MYSQL_DATABASE"],
            port=app.config["MYSQL_PORT"],
            charset="utf8mb4",
            use_unicode=True,
            autocommit=False,
        )
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is None:
        return
    try:
        if exception is not None:
            db.rollback()
    except Exception:
        app.logger.exception("Gagal melakukan rollback koneksi database.")
    finally:
        try:
            db.close()
        except Exception:
            app.logger.exception("Gagal menutup koneksi database.")


def query_one(sql, params=()):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    finally:
        cursor.close()


def query_all(sql, params=()):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()


def execute(sql, params=()):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(sql, params)
        db.commit()
        return cursor.lastrowid
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()


def scalar(sql, params=()):
    row = query_one(sql, params)
    if not row:
        return 0
    return int(next(iter(row.values())))


# ---------------------------------------------------------------------------
# Helper umum
# ---------------------------------------------------------------------------


def format_tanggal(value):
    if not value:
        return "-"
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        return value
    bulan = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]
    return f"{value.day} {bulan[value.month - 1]} {value.year}"


def format_tanggal_waktu(value):
    if not value:
        return "-"
    if isinstance(value, date) and not isinstance(value, datetime):
        return format_tanggal(value)
    return f"{format_tanggal(value)} {value:%H:%M}"


def format_ukuran(value):
    if not value:
        return "-"
    try:
        value = int(value)
    except (TypeError, ValueError):
        return "-"
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def status_garansi(tanggal_berakhir):
    if not tanggal_berakhir:
        return "tidak_aktif"
    if isinstance(tanggal_berakhir, datetime):
        tanggal_berakhir = tanggal_berakhir.date()
    return "aktif" if tanggal_berakhir >= date.today() else "berakhir"


def add_months(tanggal, bulan):
    month_index = tanggal.month - 1 + int(bulan)
    year = tanggal.year + month_index // 12
    month = month_index % 12 + 1
    day = min(tanggal.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def parse_tanggal(value, nama_field="tanggal"):
    if not value:
        raise ValidationError(f"{nama_field} wajib diisi.")
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError(f"Format {nama_field} tidak valid.") from exc


def parse_tanggal_opsional(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def validasi_email(email):
    return bool(email and EMAIL_RE.match(email))


def safe_next_url(target):
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target


def dashboard_endpoint(role):
    return {
        "admin": "admin_dashboard",
        "petugas": "petugas_dashboard",
        "pelanggan": "pelanggan_dashboard",
    }.get(role, "login")


def qr_target_url(token_qr):
    base = app.config.get("PUBLIC_BASE_URL") or request.host_url.rstrip("/")
    return f"{base}{url_for('qr_detail', token_qr=token_qr)}"


def buat_token_qr():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def buat_nomor_seri(produk_id):
    return (
        f"PRD{int(produk_id):03d}-{datetime.now():%y%m%d}-"
        f"{secrets.token_hex(3).upper()}"
    )


def simpan_upload(file_storage, subfolder):
    """Validasi dan simpan file gambar. Mengembalikan metadata file."""
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise ValidationError("File wajib diunggah.")

    nama_asli = secure_filename(file_storage.filename or "")
    if "." not in nama_asli:
        raise ValidationError("Nama file tidak memiliki ekstensi yang valid.")

    ekstensi = nama_asli.rsplit(".", 1)[1].lower()
    if ekstensi not in app.config["ALLOWED_EXTENSIONS"]:
        raise ValidationError("Format file harus jpg, jpeg, png, atau webp.")

    data = file_storage.read()
    if not data:
        raise ValidationError("File yang diunggah kosong.")
    if len(data) > app.config["MAX_FILE_SIZE"]:
        batas = app.config["MAX_FILE_SIZE"] // (1024 * 1024)
        raise ValidationError(f"Ukuran file maksimal {batas} MB.")

    try:
        with Image.open(io.BytesIO(data)) as gambar:
            gambar.verify()
    except Exception as exc:
        raise ValidationError("File bukan gambar yang valid.") from exc

    nama_file = f"{uuid.uuid4().hex}.{ekstensi}"
    folder = os.path.join(app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(folder, exist_ok=True)
    path_absolut = os.path.join(folder, nama_file)
    with open(path_absolut, "wb") as output:
        output.write(data)

    return {
        "nama_file": nama_file,
        "path_file": f"uploads/{subfolder}/{nama_file}",
        "tipe_file": ekstensi,
        "ukuran_file": len(data),
    }


def hapus_file(path_file):
    if not path_file:
        return
    try:
        path_absolut = os.path.join(app.static_folder, path_file)
        if os.path.isfile(path_absolut):
            os.remove(path_absolut)
    except OSError:
        app.logger.exception("Gagal menghapus file upload: %s", path_file)


def catat_log(aksi, deskripsi, pengguna_id=None):
    """Mencatat aktivitas. Kegagalan log tidak boleh menggagalkan aksi utama."""
    try:
        if pengguna_id is None and g.get("user"):
            pengguna_id = g.user["id"]
        execute(
            """
            INSERT INTO log_aktivitas (pengguna_id, aksi, deskripsi, alamat_ip)
            VALUES (%s, %s, %s, %s)
            """,
            (
                pengguna_id,
                (aksi or "aktivitas")[:100],
                (deskripsi or "")[:1000],
                request.remote_addr,
            ),
        )
    except Exception:
        app.logger.exception("Gagal mencatat log aktivitas.")


def tambah_notifikasi(cursor, pengguna_id, klaim_id, judul, pesan):
    cursor.execute(
        """
        INSERT INTO notifikasi (pengguna_id, klaim_id, judul, pesan, dibaca)
        VALUES (%s, %s, %s, %s, 0)
        """,
        (pengguna_id, klaim_id, judul[:150], pesan),
    )


def ambil_qr(token_qr):
    row = query_one(
        """
        SELECT
            q.id AS qr_id,
            q.produk_id,
            q.nomor_seri,
            q.token_qr,
            q.status AS status_qr,
            q.dibuat_pada,
            p.nama_produk,
            p.kategori_model,
            p.deskripsi,
            p.status AS status_produk,
            kg.id AS kebijakan_id,
            kg.nama AS nama_kebijakan,
            kg.durasi_bulan,
            kg.aktif AS kebijakan_aktif,
            r.id AS registrasi_id,
            r.pelanggan_id,
            r.tanggal_pembelian,
            r.tempat_pembelian,
            r.nomor_invoice,
            g.tanggal_mulai,
            g.tanggal_berakhir,
            g.status AS status_garansi_tersimpan
        FROM kode_qr_produk q
        JOIN produk p ON p.id = q.produk_id
        JOIN kebijakan_garansi kg ON kg.id = p.kebijakan_garansi_id
        LEFT JOIN registrasi_produk r
            ON r.kode_qr_id = q.id AND r.status_registrasi = 'aktif'
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        WHERE q.token_qr = %s
        """,
        (token_qr,),
    )
    if row:
        row["status_garansi_aktual"] = status_garansi(row.get("tanggal_berakhir"))
    return row


def ambil_registrasi(registrasi_id, pelanggan_id=None):
    sql = """
        SELECT
            r.id AS registrasi_id,
            r.pelanggan_id,
            r.tanggal_pembelian,
            r.tempat_pembelian,
            r.nomor_invoice,
            r.bukti_pembelian,
            r.status_registrasi,
            r.dibuat_pada,
            u.nama AS nama_pelanggan,
            u.email AS email_pelanggan,
            u.nomor_telepon AS telepon_pelanggan,
            u.alamat AS alamat_pelanggan,
            p.id AS produk_id,
            p.nama_produk,
            p.kategori_model,
            p.deskripsi,
            p.status AS status_produk,
            q.id AS qr_id,
            q.nomor_seri,
            q.token_qr,
            q.status AS status_qr,
            kg.id AS kebijakan_id,
            kg.nama AS nama_kebijakan,
            kg.durasi_bulan,
            kg.aktif AS kebijakan_aktif,
            g.id AS garansi_id,
            g.tanggal_mulai,
            g.tanggal_berakhir,
            g.status AS status_garansi_tersimpan
        FROM registrasi_produk r
        JOIN pengguna u ON u.id = r.pelanggan_id
        JOIN kode_qr_produk q ON q.id = r.kode_qr_id
        JOIN produk p ON p.id = q.produk_id
        JOIN kebijakan_garansi kg ON kg.id = p.kebijakan_garansi_id
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        WHERE r.id = %s AND r.status_registrasi = 'aktif'
    """
    params = [registrasi_id]
    if pelanggan_id is not None:
        sql += " AND r.pelanggan_id = %s"
        params.append(pelanggan_id)

    row = query_one(sql, tuple(params))
    if row:
        row["status_garansi_aktual"] = status_garansi(row.get("tanggal_berakhir"))
    return row


def klaim_aktif_untuk_registrasi(registrasi_id):
    return query_one(
        """
        SELECT id, status
        FROM klaim_garansi
        WHERE registrasi_produk_id = %s
          AND status IN ('menunggu_verifikasi', 'sedang_ditinjau', 'disetujui', 'dalam_perbaikan')
        ORDER BY id DESC
        LIMIT 1
        """,
        (registrasi_id,),
    )


def hitung_status_klaim():
    rows = query_all(
        "SELECT status, COUNT(*) AS jumlah FROM klaim_garansi GROUP BY status"
    )
    return {row["status"]: int(row["jumlah"]) for row in rows}


def pesan_notifikasi_status(klaim_id, status_baru, alasan=None):
    label = STATUS_KLAIM_LABELS.get(status_baru, status_baru)
    if status_baru == "ditolak":
        pesan = f"Klaim #{klaim_id} ditolak."
        if alasan:
            pesan += f" Alasan: {alasan}"
        return "Klaim Ditolak", pesan
    if status_baru == "disetujui":
        return "Klaim Disetujui", f"Klaim #{klaim_id} telah disetujui dan akan diproses."
    if status_baru == "dalam_perbaikan":
        return "Klaim Dalam Perbaikan", f"Klaim #{klaim_id} sedang dalam proses perbaikan."
    if status_baru == "selesai":
        return "Klaim Selesai", f"Klaim #{klaim_id} telah selesai diproses."
    if status_baru == "sedang_ditinjau":
        return "Klaim Sedang Ditinjau", f"Klaim #{klaim_id} sedang ditinjau oleh petugas."
    return f"Status Klaim: {label}", f"Status klaim #{klaim_id} berubah menjadi {label}."


# ---------------------------------------------------------------------------
# Authentication dan authorization
# ---------------------------------------------------------------------------


@app.before_request
def muat_pengguna():
    g.user = None
    # Berkas unggahan hanya boleh diakses melalui /berkas/<path> yang memeriksa
    # kepemilikan. Cegah akses langsung melalui folder static (termasuk variasi
    # huruf besar/kecil dan garis miring ganda pada Windows).
    if request.path.lower().startswith("/static/"):
        jalur = os.path.normpath(request.path).replace("\\", "/").lower()
        if "/uploads/" in jalur:
            abort(404)
    if request.endpoint == "static":
        return
    user_id = session.get("user_id")
    if not user_id:
        return
    try:
        user = query_one(
            "SELECT id, nama, email, nomor_telepon, role, aktif FROM pengguna WHERE id = %s",
            (user_id,),
        )
    except MySQLError:
        app.logger.exception("Gagal memuat data pengguna dari session.")
        return

    if not user or not user["aktif"]:
        session.clear()
        flash("Sesi berakhir atau akun tidak aktif. Silakan login kembali.", "warning")
        return

    g.user = user


def role_required(*roles):
    def decorator(fungsi):
        @wraps(fungsi)
        def wrapper(*args, **kwargs):
            if g.get("user") is None:
                flash("Silakan login terlebih dahulu.", "warning")
                return redirect(url_for("login", next=request.full_path))
            if g.user["role"] not in roles:
                abort(403)
            return fungsi(*args, **kwargs)

        return wrapper

    return decorator


def format_angka_ringkas(value):
    """Memformat angka dengan pemisah ribuan gaya Indonesia."""
    try:
        angka = int(value)
    except (TypeError, ValueError):
        angka = 0
    return f"{angka:,}".replace(",", ".")


def statistik_landing():
    """Mengambil ringkasan statistik publik untuk landing page."""
    data = {
        "produk": 0,
        "unit_qr": 0,
        "unit_terdaftar": 0,
        "garansi_aktif": 0,
        "pelanggan": 0,
        "kebijakan": 0,
        "klaim_total": 0,
        "klaim_disetujui": 0,
    }
    try:
        data["produk"] = scalar("SELECT COUNT(*) FROM produk WHERE status = 'aktif'")
        data["unit_qr"] = scalar("SELECT COUNT(*) FROM kode_qr_produk")
        data["unit_terdaftar"] = scalar(
            "SELECT COUNT(*) FROM registrasi_produk WHERE status_registrasi = 'aktif'"
        )
        data["garansi_aktif"] = scalar(
            """
            SELECT COUNT(*) FROM garansi
            WHERE status = 'aktif' AND tanggal_berakhir >= CURDATE()
            """
        )
        data["pelanggan"] = scalar(
            "SELECT COUNT(*) FROM pengguna WHERE role = 'pelanggan' AND aktif = 1"
        )
        data["kebijakan"] = scalar(
            "SELECT COUNT(*) FROM kebijakan_garansi WHERE aktif = 1"
        )
        data["klaim_total"] = scalar("SELECT COUNT(*) FROM klaim_garansi")
        data["klaim_disetujui"] = scalar(
            """
            SELECT COUNT(*) FROM klaim_garansi
            WHERE status IN ('disetujui', 'dalam_perbaikan', 'selesai')
            """
        )
    except MySQLError:
        app.logger.exception("Gagal memuat statistik landing page.")

    total_klaim = data["klaim_total"]
    data["persen_klaim"] = (
        100 if not total_klaim else round(100 * data["klaim_disetujui"] / total_klaim)
    )
    for kunci in ("produk", "unit_qr", "unit_terdaftar", "garansi_aktif", "pelanggan", "kebijakan", "klaim_total", "klaim_disetujui"):
        data[f"{kunci}_format"] = format_angka_ringkas(data[kunci])
    return data


def kategori_landing(limit=6):
    """Daftar kategori produk aktif beserta jumlah unitnya."""
    try:
        return query_all(
            """
            SELECT
                p.kategori_model AS kategori,
                COUNT(*) AS jumlah,
                MAX(kg.durasi_bulan) AS durasi_maks
            FROM produk p
            JOIN kebijakan_garansi kg ON kg.id = p.kebijakan_garansi_id
            WHERE p.status = 'aktif'
            GROUP BY p.kategori_model
            ORDER BY jumlah DESC, kategori ASC
            LIMIT %s
            """,
            (limit,),
        )
    except MySQLError:
        app.logger.exception("Gagal memuat kategori produk landing page.")
        return []


def kebijakan_landing(limit=3):
    """Kebijakan garansi aktif yang ditampilkan pada landing page."""
    try:
        return query_all(
            """
            SELECT id, nama, durasi_bulan, deskripsi
            FROM kebijakan_garansi
            WHERE aktif = 1
            ORDER BY durasi_bulan DESC, nama ASC
            LIMIT %s
            """,
            (limit,),
        )
    except MySQLError:
        app.logger.exception("Gagal memuat kebijakan garansi landing page.")
        return []


def produk_unggulan_landing():
    """Produk aktif terbaru untuk kartu unggulan pada hero."""
    try:
        produk = query_one(
            """
            SELECT
                p.nama_produk,
                p.kategori_model,
                kg.nama AS nama_kebijakan,
                kg.durasi_bulan
            FROM produk p
            JOIN kebijakan_garansi kg ON kg.id = p.kebijakan_garansi_id
            WHERE p.status = 'aktif'
            ORDER BY p.id DESC
            LIMIT 1
            """
        )
    except MySQLError:
        app.logger.exception("Gagal memuat produk unggulan landing page.")
        produk = None
    return produk or {
        "nama_produk": "VoltShield Smart Series",
        "kategori_model": "Elektronik Rumah Tangga",
        "nama_kebijakan": "Garansi Standar",
        "durasi_bulan": 12,
    }


@app.route("/")
def index():
    return render_template(
        "index.html",
        statistik=statistik_landing(),
        kategori_produk=kategori_landing(),
        kebijakan_aktif=kebijakan_landing(),
        produk_unggulan=produk_unggulan_landing(),
    )


@app.route("/cek-garansi", methods=["GET", "POST"])
def cek_garansi():
    """Mencari unit berdasarkan nomor seri atau token QR, lalu membuka detailnya."""
    kode = (request.values.get("token_qr") or "").strip()

    if not kode:
        flash("Masukkan nomor seri atau token QR terlebih dahulu.", "warning")
        return redirect(url_for("index") + "#cek-garansi")

    try:
        qr = query_one(
            """
            SELECT token_qr FROM kode_qr_produk
            WHERE token_qr = %s OR nomor_seri = %s
            LIMIT 1
            """,
            (kode, kode),
        )
    except MySQLError:
        app.logger.exception("Gagal mencari data garansi dari landing page.")
        flash("Data garansi sedang tidak dapat diakses. Silakan coba lagi.", "danger")
        return redirect(url_for("index") + "#cek-garansi")

    if not qr:
        flash(
            f'Nomor seri "{kode}" tidak ditemukan. Periksa kembali kode pada kemasan produk.',
            "danger",
        )
        return redirect(url_for("index") + "#cek-garansi")

    return redirect(url_for("qr_detail", token_qr=qr["token_qr"]))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for(dashboard_endpoint(g.user["role"])))

    next_url = safe_next_url(request.args.get("next") or request.form.get("next"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email dan password wajib diisi.", "danger")
            return render_template("login.html", next_url=next_url, statistik=statistik_landing())

        try:
            user = query_one("SELECT * FROM pengguna WHERE email = %s", (email,))
        except MySQLError:
            app.logger.exception("Gagal memeriksa akun saat login.")
            flash("Terjadi gangguan pada database. Silakan coba lagi.", "danger")
            return render_template("login.html", next_url=next_url, statistik=statistik_landing())

        password_valid = False
        if user:
            try:
                password_valid = check_password_hash(user["password_hash"], password)
            except (ValueError, TypeError):
                password_valid = False

        if not user or not password_valid:
            flash("Email atau password salah.", "danger")
            return render_template("login.html", next_url=next_url, statistik=statistik_landing())

        if not user["aktif"]:
            flash("Akun Anda tidak aktif. Hubungi admin.", "danger")
            return render_template("login.html", next_url=next_url, statistik=statistik_landing())

        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["_ingat_30d"] = bool(request.form.get("ingat_saya"))
        catat_log("login", f"Pengguna {user['email']} login.", user["id"])

        flash(f"Selamat datang, {user['nama']}.", "success")
        return redirect(next_url or url_for(dashboard_endpoint(user["role"])))

    return render_template("login.html", next_url=next_url, statistik=statistik_landing())


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user"):
        return redirect(url_for(dashboard_endpoint(g.user["role"])))

    next_url = safe_next_url(request.args.get("next") or request.form.get("next"))
    form = {
        "nama": "",
        "email": "",
        "nomor_telepon": "",
        "alamat": "",
    }

    if request.method == "POST":
        form.update(
            {
                "nama": (request.form.get("nama") or "").strip(),
                "email": (request.form.get("email") or "").strip().lower(),
                "nomor_telepon": (request.form.get("nomor_telepon") or "").strip(),
                "alamat": (request.form.get("alamat") or "").strip(),
            }
        )
        password = request.form.get("password") or ""
        konfirmasi = request.form.get("konfirmasi_password") or ""

        try:
            if len(form["nama"]) < 3:
                raise ValidationError("Nama minimal 3 karakter.")
            if not validasi_email(form["email"]):
                raise ValidationError("Format email tidak valid.")
            if form["nomor_telepon"] and len(form["nomor_telepon"]) < 8:
                raise ValidationError("Nomor telepon tidak valid.")
            if len(password) < 8:
                raise ValidationError("Password minimal 8 karakter.")
            if password != konfirmasi:
                raise ValidationError("Konfirmasi password tidak sama.")
            if query_one("SELECT id FROM pengguna WHERE email = %s", (form["email"],)):
                raise ValidationError("Email sudah digunakan.")

            pengguna_id = execute(
                """
                INSERT INTO pengguna
                    (nama, email, nomor_telepon, alamat, password_hash, role, aktif)
                VALUES (%s, %s, %s, %s, %s, 'pelanggan', 1)
                """,
                (
                    form["nama"],
                    form["email"],
                    form["nomor_telepon"] or None,
                    form["alamat"] or None,
                    generate_password_hash(password),
                ),
            )
        except ValidationError as exc:
            flash(str(exc), "danger")
            return render_template("register.html", form=form, next_url=next_url, statistik=statistik_landing())
        except IntegrityError:
            flash("Email sudah digunakan.", "danger")
            return render_template("register.html", form=form, next_url=next_url, statistik=statistik_landing())

        session.clear()
        session.permanent = True
        session["user_id"] = pengguna_id
        session["role"] = "pelanggan"
        catat_log("registrasi_akun", "Pelanggan membuat akun baru.", pengguna_id)
        flash("Akun berhasil dibuat. Selamat datang.", "success")
        return redirect(next_url or url_for("pelanggan_dashboard"))

    return render_template("register.html", form=form, next_url=next_url, statistik=statistik_landing())


@app.route("/logout", methods=["GET", "POST"])
def logout():
    if g.get("user"):
        catat_log("logout", f"Pengguna {g.user['email']} logout.")
    session.clear()
    flash("Anda telah logout.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Route admin
# ---------------------------------------------------------------------------


@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    stats = {
        "total_petugas": scalar(
            "SELECT COUNT(*) FROM pengguna WHERE role = 'petugas'"
        ),
        "total_pelanggan": scalar(
            "SELECT COUNT(*) FROM pengguna WHERE role = 'pelanggan'"
        ),
        "total_produk": scalar("SELECT COUNT(*) FROM produk"),
        "total_klaim": scalar("SELECT COUNT(*) FROM klaim_garansi"),
        "total_registrasi": scalar(
            "SELECT COUNT(*) FROM registrasi_produk WHERE status_registrasi = 'aktif'"
        ),
    }
    status_counts = hitung_status_klaim()
    klaim_terbaru = query_all(
        """
        SELECT
            k.id,
            k.status,
            k.tanggal_klaim,
            u.nama AS nama_pelanggan,
            p.nama_produk,
            q.nomor_seri
        FROM klaim_garansi k
        JOIN pengguna u ON u.id = k.pelanggan_id
        JOIN registrasi_produk r ON r.id = k.registrasi_produk_id
        JOIN kode_qr_produk q ON q.id = r.kode_qr_id
        JOIN produk p ON p.id = q.produk_id
        ORDER BY k.tanggal_klaim DESC
        LIMIT 8
        """
    )
    log_terbaru = query_all(
        """
        SELECT l.*, u.nama AS nama_pengguna, u.role
        FROM log_aktivitas l
        LEFT JOIN pengguna u ON u.id = l.pengguna_id
        ORDER BY l.dibuat_pada DESC
        LIMIT 10
        """
    )
    daftar_petugas_dashboard = query_all(
        """
        SELECT id, nama, email, nomor_telepon, aktif, dibuat_pada
        FROM pengguna
        WHERE role = 'petugas'
        ORDER BY dibuat_pada DESC
        LIMIT 5
        """
    )
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        status_counts=status_counts,
        klaim_terbaru=klaim_terbaru,
        log_terbaru=log_terbaru,
        daftar_petugas_dashboard=daftar_petugas_dashboard,
    )


@app.route("/admin/dashboard/petugas/tambah", methods=["POST"])
@role_required("admin")
def admin_dashboard_petugas_tambah():
    nama = (request.form.get("nama") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    nomor_telepon = (request.form.get("nomor_telepon") or "").strip()
    alamat = (request.form.get("alamat") or "").strip()
    password = request.form.get("password") or ""
    konfirmasi = request.form.get("konfirmasi_password") or ""

    try:
        if len(nama) < 3:
            raise ValidationError("Nama minimal 3 karakter.")
        if not validasi_email(email):
            raise ValidationError("Format email tidak valid.")
        if nomor_telepon and len(nomor_telepon) < 8:
            raise ValidationError("Nomor telepon tidak valid.")
        if len(password) < 8:
            raise ValidationError("Password minimal 8 karakter.")
        if password != konfirmasi:
            raise ValidationError("Konfirmasi password tidak sama.")
        if query_one("SELECT id FROM pengguna WHERE email = %s", (email,)):
            raise ValidationError("Email sudah digunakan.")

        execute(
            """
            INSERT INTO pengguna
                (nama, email, nomor_telepon, alamat, password_hash, role, aktif)
            VALUES (%s, %s, %s, %s, %s, 'petugas', 1)
            """,
            (nama, email, nomor_telepon or None, alamat or None,
             generate_password_hash(password)),
        )
        catat_log("tambah_petugas_dashboard", f"Menambahkan petugas {email} dari dashboard.")
        flash("Petugas berhasil ditambahkan.", "success")
    except ValidationError as exc:
        flash(str(exc), "danger")
    except IntegrityError:
        flash("Email sudah digunakan.", "danger")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/dashboard/petugas/<int:petugas_id>/toggle", methods=["POST"])
@role_required("admin")
def admin_dashboard_petugas_toggle(petugas_id):
    petugas = query_one(
        "SELECT id, nama, email, aktif FROM pengguna WHERE id = %s AND role = 'petugas'",
        (petugas_id,),
    )
    if not petugas:
        abort(404)

    status_baru = 0 if petugas["aktif"] else 1
    execute(
        "UPDATE pengguna SET aktif = %s WHERE id = %s AND role = 'petugas'",
        (status_baru, petugas_id),
    )
    label = "diaktifkan" if status_baru else "dinonaktifkan"
    catat_log("toggle_petugas_dashboard", f"Akun petugas {petugas['email']} {label}.")
    flash(f"Akun petugas berhasil {label}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/petugas")
@role_required("admin")
def admin_petugas():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()

    sql = """
        SELECT
            p.*,
            (SELECT COUNT(*) FROM log_aktivitas l WHERE l.pengguna_id = p.id) AS total_aktivitas
        FROM pengguna p
        WHERE p.role = 'petugas'
    """
    params = []
    if q:
        sql += " AND (p.nama LIKE %s OR p.email LIKE %s OR p.nomor_telepon LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if status in {"aktif", "nonaktif"}:
        sql += " AND p.aktif = %s"
        params.append(1 if status == "aktif" else 0)
    sql += " ORDER BY p.dibuat_pada DESC"

    daftar_petugas = query_all(sql, tuple(params))
    return render_template(
        "admin/petugas.html",
        daftar_petugas=daftar_petugas,
        q=q,
        status=status,
    )


@app.route("/admin/petugas/tambah", methods=["GET", "POST"])
@role_required("admin")
def admin_petugas_tambah():
    form = {
        "nama": "",
        "email": "",
        "nomor_telepon": "",
        "alamat": "",
        "aktif": 1,
    }

    if request.method == "POST":
        form.update(
            {
                "nama": (request.form.get("nama") or "").strip(),
                "email": (request.form.get("email") or "").strip().lower(),
                "nomor_telepon": (request.form.get("nomor_telepon") or "").strip(),
                "alamat": (request.form.get("alamat") or "").strip(),
                "aktif": 1 if request.form.get("aktif") else 0,
            }
        )
        password = request.form.get("password") or ""
        konfirmasi = request.form.get("konfirmasi_password") or ""

        try:
            if len(form["nama"]) < 3:
                raise ValidationError("Nama minimal 3 karakter.")
            if not validasi_email(form["email"]):
                raise ValidationError("Format email tidak valid.")
            if form["nomor_telepon"] and len(form["nomor_telepon"]) < 8:
                raise ValidationError("Nomor telepon tidak valid.")
            if len(password) < 8:
                raise ValidationError("Password minimal 8 karakter.")
            if password != konfirmasi:
                raise ValidationError("Konfirmasi password tidak sama.")
            if query_one("SELECT id FROM pengguna WHERE email = %s", (form["email"],)):
                raise ValidationError("Email sudah digunakan.")

            petugas_id = execute(
                """
                INSERT INTO pengguna
                    (nama, email, nomor_telepon, alamat, password_hash, role, aktif)
                VALUES (%s, %s, %s, %s, %s, 'petugas', %s)
                """,
                (
                    form["nama"],
                    form["email"],
                    form["nomor_telepon"] or None,
                    form["alamat"] or None,
                    generate_password_hash(password),
                    form["aktif"],
                ),
            )
        except ValidationError as exc:
            flash(str(exc), "danger")
            return render_template("admin/petugas_tambah.html", form=form)
        except IntegrityError:
            flash("Email sudah digunakan.", "danger")
            return render_template("admin/petugas_tambah.html", form=form)

        catat_log("tambah_petugas", f"Menambahkan petugas {form['email']}.")
        flash("Petugas berhasil ditambahkan.", "success")
        return redirect(url_for("admin_petugas"))

    return render_template("admin/petugas_tambah.html", form=form)


@app.route("/admin/petugas/edit/<int:petugas_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_petugas_edit(petugas_id):
    petugas = query_one(
        "SELECT * FROM pengguna WHERE id = %s AND role = 'petugas'", (petugas_id,)
    )
    if not petugas:
        abort(404)

    form = {
        "nama": petugas["nama"],
        "email": petugas["email"],
        "nomor_telepon": petugas["nomor_telepon"] or "",
        "alamat": petugas["alamat"] or "",
        "aktif": int(petugas["aktif"]),
    }

    if request.method == "POST":
        form.update(
            {
                "nama": (request.form.get("nama") or "").strip(),
                "email": (request.form.get("email") or "").strip().lower(),
                "nomor_telepon": (request.form.get("nomor_telepon") or "").strip(),
                "alamat": (request.form.get("alamat") or "").strip(),
                "aktif": 1 if request.form.get("aktif") else 0,
            }
        )
        password = request.form.get("password") or ""
        konfirmasi = request.form.get("konfirmasi_password") or ""

        try:
            if len(form["nama"]) < 3:
                raise ValidationError("Nama minimal 3 karakter.")
            if not validasi_email(form["email"]):
                raise ValidationError("Format email tidak valid.")
            if form["nomor_telepon"] and len(form["nomor_telepon"]) < 8:
                raise ValidationError("Nomor telepon tidak valid.")
            duplikat = query_one(
                "SELECT id FROM pengguna WHERE email = %s AND id <> %s",
                (form["email"], petugas_id),
            )
            if duplikat:
                raise ValidationError("Email sudah digunakan.")
            if password:
                if len(password) < 8:
                    raise ValidationError("Password minimal 8 karakter.")
                if password != konfirmasi:
                    raise ValidationError("Konfirmasi password tidak sama.")

            if password:
                execute(
                    """
                    UPDATE pengguna
                    SET nama = %s, email = %s, nomor_telepon = %s, alamat = %s,
                        aktif = %s, password_hash = %s
                    WHERE id = %s AND role = 'petugas'
                    """,
                    (
                        form["nama"],
                        form["email"],
                        form["nomor_telepon"] or None,
                        form["alamat"] or None,
                        form["aktif"],
                        generate_password_hash(password),
                        petugas_id,
                    ),
                )
            else:
                execute(
                    """
                    UPDATE pengguna
                    SET nama = %s, email = %s, nomor_telepon = %s, alamat = %s, aktif = %s
                    WHERE id = %s AND role = 'petugas'
                    """,
                    (
                        form["nama"],
                        form["email"],
                        form["nomor_telepon"] or None,
                        form["alamat"] or None,
                        form["aktif"],
                        petugas_id,
                    ),
                )
        except ValidationError as exc:
            flash(str(exc), "danger")
            return render_template(
                "admin/petugas_edit.html", form=form, petugas=petugas
            )
        except IntegrityError:
            flash("Email sudah digunakan.", "danger")
            return render_template(
                "admin/petugas_edit.html", form=form, petugas=petugas
            )

        catat_log("edit_petugas", f"Mengubah data petugas {form['email']}.")
        flash("Data petugas berhasil diperbarui.", "success")
        return redirect(url_for("admin_petugas"))

    return render_template("admin/petugas_edit.html", form=form, petugas=petugas)


@app.route("/admin/petugas/<int:petugas_id>/toggle", methods=["POST"])
@role_required("admin")
def admin_petugas_toggle(petugas_id):
    petugas = query_one(
        "SELECT * FROM pengguna WHERE id = %s AND role = 'petugas'", (petugas_id,)
    )
    if not petugas:
        abort(404)

    status_baru = 0 if petugas["aktif"] else 1
    execute(
        "UPDATE pengguna SET aktif = %s WHERE id = %s AND role = 'petugas'",
        (status_baru, petugas_id),
    )
    label = "diaktifkan" if status_baru else "dinonaktifkan"
    catat_log("toggle_petugas", f"Akun petugas {petugas['email']} {label}.")
    flash(f"Akun petugas berhasil {label}.", "success")
    return redirect(url_for("admin_petugas"))


@app.route("/admin/petugas/<int:petugas_id>/hapus", methods=["POST"])
@role_required("admin")
def admin_petugas_hapus(petugas_id):
    petugas = query_one(
        "SELECT id,email FROM pengguna WHERE id = %s AND role = 'petugas'", (petugas_id,)
    )
    if not petugas:
        abort(404)
    if petugas_id == g.user["id"]:
        flash("Anda tidak dapat menghapus akun sendiri.", "danger")
        return redirect(url_for("admin_petugas"))
    try:
        execute("DELETE FROM pengguna WHERE id = %s AND role = 'petugas'", (petugas_id,))
        catat_log("hapus_petugas", f"Admin menghapus petugas {petugas['email']}.")
        flash("Petugas berhasil dihapus.", "success")
    except IntegrityError:
        flash("Petugas tidak dapat dihapus karena memiliki data terkait. Nonaktifkan akun sebagai alternatif.", "danger")
    return redirect(url_for("admin_petugas"))


@app.route("/admin/laporan")
@role_required("admin")
def admin_laporan():
    tanggal_mulai_raw = (request.args.get("tanggal_mulai") or "").strip()
    tanggal_selesai_raw = (request.args.get("tanggal_selesai") or "").strip()
    status = (request.args.get("status") or "").strip()
    q = (request.args.get("q") or "").strip()

    tanggal_mulai = parse_tanggal_opsional(tanggal_mulai_raw)
    tanggal_selesai = parse_tanggal_opsional(tanggal_selesai_raw)

    if tanggal_mulai_raw and not tanggal_mulai:
        flash("Tanggal mulai tidak valid dan diabaikan.", "warning")
    if tanggal_selesai_raw and not tanggal_selesai:
        flash("Tanggal selesai tidak valid dan diabaikan.", "warning")

    where = ["1 = 1"]
    params = []
    if tanggal_mulai:
        where.append("DATE(tanggal_klaim) >= %s")
        params.append(tanggal_mulai)
    if tanggal_selesai:
        where.append("DATE(tanggal_klaim) <= %s")
        params.append(tanggal_selesai)
    if status in STATUS_KLAIM_LABELS:
        where.append("status_klaim = %s")
        params.append(status)
    if q:
        where.append(
            "(nama_pelanggan LIKE %s OR email_pelanggan LIKE %s OR nama_produk LIKE %s "
            "OR nomor_seri LIKE %s OR nomor_invoice LIKE %s)"
        )
        params.extend([f"%{q}%"] * 5)

    where_sql = " AND ".join(where)
    laporan = query_all(
        f"""
        SELECT *
        FROM v_laporan_klaim_garansi
        WHERE {where_sql}
        ORDER BY tanggal_klaim DESC
        LIMIT 500
        """,
        tuple(params),
    )
    for item in laporan:
        item["status_garansi_aktual"] = status_garansi(
            item.get("tanggal_berakhir_garansi")
        )

    status_rows = query_all(
        f"""
        SELECT status_klaim, COUNT(*) AS jumlah
        FROM v_laporan_klaim_garansi
        WHERE {where_sql}
        GROUP BY status_klaim
        """,
        tuple(params),
    )
    status_counts = {row["status_klaim"]: int(row["jumlah"]) for row in status_rows}
    total_terfilter = sum(status_counts.values())

    log_aktivitas = query_all(
        """
        SELECT l.*, u.nama AS nama_pengguna, u.role
        FROM log_aktivitas l
        LEFT JOIN pengguna u ON u.id = l.pengguna_id
        ORDER BY l.dibuat_pada DESC
        LIMIT 100
        """
    )

    return render_template(
        "admin/laporan.html",
        laporan=laporan,
        status_counts=status_counts,
        total_terfilter=total_terfilter,
        log_aktivitas=log_aktivitas,
        filter={
            "tanggal_mulai": tanggal_mulai_raw,
            "tanggal_selesai": tanggal_selesai_raw,
            "status": status,
            "q": q,
        },
    )


# ---------------------------------------------------------------------------
# Admin: CRUD Pelanggan
# ---------------------------------------------------------------------------


@app.route("/admin/pelanggan")
@role_required("admin", "petugas")
def admin_pelanggan():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    sql = """
        SELECT u.*,
            (SELECT COUNT(*) FROM registrasi_produk r WHERE r.pelanggan_id=u.id AND r.status_registrasi='aktif') AS total_registrasi,
            (SELECT COUNT(*) FROM klaim_garansi k WHERE k.pelanggan_id=u.id) AS total_klaim
        FROM pengguna u WHERE u.role='pelanggan'
    """
    params = []
    if q:
        sql += " AND (u.nama LIKE %s OR u.email LIKE %s OR u.nomor_telepon LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if status in {"aktif", "nonaktif"}:
        sql += " AND u.aktif=%s"
        params.append(1 if status == "aktif" else 0)
    sql += " ORDER BY u.dibuat_pada DESC"
    rows = query_all(sql, tuple(params))
    return render_template("admin/pelanggan.html", daftar_pelanggan=rows, q=q, status=status)


@app.route("/admin/pelanggan/tambah", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_pelanggan_tambah():
    form = {"nama": "", "email": "", "nomor_telepon": "", "alamat": "", "aktif": 1}
    if request.method == "POST":
        form.update({
            "nama": (request.form.get("nama") or "").strip(),
            "email": (request.form.get("email") or "").strip().lower(),
            "nomor_telepon": (request.form.get("nomor_telepon") or "").strip(),
            "alamat": (request.form.get("alamat") or "").strip(),
            "aktif": 1 if request.form.get("aktif") else 0,
        })
        password = request.form.get("password") or ""
        try:
            if len(form["nama"]) < 3:
                raise ValidationError("Nama minimal 3 karakter.")
            if not validasi_email(form["email"]):
                raise ValidationError("Format email tidak valid.")
            if len(password) < 8:
                raise ValidationError("Password minimal 8 karakter.")
            if query_one("SELECT id FROM pengguna WHERE email=%s", (form["email"],)):
                raise ValidationError("Email sudah digunakan.")
            execute(
                """INSERT INTO pengguna (nama,email,nomor_telepon,alamat,password_hash,role,aktif)
                   VALUES (%s,%s,%s,%s,%s,'pelanggan',%s)""",
                (form["nama"], form["email"], form["nomor_telepon"] or None,
                 form["alamat"] or None, generate_password_hash(password), form["aktif"]),
            )
            catat_log("tambah_pelanggan", f"Admin menambahkan pelanggan {form['email']}.")
            flash("Pelanggan berhasil ditambahkan.", "success")
            return redirect(url_for(('petugas_manage_pelanggan' if request.path.startswith('/petugas/manage') else 'admin_pelanggan')))
        except ValidationError as e:
            flash(str(e), "danger")
        except IntegrityError:
            flash("Email sudah digunakan.", "danger")
    return render_template("admin/pelanggan_tambah.html", form=form)


@app.route("/admin/pelanggan/edit/<int:pelanggan_id>", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_pelanggan_edit(pelanggan_id):
    row = query_one("SELECT * FROM pengguna WHERE id=%s AND role='pelanggan'", (pelanggan_id,))
    if not row:
        abort(404)
    form = {
        "nama": row["nama"], "email": row["email"],
        "nomor_telepon": row.get("nomor_telepon") or "",
        "alamat": row.get("alamat") or "", "aktif": int(row["aktif"]),
    }
    if request.method == "POST":
        form.update({
            "nama": (request.form.get("nama") or "").strip(),
            "email": (request.form.get("email") or "").strip().lower(),
            "nomor_telepon": (request.form.get("nomor_telepon") or "").strip(),
            "alamat": (request.form.get("alamat") or "").strip(),
            "aktif": 1 if request.form.get("aktif") else 0,
        })
        password = request.form.get("password") or ""
        try:
            if len(form["nama"]) < 3:
                raise ValidationError("Nama minimal 3 karakter.")
            if not validasi_email(form["email"]):
                raise ValidationError("Format email tidak valid.")
            dup = query_one("SELECT id FROM pengguna WHERE email=%s AND id<>%s", (form["email"], pelanggan_id))
            if dup:
                raise ValidationError("Email sudah digunakan.")
            if password and len(password) < 8:
                raise ValidationError("Password minimal 8 karakter.")
            if password:
                execute(
                    """UPDATE pengguna SET nama=%s,email=%s,nomor_telepon=%s,alamat=%s,aktif=%s,password_hash=%s
                       WHERE id=%s AND role='pelanggan'""",
                    (form["nama"], form["email"], form["nomor_telepon"] or None, form["alamat"] or None,
                     form["aktif"], generate_password_hash(password), pelanggan_id),
                )
            else:
                execute(
                    """UPDATE pengguna SET nama=%s,email=%s,nomor_telepon=%s,alamat=%s,aktif=%s
                       WHERE id=%s AND role='pelanggan'""",
                    (form["nama"], form["email"], form["nomor_telepon"] or None, form["alamat"] or None,
                     form["aktif"], pelanggan_id),
                )
            catat_log("edit_pelanggan", f"Admin mengubah pelanggan {form['email']}.")
            flash("Data pelanggan berhasil diperbarui.", "success")
            return redirect(url_for(('petugas_manage_pelanggan' if request.path.startswith('/petugas/manage') else 'admin_pelanggan')))
        except ValidationError as e:
            flash(str(e), "danger")
        except IntegrityError:
            flash("Email sudah digunakan.", "danger")
    return render_template("admin/pelanggan_edit.html", form=form, pelanggan=row)


@app.route("/admin/pelanggan/<int:pelanggan_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_pelanggan_hapus(pelanggan_id):
    row = query_one("SELECT id,email FROM pengguna WHERE id=%s AND role='pelanggan'", (pelanggan_id,))
    if not row:
        abort(404)
    try:
        execute("DELETE FROM pengguna WHERE id=%s AND role='pelanggan'", (pelanggan_id,))
        catat_log("hapus_pelanggan", f"Admin menghapus pelanggan {row['email']}.")
        flash("Pelanggan berhasil dihapus.", "success")
    except IntegrityError:
        flash("Pelanggan tidak dapat dihapus karena masih memiliki data terkait (registrasi/klaim). Nonaktifkan akun jika perlu.", "danger")
    except Exception:
        app.logger.exception("Gagal hapus pelanggan")
        flash("Gagal menghapus pelanggan.", "danger")
    return redirect(url_for(('petugas_manage_pelanggan' if request.path.startswith('/petugas/manage') else 'admin_pelanggan')))




# ---------------------------------------------------------------------------
# Admin: CRUD Kebijakan Garansi
# ---------------------------------------------------------------------------

@app.route("/admin/kebijakan")
@role_required("admin", "petugas")
def admin_kebijakan():
    q = (request.args.get("q") or "").strip()
    sql = "SELECT * FROM kebijakan_garansi WHERE 1=1"
    params = []
    if q:
        sql += " AND nama LIKE %s"
        params.append(f"%{q}%")
    sql += " ORDER BY durasi_bulan, id"
    rows = query_all(sql, tuple(params))
    return render_template("admin/kebijakan.html", daftar=rows, q=q)

@app.route("/admin/kebijakan/tambah", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_kebijakan_tambah():
    form = {"nama": "", "durasi_bulan": "", "deskripsi": "", "aktif": 1}
    if request.method == "POST":
        form = {"nama": (request.form.get("nama") or "").strip(),
                "durasi_bulan": (request.form.get("durasi_bulan") or "").strip(),
                "deskripsi": (request.form.get("deskripsi") or "").strip(),
                "aktif": 1 if request.form.get("aktif") else 0}
        try:
            if len(form["nama"]) < 3:
                raise ValidationError("Nama kebijakan minimal 3 karakter.")
            if not form["durasi_bulan"].isdigit() or int(form["durasi_bulan"]) < 1:
                raise ValidationError("Durasi bulan harus angka >= 1.")
            execute("INSERT INTO kebijakan_garansi (nama,durasi_bulan,deskripsi,aktif) VALUES (%s,%s,%s,%s)",
                    (form["nama"], int(form["durasi_bulan"]), form["deskripsi"] or None, form["aktif"]))
            catat_log("tambah_kebijakan", f"Menambah kebijakan {form['nama']}.")
            flash("Kebijakan garansi berhasil ditambahkan.", "success")
            return redirect(url_for(('petugas_manage_kebijakan' if request.path.startswith('/petugas/manage') else 'admin_kebijakan')))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/kebijakan_tambah.html", form=form)

@app.route("/admin/kebijakan/edit/<int:kebijakan_id>", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_kebijakan_edit(kebijakan_id):
    row = query_one("SELECT * FROM kebijakan_garansi WHERE id=%s", (kebijakan_id,))
    if not row:
        abort(404)
    form = {"nama": row["nama"], "durasi_bulan": str(row["durasi_bulan"]),
            "deskripsi": row.get("deskripsi") or "", "aktif": int(row["aktif"])}
    if request.method == "POST":
        form = {"nama": (request.form.get("nama") or "").strip(),
                "durasi_bulan": (request.form.get("durasi_bulan") or "").strip(),
                "deskripsi": (request.form.get("deskripsi") or "").strip(),
                "aktif": 1 if request.form.get("aktif") else 0}
        try:
            if len(form["nama"]) < 3:
                raise ValidationError("Nama kebijakan minimal 3 karakter.")
            if not form["durasi_bulan"].isdigit() or int(form["durasi_bulan"]) < 1:
                raise ValidationError("Durasi bulan harus angka >= 1.")
            execute("UPDATE kebijakan_garansi SET nama=%s,durasi_bulan=%s,deskripsi=%s,aktif=%s WHERE id=%s",
                    (form["nama"], int(form["durasi_bulan"]), form["deskripsi"] or None, form["aktif"], kebijakan_id))
            catat_log("edit_kebijakan", f"Mengubah kebijakan {form['nama']}.")
            flash("Kebijakan garansi berhasil diperbarui.", "success")
            return redirect(url_for(('petugas_manage_kebijakan' if request.path.startswith('/petugas/manage') else 'admin_kebijakan')))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/kebijakan_edit.html", form=form, item=row)

@app.route("/admin/kebijakan/<int:kebijakan_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_kebijakan_hapus(kebijakan_id):
    row = query_one("SELECT id,nama FROM kebijakan_garansi WHERE id=%s", (kebijakan_id,))
    if not row:
        abort(404)
    try:
        execute("DELETE FROM kebijakan_garansi WHERE id=%s", (kebijakan_id,))
        catat_log("hapus_kebijakan", f"Menghapus kebijakan {row['nama']}.")
        flash("Kebijakan berhasil dihapus.", "success")
    except IntegrityError:
        flash("Kebijakan tidak dapat dihapus karena masih digunakan produk.", "danger")
    return redirect(url_for(('petugas_manage_kebijakan' if request.path.startswith('/petugas/manage') else 'admin_kebijakan')))


# ---------------------------------------------------------------------------
# Admin: CRUD Produk
# ---------------------------------------------------------------------------

@app.route("/admin/produk")
@role_required("admin", "petugas")
def admin_produk():
    q = (request.args.get("q") or "").strip()
    rows = query_all("""SELECT p.*, kg.nama AS nama_kebijakan, kg.durasi_bulan,
        (SELECT COUNT(*) FROM kode_qr_produk qr WHERE qr.produk_id=p.id) AS jumlah_unit
        FROM produk p JOIN kebijakan_garansi kg ON kg.id=p.kebijakan_garansi_id
        WHERE (%s='' OR p.nama_produk LIKE %s OR p.kategori_model LIKE %s)
        ORDER BY p.dibuat_pada DESC""", (q, f"%{q}%", f"%{q}%"))
    return render_template("admin/produk.html", daftar=rows, q=q)

@app.route("/admin/produk/tambah", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_produk_tambah():
    kebijakan = query_all("SELECT * FROM kebijakan_garansi ORDER BY durasi_bulan")
    form = {"nama_produk": "", "kategori_model": "", "kebijakan_garansi_id": "", "deskripsi": "", "status": "aktif"}
    if request.method == "POST":
        for k in form:
            form[k] = (request.form.get(k) or "").strip()
        try:
            if len(form["nama_produk"]) < 3:
                raise ValidationError("Nama produk minimal 3 karakter.")
            if not form["kategori_model"]:
                raise ValidationError("Kategori/model wajib diisi.")
            if not form["kebijakan_garansi_id"].isdigit():
                raise ValidationError("Kebijakan garansi wajib dipilih.")
            execute("""INSERT INTO produk (nama_produk,kategori_model,kebijakan_garansi_id,deskripsi,status)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (form["nama_produk"], form["kategori_model"], int(form["kebijakan_garansi_id"]),
                     form["deskripsi"] or None, form["status"] if form["status"] in {"aktif","nonaktif"} else "aktif"))
            flash("Produk berhasil ditambahkan.", "success")
            return redirect(url_for(('petugas_manage_produk' if request.path.startswith('/petugas/manage') else 'admin_produk')))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/produk_tambah.html", form=form, kebijakan_list=kebijakan)

@app.route("/admin/produk/edit/<int:produk_id>", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_produk_edit(produk_id):
    row = query_one("SELECT * FROM produk WHERE id=%s", (produk_id,))
    if not row:
        abort(404)
    kebijakan = query_all("SELECT * FROM kebijakan_garansi ORDER BY durasi_bulan")
    form = {"nama_produk": row["nama_produk"], "kategori_model": row["kategori_model"],
            "kebijakan_garansi_id": str(row["kebijakan_garansi_id"]),
            "deskripsi": row.get("deskripsi") or "", "status": row["status"]}
    if request.method == "POST":
        for k in form:
            form[k] = (request.form.get(k) or "").strip()
        try:
            if len(form["nama_produk"]) < 3:
                raise ValidationError("Nama produk minimal 3 karakter.")
            if not form["kebijakan_garansi_id"].isdigit():
                raise ValidationError("Kebijakan garansi wajib dipilih.")
            execute("""UPDATE produk SET nama_produk=%s,kategori_model=%s,kebijakan_garansi_id=%s,deskripsi=%s,status=%s WHERE id=%s""",
                    (form["nama_produk"], form["kategori_model"], int(form["kebijakan_garansi_id"]),
                     form["deskripsi"] or None, form["status"] if form["status"] in {"aktif","nonaktif"} else "aktif", produk_id))
            flash("Produk berhasil diperbarui.", "success")
            return redirect(url_for(('petugas_manage_produk' if request.path.startswith('/petugas/manage') else 'admin_produk')))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/produk_edit.html", form=form, produk=row, kebijakan_list=kebijakan)

@app.route("/admin/produk/<int:produk_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_produk_hapus(produk_id):
    row = query_one("SELECT id,nama_produk FROM produk WHERE id=%s", (produk_id,))
    if not row:
        abort(404)
    try:
        execute("DELETE FROM produk WHERE id=%s", (produk_id,))
        flash("Produk berhasil dihapus.", "success")
    except IntegrityError:
        flash("Produk tidak dapat dihapus karena masih memiliki unit QR/registrasi terkait.", "danger")
    return redirect(url_for(('petugas_manage_produk' if request.path.startswith('/petugas/manage') else 'admin_produk')))

# ---------------------------------------------------------------------------
# Admin: CRUD QR / Unit Produk
# ---------------------------------------------------------------------------

@app.route("/admin/qr")
@role_required("admin", "petugas")
def admin_qr():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    sql = """SELECT qr.*, p.nama_produk, p.kategori_model,
        r.id AS registrasi_id, u.nama AS nama_pelanggan
        FROM kode_qr_produk qr
        JOIN produk p ON p.id=qr.produk_id
        LEFT JOIN registrasi_produk r ON r.kode_qr_id=qr.id AND r.status_registrasi='aktif'
        LEFT JOIN pengguna u ON u.id=r.pelanggan_id
        WHERE 1=1"""
    params = []
    if q:
        sql += " AND (qr.nomor_seri LIKE %s OR qr.token_qr LIKE %s OR p.nama_produk LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if status in {"tersedia", "terdaftar", "nonaktif"}:
        sql += " AND qr.status=%s"
        params.append(status)
    sql += " ORDER BY qr.dibuat_pada DESC LIMIT 500"
    rows = query_all(sql, tuple(params))
    return render_template("admin/qr.html", daftar=rows, q=q, status=status)

@app.route("/admin/qr/tambah", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_qr_tambah():
    produk = query_all("SELECT id,nama_produk FROM produk ORDER BY nama_produk")
    form = {"produk_id": "", "nomor_seri": "", "status": "tersedia"}
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        try:
            if not form["produk_id"].isdigit():
                raise ValidationError("Produk wajib dipilih.")
            prod = query_one("SELECT id FROM produk WHERE id=%s", (int(form["produk_id"]),))
            if not prod:
                raise ValidationError("Produk tidak ditemukan.")
            token = buat_token_qr()
            nomor = form["nomor_seri"] or buat_nomor_seri(int(form["produk_id"]))
            if form["status"] not in {"tersedia", "terdaftar", "nonaktif"}:
                form["status"] = "tersedia"
            execute("INSERT INTO kode_qr_produk (produk_id,nomor_seri,token_qr,status) VALUES (%s,%s,%s,%s)",
                    (int(form["produk_id"]), nomor, token, form["status"]))
            flash("Unit QR berhasil ditambahkan.", "success")
            return redirect(url_for(('petugas_manage_qr' if request.path.startswith('/petugas/manage') else 'admin_qr')))
        except ValidationError as e:
            flash(str(e), "danger")
        except IntegrityError:
            flash("Nomor seri/token sudah digunakan.", "danger")
    return render_template("admin/qr_tambah.html", form=form, produk_list=produk)

@app.route("/admin/qr/edit/<int:qr_id>", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_qr_edit(qr_id):
    row = query_one("SELECT * FROM kode_qr_produk WHERE id=%s", (qr_id,))
    if not row:
        abort(404)
    produk = query_all("SELECT id,nama_produk FROM produk ORDER BY nama_produk")
    form = {"produk_id": str(row["produk_id"]), "nomor_seri": row["nomor_seri"], "status": row["status"]}
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        try:
            if not form["produk_id"].isdigit():
                raise ValidationError("Produk wajib dipilih.")
            if not form["nomor_seri"]:
                raise ValidationError("Nomor seri wajib diisi.")
            if form["status"] not in {"tersedia", "terdaftar", "nonaktif"}:
                form["status"] = "tersedia"
            execute("UPDATE kode_qr_produk SET produk_id=%s, nomor_seri=%s, status=%s WHERE id=%s",
                    (int(form["produk_id"]), form["nomor_seri"], form["status"], qr_id))
            flash("Unit QR berhasil diperbarui.", "success")
            return redirect(url_for(('petugas_manage_qr' if request.path.startswith('/petugas/manage') else 'admin_qr')))
        except ValidationError as e:
            flash(str(e), "danger")
        except IntegrityError:
            flash("Nomor seri sudah digunakan.", "danger")
    return render_template("admin/qr_edit.html", form=form, item=row, produk_list=produk)

@app.route("/admin/qr/<int:qr_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_qr_hapus(qr_id):
    row = query_one("SELECT id,nomor_seri FROM kode_qr_produk WHERE id=%s", (qr_id,))
    if not row:
        abort(404)
    try:
        execute("DELETE FROM kode_qr_produk WHERE id=%s", (qr_id,))
        flash("Unit QR berhasil dihapus.", "success")
    except IntegrityError:
        flash("Unit QR tidak dapat dihapus karena sudah memiliki registrasi terkait.", "danger")
    return redirect(url_for(('petugas_manage_qr' if request.path.startswith('/petugas/manage') else 'admin_qr')))


# ---------------------------------------------------------------------------
# Admin: CRUD Registrasi & Garansi
# ---------------------------------------------------------------------------

@app.route("/admin/registrasi")
@role_required("admin", "petugas")
def admin_registrasi():
    q = (request.args.get("q") or "").strip()
    sql = """SELECT r.*, u.nama AS nama_pelanggan, u.email AS email_pelanggan,
        p.nama_produk, qr.nomor_seri, g.tanggal_berakhir, g.status AS status_garansi
        FROM registrasi_produk r
        JOIN pengguna u ON u.id=r.pelanggan_id
        JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id
        JOIN produk p ON p.id=qr.produk_id
        LEFT JOIN garansi g ON g.registrasi_produk_id=r.id WHERE 1=1"""
    params = []
    if q:
        sql += " AND (u.nama LIKE %s OR p.nama_produk LIKE %s OR qr.nomor_seri LIKE %s OR r.nomor_invoice LIKE %s)"
        params.extend([f"%{q}%"] * 4)
    sql += " ORDER BY r.dibuat_pada DESC LIMIT 500"
    rows = query_all(sql, tuple(params))
    for item in rows:
        item["status_garansi_aktual"] = status_garansi(item.get("tanggal_berakhir"))
    return render_template("admin/registrasi.html", daftar=rows, q=q)

@app.route("/admin/registrasi/edit/<int:registrasi_id>", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_registrasi_edit(registrasi_id):
    row = query_one("""SELECT r.*, u.nama AS nama_pelanggan, p.nama_produk, qr.nomor_seri
        FROM registrasi_produk r JOIN pengguna u ON u.id=r.pelanggan_id
        JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id JOIN produk p ON p.id=qr.produk_id WHERE r.id=%s""", (registrasi_id,))
    if not row:
        abort(404)
    form = {"tanggal_pembelian": str(row["tanggal_pembelian"]), "tempat_pembelian": row["tempat_pembelian"],
            "nomor_invoice": row["nomor_invoice"], "status_registrasi": row["status_registrasi"],
            "catatan_verifikasi": row.get("catatan_verifikasi") or ""}
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        try:
            tgl = parse_tanggal(form["tanggal_pembelian"], "Tanggal pembelian")
            if form["status_registrasi"] not in {"aktif", "dibatalkan"}:
                form["status_registrasi"] = "aktif"
            execute("""UPDATE registrasi_produk SET tanggal_pembelian=%s,tempat_pembelian=%s,nomor_invoice=%s,
                       status_registrasi=%s,catatan_verifikasi=%s,diverifikasi_oleh=%s,diverifikasi_pada=NOW() WHERE id=%s""",
                    (tgl, form["tempat_pembelian"], form["nomor_invoice"], form["status_registrasi"],
                     form["catatan_verifikasi"] or None, g.user["id"], registrasi_id))
            if form["status_registrasi"] == "dibatalkan":
                execute("UPDATE kode_qr_produk SET status='tersedia' WHERE id=%s", (row["kode_qr_id"],))
                execute("UPDATE garansi SET status='dibatalkan' WHERE registrasi_produk_id=%s", (registrasi_id,))
            flash("Registrasi berhasil diperbarui.", "success")
            return redirect(url_for(('petugas_manage_registrasi' if request.path.startswith('/petugas/manage') else 'admin_registrasi')))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/registrasi_edit.html", form=form, item=row)

@app.route("/admin/registrasi/<int:registrasi_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_registrasi_hapus(registrasi_id):
    row = query_one("SELECT id,kode_qr_id FROM registrasi_produk WHERE id=%s", (registrasi_id,))
    if not row:
        abort(404)
    try:
        execute("DELETE FROM garansi WHERE registrasi_produk_id=%s", (registrasi_id,))
        execute("DELETE FROM registrasi_produk WHERE id=%s", (registrasi_id,))
        execute("UPDATE kode_qr_produk SET status='tersedia' WHERE id=%s", (row["kode_qr_id"],))
        flash("Registrasi berhasil dihapus.", "success")
    except IntegrityError:
        flash("Registrasi tidak dapat dihapus karena masih memiliki klaim terkait.", "danger")
    return redirect(url_for(('petugas_manage_registrasi' if request.path.startswith('/petugas/manage') else 'admin_registrasi')))

@app.route("/admin/garansi")
@role_required("admin", "petugas")
def admin_garansi():
    q = (request.args.get("q") or "").strip()
    sql = """SELECT g.*, r.nomor_invoice, u.nama AS nama_pelanggan, p.nama_produk, qr.nomor_seri
        FROM garansi g JOIN registrasi_produk r ON r.id=g.registrasi_produk_id
        JOIN pengguna u ON u.id=r.pelanggan_id JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id
        JOIN produk p ON p.id=qr.produk_id WHERE 1=1"""
    params = []
    if q:
        sql += " AND (u.nama LIKE %s OR p.nama_produk LIKE %s OR qr.nomor_seri LIKE %s)"
        params.extend([f"%{q}%"] * 3)
    sql += " ORDER BY g.dibuat_pada DESC LIMIT 500"
    rows = query_all(sql, tuple(params))
    for item in rows:
        item["status_garansi_aktual"] = status_garansi(item.get("tanggal_berakhir"))
    return render_template("admin/garansi.html", daftar=rows, q=q)

@app.route("/admin/garansi/edit/<int:garansi_id>", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_garansi_edit(garansi_id):
    row = query_one("""SELECT g.*, u.nama AS nama_pelanggan, p.nama_produk, qr.nomor_seri
        FROM garansi g JOIN registrasi_produk r ON r.id=g.registrasi_produk_id
        JOIN pengguna u ON u.id=r.pelanggan_id JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id
        JOIN produk p ON p.id=qr.produk_id WHERE g.id=%s""", (garansi_id,))
    if not row:
        abort(404)
    form = {"tanggal_mulai": str(row["tanggal_mulai"]), "tanggal_berakhir": str(row["tanggal_berakhir"]), "status": row["status"]}
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        try:
            mulai = parse_tanggal(form["tanggal_mulai"], "Tanggal mulai")
            akhir = parse_tanggal(form["tanggal_berakhir"], "Tanggal berakhir")
            if akhir < mulai:
                raise ValidationError("Tanggal berakhir harus >= tanggal mulai.")
            if form["status"] not in {"aktif", "berakhir", "dibatalkan"}:
                form["status"] = "aktif"
            execute("UPDATE garansi SET tanggal_mulai=%s,tanggal_berakhir=%s,status=%s WHERE id=%s",
                    (mulai, akhir, form["status"], garansi_id))
            flash("Garansi berhasil diperbarui.", "success")
            return redirect(url_for(('petugas_manage_garansi' if request.path.startswith('/petugas/manage') else 'admin_garansi')))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/garansi_edit.html", form=form, item=row)

@app.route("/admin/garansi/<int:garansi_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_garansi_hapus(garansi_id):
    execute("DELETE FROM garansi WHERE id=%s", (garansi_id,))
    flash("Garansi berhasil dihapus.", "success")
    return redirect(url_for(('petugas_manage_garansi' if request.path.startswith('/petugas/manage') else 'admin_garansi')))


# ---------------------------------------------------------------------------
# Admin: CRUD Klaim, Servis, Notifikasi, Log
# ---------------------------------------------------------------------------

@app.route("/admin/klaim")
@role_required("admin", "petugas")
def admin_klaim():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    sql = """SELECT k.*, u.nama AS nama_pelanggan, p.nama_produk, qr.nomor_seri
        FROM klaim_garansi k JOIN pengguna u ON u.id=k.pelanggan_id
        JOIN registrasi_produk r ON r.id=k.registrasi_produk_id
        JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id
        JOIN produk p ON p.id=qr.produk_id WHERE 1=1"""
    params = []
    if status in STATUS_KLAIM_LABELS:
        sql += " AND k.status=%s"; params.append(status)
    if q:
        sql += " AND (u.nama LIKE %s OR p.nama_produk LIKE %s OR qr.nomor_seri LIKE %s)"
        params.extend([f"%{q}%"] * 3)
    sql += " ORDER BY k.tanggal_klaim DESC LIMIT 500"
    rows = query_all(sql, tuple(params))
    return render_template("admin/klaim.html", daftar=rows, q=q, status=status)

@app.route("/admin/klaim/edit/<int:klaim_id>", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_klaim_edit(klaim_id):
    row = query_one("""SELECT k.*, u.nama AS nama_pelanggan, p.nama_produk, qr.nomor_seri
        FROM klaim_garansi k JOIN pengguna u ON u.id=k.pelanggan_id
        JOIN registrasi_produk r ON r.id=k.registrasi_produk_id
        JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id JOIN produk p ON p.id=qr.produk_id WHERE k.id=%s""", (klaim_id,))
    if not row:
        abort(404)
    form = {"status": row["status"], "deskripsi_masalah": row["deskripsi_masalah"], "alasan_penolakan": row.get("alasan_penolakan") or ""}
    if request.method == "POST":
        form = {"status": (request.form.get("status") or "").strip(),
                "deskripsi_masalah": (request.form.get("deskripsi_masalah") or "").strip(),
                "alasan_penolakan": (request.form.get("alasan_penolakan") or "").strip()}
        try:
            if form["status"] not in STATUS_KLAIM_LABELS:
                raise ValidationError("Status klaim tidak valid.")
            if len(form["deskripsi_masalah"]) < 10:
                raise ValidationError("Deskripsi masalah minimal 10 karakter.")
            if form["status"] == "ditolak" and not form["alasan_penolakan"]:
                raise ValidationError("Alasan penolakan wajib diisi untuk status ditolak.")
            execute("""UPDATE klaim_garansi SET status=%s, deskripsi_masalah=%s, alasan_penolakan=%s, diproses_oleh=%s, tanggal_verifikasi=COALESCE(tanggal_verifikasi,NOW()) WHERE id=%s""",
                    (form["status"], form["deskripsi_masalah"], form["alasan_penolakan"] if form["status"] == "ditolak" else None, g.user["id"], klaim_id))
            flash("Klaim berhasil diperbarui.", "success")
            return redirect(url_for(('petugas_manage_klaim' if request.path.startswith('/petugas/manage') else 'admin_klaim')))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/klaim_edit.html", form=form, item=row)

@app.route("/admin/klaim/<int:klaim_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_klaim_hapus(klaim_id):
    try:
        execute("DELETE FROM klaim_garansi WHERE id=%s", (klaim_id,))
        flash("Klaim berhasil dihapus.", "success")
    except Exception:
        app.logger.exception("Gagal hapus klaim")
        flash("Gagal menghapus klaim.", "danger")
    return redirect(url_for(('petugas_manage_klaim' if request.path.startswith('/petugas/manage') else 'admin_klaim')))

@app.route("/admin/servis")
@role_required("admin", "petugas")
def admin_servis():
    klaim_id = (request.args.get("klaim_id") or "").strip()
    sql = """SELECT cs.*, k.status AS status_klaim, u.nama AS nama_petugas, p.nama_produk, qr.nomor_seri
        FROM catatan_servis cs JOIN klaim_garansi k ON k.id=cs.klaim_id
        JOIN registrasi_produk r ON r.id=k.registrasi_produk_id
        JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id JOIN produk p ON p.id=qr.produk_id
        LEFT JOIN pengguna u ON u.id=cs.petugas_id WHERE 1=1"""
    params = []
    if klaim_id.isdigit():
        sql += " AND cs.klaim_id=%s"; params.append(int(klaim_id))
    sql += " ORDER BY cs.dibuat_pada DESC LIMIT 500"
    return render_template("admin/servis.html", daftar=query_all(sql, tuple(params)), klaim_id=klaim_id)

@app.route("/admin/servis/tambah", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_servis_tambah():
    klaim_list = query_all("SELECT k.id, p.nama_produk, qr.nomor_seri FROM klaim_garansi k JOIN registrasi_produk r ON r.id=k.registrasi_produk_id JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id JOIN produk p ON p.id=qr.produk_id ORDER BY k.id DESC LIMIT 300")
    form = {"klaim_id": (request.args.get("klaim_id") or "").strip(), "hasil_pemeriksaan": "", "tindakan_perbaikan": "", "komponen_diganti": "", "penggantian_produk": "0", "catatan_tambahan": "", "tanggal_proses": ""}
    if request.method == "POST":
        for k in form:
            form[k] = (request.form.get(k) or "").strip()
        try:
            if not form["klaim_id"].isdigit():
                raise ValidationError("Klaim wajib dipilih.")
            tgl = parse_tanggal_opsional(form["tanggal_proses"]) or date.today()
            execute("""INSERT INTO catatan_servis (klaim_id,petugas_id,hasil_pemeriksaan,tindakan_perbaikan,komponen_diganti,penggantian_produk,catatan_tambahan,tanggal_proses)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (int(form["klaim_id"]), g.user["id"], form["hasil_pemeriksaan"] or None, form["tindakan_perbaikan"] or None,
                     form["komponen_diganti"] or None, 1 if form["penggantian_produk"] == "1" else 0, form["catatan_tambahan"] or None, tgl))
            flash("Catatan servis berhasil ditambahkan.", "success")
            return redirect(url_for("admin_servis", klaim_id=form["klaim_id"]))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/servis_tambah.html", form=form, klaim_list=klaim_list)

@app.route("/admin/servis/edit/<int:servis_id>", methods=["GET", "POST"])
@role_required("admin", "petugas")
def admin_servis_edit(servis_id):
    row = query_one("SELECT * FROM catatan_servis WHERE id=%s", (servis_id,))
    if not row:
        abort(404)
    klaim_list = query_all("SELECT k.id, p.nama_produk, qr.nomor_seri FROM klaim_garansi k JOIN registrasi_produk r ON r.id=k.registrasi_produk_id JOIN kode_qr_produk qr ON qr.id=r.kode_qr_id JOIN produk p ON p.id=qr.produk_id ORDER BY k.id DESC LIMIT 300")
    form = {"klaim_id": str(row["klaim_id"]), "hasil_pemeriksaan": row.get("hasil_pemeriksaan") or "", "tindakan_perbaikan": row.get("tindakan_perbaikan") or "",
            "komponen_diganti": row.get("komponen_diganti") or "", "penggantian_produk": str(int(row.get("penggantian_produk") or 0)),
            "catatan_tambahan": row.get("catatan_tambahan") or "", "tanggal_proses": str(row["tanggal_proses"]) if row.get("tanggal_proses") else ""}
    if request.method == "POST":
        for k in form:
            form[k] = (request.form.get(k) or "").strip()
        try:
            if not form["klaim_id"].isdigit():
                raise ValidationError("Klaim wajib dipilih.")
            tgl = parse_tanggal_opsional(form["tanggal_proses"])
            execute("""UPDATE catatan_servis SET klaim_id=%s,hasil_pemeriksaan=%s,tindakan_perbaikan=%s,komponen_diganti=%s,penggantian_produk=%s,catatan_tambahan=%s,tanggal_proses=%s WHERE id=%s""",
                    (int(form["klaim_id"]), form["hasil_pemeriksaan"] or None, form["tindakan_perbaikan"] or None,
                     form["komponen_diganti"] or None, 1 if form["penggantian_produk"] == "1" else 0, form["catatan_tambahan"] or None, tgl, servis_id))
            flash("Catatan servis berhasil diperbarui.", "success")
            return redirect(url_for("admin_servis", klaim_id=form["klaim_id"]))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("admin/servis_edit.html", form=form, item=row, klaim_list=klaim_list)

@app.route("/admin/servis/<int:servis_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_servis_hapus(servis_id):
    row = query_one("SELECT id,klaim_id FROM catatan_servis WHERE id=%s", (servis_id,))
    if row:
        execute("DELETE FROM catatan_servis WHERE id=%s", (servis_id,))
        flash("Catatan servis berhasil dihapus.", "success")
        return redirect(url_for("admin_servis", klaim_id=row["klaim_id"]))
    abort(404)

@app.route("/admin/notifikasi")
@role_required("admin", "petugas")
def admin_notifikasi():
    q = (request.args.get("q") or "").strip()
    sql = """SELECT n.*, u.nama AS nama_pengguna, u.email FROM notifikasi n JOIN pengguna u ON u.id=n.pengguna_id WHERE 1=1"""
    params = []
    if q:
        sql += " AND (u.nama LIKE %s OR u.email LIKE %s OR n.judul LIKE %s)"
        params.extend([f"%{q}%"] * 3)
    sql += " ORDER BY n.dibuat_pada DESC LIMIT 500"
    return render_template("admin/notifikasi.html", daftar=query_all(sql, tuple(params)), q=q)

@app.route("/admin/notifikasi/<int:notif_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_notifikasi_hapus(notif_id):
    execute("DELETE FROM notifikasi WHERE id=%s", (notif_id,))
    flash("Notifikasi berhasil dihapus.", "success")
    return redirect(url_for(('petugas_manage_notifikasi' if request.path.startswith('/petugas/manage') else 'admin_notifikasi')))

@app.route("/admin/log")
@role_required("admin", "petugas")
def admin_log():
    q = (request.args.get("q") or "").strip()
    sql = """SELECT l.*, u.nama AS nama_pengguna, u.role, u.email FROM log_aktivitas l LEFT JOIN pengguna u ON u.id=l.pengguna_id WHERE 1=1"""
    params = []
    if q:
        sql += " AND (l.aksi LIKE %s OR l.deskripsi LIKE %s OR u.nama LIKE %s)"
        params.extend([f"%{q}%"] * 3)
    sql += " ORDER BY l.dibuat_pada DESC LIMIT 500"
    return render_template("admin/log.html", daftar=query_all(sql, tuple(params)), q=q)

@app.route("/admin/log/<int:log_id>/hapus", methods=["POST"])
@role_required("admin", "petugas")
def admin_log_hapus(log_id):
    execute("DELETE FROM log_aktivitas WHERE id=%s", (log_id,))
    flash("Log berhasil dihapus.", "success")
    return redirect(url_for(('petugas_manage_log' if request.path.startswith('/petugas/manage') else 'admin_log')))


# ---------------------------------------------------------------------------
# Route petugas
# ---------------------------------------------------------------------------


@app.route("/petugas/dashboard")
@role_required("petugas")
def petugas_dashboard():
    stats = {
        "total_produk": scalar("SELECT COUNT(*) FROM produk"),
        "total_pelanggan": scalar(
            "SELECT COUNT(*) FROM pengguna WHERE role = 'pelanggan'"
        ),
        "total_registrasi": scalar(
            "SELECT COUNT(*) FROM registrasi_produk WHERE status_registrasi = 'aktif'"
        ),
        "total_unit_qr": scalar("SELECT COUNT(*) FROM kode_qr_produk"),
        "total_klaim": scalar("SELECT COUNT(*) FROM klaim_garansi"),
    }
    status_counts = hitung_status_klaim()
    klaim_terbaru = query_all(
        """
        SELECT
            k.id,
            k.status,
            k.tanggal_klaim,
            u.nama AS nama_pelanggan,
            p.nama_produk,
            q.nomor_seri
        FROM klaim_garansi k
        JOIN pengguna u ON u.id = k.pelanggan_id
        JOIN registrasi_produk r ON r.id = k.registrasi_produk_id
        JOIN kode_qr_produk q ON q.id = r.kode_qr_id
        JOIN produk p ON p.id = q.produk_id
        ORDER BY k.tanggal_klaim DESC
        LIMIT 8
        """
    )
    daftar_produk_dashboard = query_all(
        """
        SELECT p.id, p.nama_produk, p.kategori_model, p.status, p.dibuat_pada,
               kg.nama AS nama_kebijakan
        FROM produk p
        JOIN kebijakan_garansi kg ON kg.id = p.kebijakan_garansi_id
        ORDER BY p.dibuat_pada DESC
        LIMIT 5
        """
    )
    return render_template(
        "petugas/dashboard.html",
        stats=stats,
        status_counts=status_counts,
        klaim_terbaru=klaim_terbaru,
        daftar_produk_dashboard=daftar_produk_dashboard,
    )


@app.route("/petugas/dashboard/produk/<int:produk_id>/toggle", methods=["POST"])
@role_required("petugas")
def petugas_dashboard_produk_toggle(produk_id):
    produk = query_one("SELECT id, nama_produk, status FROM produk WHERE id = %s", (produk_id,))
    if not produk:
        abort(404)

    status_baru = "nonaktif" if produk["status"] == "aktif" else "aktif"
    execute("UPDATE produk SET status = %s WHERE id = %s", (status_baru, produk_id))
    catat_log(
        "toggle_produk_dashboard",
        f"Produk {produk['nama_produk']} diubah menjadi {status_baru} dari dashboard.",
    )
    flash(f"Produk berhasil diubah menjadi {status_baru}.", "success")
    return redirect(url_for("petugas_dashboard"))


@app.route("/petugas/produk")
@role_required("petugas")
def petugas_produk():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()

    sql = """
        SELECT
            p.*,
            kg.nama AS nama_kebijakan,
            kg.durasi_bulan,
            (SELECT COUNT(*) FROM kode_qr_produk qr WHERE qr.produk_id = p.id) AS jumlah_unit,
            (SELECT COUNT(*) FROM kode_qr_produk qr WHERE qr.produk_id = p.id AND qr.status = 'terdaftar') AS jumlah_terdaftar
        FROM produk p
        JOIN kebijakan_garansi kg ON kg.id = p.kebijakan_garansi_id
        WHERE 1 = 1
    """
    params = []
    if q:
        sql += " AND (p.nama_produk LIKE %s OR p.kategori_model LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    if status in {"aktif", "nonaktif"}:
        sql += " AND p.status = %s"
        params.append(status)
    sql += " ORDER BY p.dibuat_pada DESC"

    daftar_produk = query_all(sql, tuple(params))
    return render_template(
        "petugas/produk.html",
        daftar_produk=daftar_produk,
        q=q,
        status=status,
    )


@app.route("/petugas/produk/tambah", methods=["GET", "POST"])
@role_required("petugas")
def petugas_produk_tambah():
    kebijakan_list = query_all(
        "SELECT * FROM kebijakan_garansi WHERE aktif = 1 ORDER BY durasi_bulan"
    )
    form = {
        "nama_produk": "",
        "kategori_model": "",
        "kebijakan_garansi_id": "",
        "deskripsi": "",
        "status": "aktif",
    }

    if request.method == "POST":
        form.update(
            {
                "nama_produk": (request.form.get("nama_produk") or "").strip(),
                "kategori_model": (request.form.get("kategori_model") or "").strip(),
                "kebijakan_garansi_id": (request.form.get("kebijakan_garansi_id") or "").strip(),
                "deskripsi": (request.form.get("deskripsi") or "").strip(),
                "status": (request.form.get("status") or "aktif").strip(),
            }
        )
        try:
            if len(form["nama_produk"]) < 3:
                raise ValidationError("Nama produk minimal 3 karakter.")
            if not form["kategori_model"]:
                raise ValidationError("Kategori/model wajib diisi.")
            if form["status"] not in {"aktif", "nonaktif"}:
                raise ValidationError("Status produk tidak valid.")
            if not form["kebijakan_garansi_id"]:
                raise ValidationError("Kebijakan garansi wajib dipilih.")
            kebijakan = query_one(
                "SELECT id FROM kebijakan_garansi WHERE id = %s AND aktif = 1",
                (form["kebijakan_garansi_id"],),
            )
            if not kebijakan:
                raise ValidationError("Kebijakan garansi tidak ditemukan atau nonaktif.")

            execute(
                """
                INSERT INTO produk
                    (nama_produk, kategori_model, kebijakan_garansi_id, deskripsi, status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    form["nama_produk"],
                    form["kategori_model"],
                    form["kebijakan_garansi_id"],
                    form["deskripsi"] or None,
                    form["status"],
                ),
            )
        except ValidationError as exc:
            flash(str(exc), "danger")
            return render_template(
                "petugas/produk_tambah.html",
                form=form,
                kebijakan_list=kebijakan_list,
            )

        catat_log("tambah_produk", f"Menambahkan produk {form['nama_produk']}.")
        flash("Produk berhasil ditambahkan.", "success")
        return redirect(url_for("petugas_produk"))

    return render_template(
        "petugas/produk_tambah.html", form=form, kebijakan_list=kebijakan_list
    )


@app.route("/petugas/produk/edit/<int:produk_id>", methods=["GET", "POST"])
@role_required("petugas")
def petugas_produk_edit(produk_id):
    produk = query_one("SELECT * FROM produk WHERE id = %s", (produk_id,))
    if not produk:
        abort(404)

    kebijakan_list = query_all(
        "SELECT * FROM kebijakan_garansi WHERE aktif = 1 OR id = %s ORDER BY durasi_bulan",
        (produk["kebijakan_garansi_id"],),
    )
    form = {
        "nama_produk": produk["nama_produk"],
        "kategori_model": produk["kategori_model"],
        "kebijakan_garansi_id": str(produk["kebijakan_garansi_id"]),
        "deskripsi": produk["deskripsi"] or "",
        "status": produk["status"],
    }

    if request.method == "POST":
        form.update(
            {
                "nama_produk": (request.form.get("nama_produk") or "").strip(),
                "kategori_model": (request.form.get("kategori_model") or "").strip(),
                "kebijakan_garansi_id": (request.form.get("kebijakan_garansi_id") or "").strip(),
                "deskripsi": (request.form.get("deskripsi") or "").strip(),
                "status": (request.form.get("status") or "aktif").strip(),
            }
        )
        try:
            if len(form["nama_produk"]) < 3:
                raise ValidationError("Nama produk minimal 3 karakter.")
            if not form["kategori_model"]:
                raise ValidationError("Kategori/model wajib diisi.")
            if form["status"] not in {"aktif", "nonaktif"}:
                raise ValidationError("Status produk tidak valid.")
            if not form["kebijakan_garansi_id"]:
                raise ValidationError("Kebijakan garansi wajib dipilih.")
            kebijakan = query_one(
                "SELECT id FROM kebijakan_garansi WHERE id = %s AND aktif = 1",
                (form["kebijakan_garansi_id"],),
            )
            if not kebijakan:
                raise ValidationError("Kebijakan garansi tidak ditemukan atau nonaktif.")

            execute(
                """
                UPDATE produk
                SET nama_produk = %s, kategori_model = %s, kebijakan_garansi_id = %s,
                    deskripsi = %s, status = %s
                WHERE id = %s
                """,
                (
                    form["nama_produk"],
                    form["kategori_model"],
                    form["kebijakan_garansi_id"],
                    form["deskripsi"] or None,
                    form["status"],
                    produk_id,
                ),
            )
        except ValidationError as exc:
            flash(str(exc), "danger")
            return render_template(
                "petugas/produk_edit.html",
                form=form,
                produk=produk,
                kebijakan_list=kebijakan_list,
            )

        catat_log("edit_produk", f"Mengubah produk {form['nama_produk']}.")
        flash("Produk berhasil diperbarui.", "success")
        return redirect(url_for("petugas_produk"))

    return render_template(
        "petugas/produk_edit.html",
        form=form,
        produk=produk,
        kebijakan_list=kebijakan_list,
    )


@app.route("/petugas/produk/<int:produk_id>/toggle", methods=["POST"])
@role_required("petugas")
def petugas_produk_toggle(produk_id):
    produk = query_one("SELECT * FROM produk WHERE id = %s", (produk_id,))
    if not produk:
        abort(404)

    status_baru = "nonaktif" if produk["status"] == "aktif" else "aktif"
    execute("UPDATE produk SET status = %s WHERE id = %s", (status_baru, produk_id))
    catat_log(
        "toggle_produk",
        f"Produk {produk['nama_produk']} diubah menjadi {status_baru}.",
    )
    flash(f"Produk berhasil diubah menjadi {status_baru}.", "success")
    return redirect(url_for("petugas_produk"))


@app.route("/petugas/produk/<int:produk_id>/hapus", methods=["POST"])
@role_required("petugas")
def petugas_produk_hapus(produk_id):
    produk = query_one("SELECT id, nama_produk FROM produk WHERE id = %s", (produk_id,))
    if not produk:
        abort(404)
    try:
        execute("DELETE FROM produk WHERE id = %s", (produk_id,))
        catat_log("hapus_produk", f"Petugas menghapus produk {produk['nama_produk']}.")
        flash("Produk berhasil dihapus.", "success")
    except IntegrityError:
        flash("Produk tidak dapat dihapus karena masih memiliki unit QR/registrasi terkait.", "danger")
    return redirect(url_for("petugas_produk"))


@app.route("/petugas/qr")
@role_required("petugas")
def petugas_qr():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    produk_id = (request.args.get("produk_id") or "").strip()

    sql = """
        SELECT
            qr.*,
            p.nama_produk,
            p.kategori_model,
            r.id AS registrasi_id,
            u.nama AS nama_pelanggan,
            g.tanggal_berakhir
        FROM kode_qr_produk qr
        JOIN produk p ON p.id = qr.produk_id
        LEFT JOIN registrasi_produk r
            ON r.kode_qr_id = qr.id AND r.status_registrasi = 'aktif'
        LEFT JOIN pengguna u ON u.id = r.pelanggan_id
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        WHERE 1 = 1
    """
    params = []
    if q:
        sql += " AND (qr.nomor_seri LIKE %s OR qr.token_qr LIKE %s OR p.nama_produk LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if status in {"tersedia", "terdaftar", "nonaktif"}:
        sql += " AND qr.status = %s"
        params.append(status)
    if produk_id.isdigit():
        sql += " AND qr.produk_id = %s"
        params.append(int(produk_id))
    sql += " ORDER BY qr.dibuat_pada DESC LIMIT 500"

    daftar_qr = query_all(sql, tuple(params))
    for item in daftar_qr:
        item["status_garansi_aktual"] = status_garansi(item.get("tanggal_berakhir"))

    produk_list = query_all(
        "SELECT id, nama_produk FROM produk ORDER BY nama_produk"
    )
    return render_template(
        "petugas/qr.html",
        daftar_qr=daftar_qr,
        produk_list=produk_list,
        q=q,
        status=status,
        produk_id=produk_id,
    )


@app.route("/petugas/qr/generate", methods=["GET", "POST"])
@role_required("petugas")
def petugas_qr_generate():
    produk_list = query_all(
        "SELECT id, nama_produk, kategori_model FROM produk WHERE status = 'aktif' ORDER BY nama_produk"
    )
    form = {"produk_id": "", "jumlah": "1"}

    if request.method == "POST":
        form.update(
            {
                "produk_id": (request.form.get("produk_id") or "").strip(),
                "jumlah": (request.form.get("jumlah") or "1").strip(),
            }
        )
        try:
            if not form["produk_id"].isdigit():
                raise ValidationError("Produk wajib dipilih.")
            if not form["jumlah"].isdigit():
                raise ValidationError("Jumlah QR harus berupa angka bulat.")
            jumlah = int(form["jumlah"])
            if jumlah < 1 or jumlah > 50:
                raise ValidationError("Jumlah QR harus antara 1 sampai 50.")
            produk = query_one(
                "SELECT * FROM produk WHERE id = %s AND status = 'aktif'",
                (int(form["produk_id"]),),
            )
            if not produk:
                raise ValidationError("Produk tidak ditemukan atau nonaktif.")

            db = get_db()
            cursor = db.cursor(dictionary=True)
            try:
                dibuat = []
                for _ in range(jumlah):
                    token = None
                    nomor_seri = None
                    for _percobaan in range(20):
                        kandidat_token = buat_token_qr()
                        cursor.execute(
                            "SELECT id FROM kode_qr_produk WHERE token_qr = %s",
                            (kandidat_token,),
                        )
                        if cursor.fetchone():
                            continue
                        kandidat_seri = buat_nomor_seri(produk["id"])
                        cursor.execute(
                            "SELECT id FROM kode_qr_produk WHERE nomor_seri = %s",
                            (kandidat_seri,),
                        )
                        if cursor.fetchone():
                            continue
                        token = kandidat_token
                        nomor_seri = kandidat_seri
                        break
                    if not token or not nomor_seri:
                        raise ValidationError(
                            "Gagal membuat token unik. Silakan coba lagi."
                        )
                    cursor.execute(
                        """
                        INSERT INTO kode_qr_produk (produk_id, nomor_seri, token_qr, status)
                        VALUES (%s, %s, %s, 'tersedia')
                        """,
                        (produk["id"], nomor_seri, token),
                    )
                    dibuat.append(nomor_seri)
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.close()
        except (ValidationError, ValueError) as exc:
            flash(str(exc), "danger")
            return render_template(
                "petugas/qr_generate.html", form=form, produk_list=produk_list
            )

        catat_log(
            "generate_qr",
            f"Membuat {len(dibuat)} QR untuk produk {produk['nama_produk']}.",
        )
        flash(f"{len(dibuat)} QR Code berhasil dibuat.", "success")
        return redirect(url_for("petugas_qr", produk_id=produk["id"]))

    return render_template(
        "petugas/qr_generate.html", form=form, produk_list=produk_list
    )


@app.route("/petugas/registrasi")
@role_required("petugas")
def petugas_registrasi():
    q = (request.args.get("q") or "").strip()
    sql = """
        SELECT
            r.*,
            u.nama AS nama_pelanggan,
            u.email AS email_pelanggan,
            u.nomor_telepon AS telepon_pelanggan,
            p.nama_produk,
            p.kategori_model,
            qr.nomor_seri,
            qr.token_qr,
            g.tanggal_mulai,
            g.tanggal_berakhir,
            g.status AS status_garansi
        FROM registrasi_produk r
        JOIN pengguna u ON u.id = r.pelanggan_id
        JOIN kode_qr_produk qr ON qr.id = r.kode_qr_id
        JOIN produk p ON p.id = qr.produk_id
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        WHERE r.status_registrasi = 'aktif'
    """
    params = []
    if q:
        sql += " AND (u.nama LIKE %s OR u.email LIKE %s OR p.nama_produk LIKE %s OR qr.nomor_seri LIKE %s OR r.nomor_invoice LIKE %s)"
        params.extend([f"%{q}%"] * 5)
    sql += " ORDER BY r.dibuat_pada DESC LIMIT 500"

    daftar_registrasi = query_all(sql, tuple(params))
    for item in daftar_registrasi:
        item["status_garansi_aktual"] = status_garansi(item.get("tanggal_berakhir"))

    return render_template(
        "petugas/registrasi.html", daftar_registrasi=daftar_registrasi, q=q
    )


@app.route("/petugas/pelanggan")
@role_required("petugas")
def petugas_pelanggan():
    q = (request.args.get("q") or "").strip()
    sql = """
        SELECT
            u.*,
            (SELECT COUNT(*) FROM registrasi_produk r
             WHERE r.pelanggan_id = u.id AND r.status_registrasi = 'aktif') AS total_registrasi,
            (SELECT COUNT(*) FROM klaim_garansi k WHERE k.pelanggan_id = u.id) AS total_klaim
        FROM pengguna u
        WHERE u.role = 'pelanggan'
    """
    params = []
    if q:
        sql += " AND (u.nama LIKE %s OR u.email LIKE %s OR u.nomor_telepon LIKE %s)"
        params.extend([f"%{q}%"] * 3)
    sql += " ORDER BY u.dibuat_pada DESC"

    daftar_pelanggan = query_all(sql, tuple(params))
    return render_template(
        "petugas/pelanggan.html", daftar_pelanggan=daftar_pelanggan, q=q
    )


@app.route("/petugas/klaim")
@role_required("petugas")
def petugas_klaim():
    status = (request.args.get("status") or "").strip()
    q = (request.args.get("q") or "").strip()

    sql = """
        SELECT
            k.*,
            u.nama AS nama_pelanggan,
            u.email AS email_pelanggan,
            p.nama_produk,
            qr.nomor_seri,
            g.tanggal_berakhir
        FROM klaim_garansi k
        JOIN pengguna u ON u.id = k.pelanggan_id
        JOIN registrasi_produk r ON r.id = k.registrasi_produk_id
        JOIN kode_qr_produk qr ON qr.id = r.kode_qr_id
        JOIN produk p ON p.id = qr.produk_id
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        WHERE 1 = 1
    """
    params = []
    if status in STATUS_KLAIM_LABELS:
        sql += " AND k.status = %s"
        params.append(status)
    if q:
        sql += " AND (u.nama LIKE %s OR u.email LIKE %s OR p.nama_produk LIKE %s OR qr.nomor_seri LIKE %s)"
        params.extend([f"%{q}%"] * 4)
    sql += " ORDER BY k.tanggal_klaim DESC LIMIT 500"

    daftar_klaim = query_all(sql, tuple(params))
    for item in daftar_klaim:
        item["status_garansi_aktual"] = status_garansi(item.get("tanggal_berakhir"))

    status_counts = hitung_status_klaim()
    return render_template(
        "petugas/klaim.html",
        daftar_klaim=daftar_klaim,
        status_counts=status_counts,
        status=status,
        q=q,
    )


@app.route("/petugas/klaim/<int:klaim_id>")
@role_required("petugas")
def petugas_klaim_detail(klaim_id):
    klaim = query_one(
        """
        SELECT
            k.*,
            u.nama AS nama_pelanggan,
            u.email AS email_pelanggan,
            u.nomor_telepon AS telepon_pelanggan,
            u.alamat AS alamat_pelanggan,
            p.nama_produk,
            p.kategori_model,
            qr.nomor_seri,
            qr.token_qr,
            r.id AS registrasi_id,
            r.tanggal_pembelian,
            r.tempat_pembelian,
            r.nomor_invoice,
            r.bukti_pembelian,
            g.tanggal_mulai,
            g.tanggal_berakhir,
            g.status AS status_garansi_tersimpan,
            pt.nama AS nama_petugas
        FROM klaim_garansi k
        JOIN pengguna u ON u.id = k.pelanggan_id
        JOIN registrasi_produk r ON r.id = k.registrasi_produk_id
        JOIN kode_qr_produk qr ON qr.id = r.kode_qr_id
        JOIN produk p ON p.id = qr.produk_id
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        LEFT JOIN pengguna pt ON pt.id = k.diproses_oleh
        WHERE k.id = %s
        """,
        (klaim_id,),
    )
    if not klaim:
        abort(404)

    klaim["status_garansi_aktual"] = status_garansi(klaim.get("tanggal_berakhir"))
    lampiran = query_all(
        "SELECT * FROM lampiran_klaim WHERE klaim_id = %s ORDER BY id",
        (klaim_id,),
    )
    riwayat = query_all(
        """
        SELECT rs.*, u.nama AS nama_pengguna, u.role
        FROM riwayat_status_klaim rs
        LEFT JOIN pengguna u ON u.id = rs.diubah_oleh
        WHERE rs.klaim_id = %s
        ORDER BY rs.dibuat_pada ASC, rs.id ASC
        """,
        (klaim_id,),
    )
    catatan_servis = query_all(
        """
        SELECT cs.*, u.nama AS nama_petugas
        FROM catatan_servis cs
        LEFT JOIN pengguna u ON u.id = cs.petugas_id
        WHERE cs.klaim_id = %s
        ORDER BY cs.dibuat_pada DESC, cs.id DESC
        """,
        (klaim_id,),
    )

    return render_template(
        "petugas/klaim_detail.html",
        klaim=klaim,
        lampiran=lampiran,
        riwayat=riwayat,
        catatan_servis=catatan_servis,
        allowed_transitions=TRANSISI_STATUS.get(klaim["status"], []),
    )


@app.route("/petugas/klaim/<int:klaim_id>/status", methods=["POST"])
@role_required("petugas")
def petugas_klaim_status(klaim_id):
    klaim = query_one(
        "SELECT * FROM klaim_garansi WHERE id = %s", (klaim_id,)
    )
    if not klaim:
        abort(404)

    status_baru = (request.form.get("status") or "").strip()
    alasan = (request.form.get("alasan_penolakan") or "").strip()
    catatan = (request.form.get("catatan") or "").strip()
    hasil_pemeriksaan = (request.form.get("hasil_pemeriksaan") or "").strip()
    tindakan_perbaikan = (request.form.get("tindakan_perbaikan") or "").strip()
    komponen_diganti = (request.form.get("komponen_diganti") or "").strip()
    penggantian_produk = 1 if request.form.get("penggantian_produk") else 0
    catatan_tambahan = (request.form.get("catatan_tambahan") or "").strip()
    tanggal_proses_raw = (request.form.get("tanggal_proses") or "").strip()

    allowed = TRANSISI_STATUS.get(klaim["status"], [])
    if status_baru not in allowed:
        flash(
            "Perubahan status tidak diizinkan dari status saat ini.", "danger"
        )
        return redirect(url_for("petugas_klaim_detail", klaim_id=klaim_id))

    if status_baru == "ditolak" and not alasan:
        flash("Alasan penolakan wajib diisi.", "danger")
        return redirect(url_for("petugas_klaim_detail", klaim_id=klaim_id))

    tanggal_proses = parse_tanggal_opsional(tanggal_proses_raw) or date.today()

    judul_notif, pesan_notif = pesan_notifikasi_status(
        klaim_id, status_baru, alasan if status_baru == "ditolak" else None
    )
    catatan_riwayat = catatan or STATUS_KLAIM_LABELS.get(status_baru, status_baru)

    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            UPDATE klaim_garansi
            SET status = %s,
                alasan_penolakan = %s,
                diproses_oleh = %s,
                tanggal_verifikasi = COALESCE(tanggal_verifikasi, NOW())
            WHERE id = %s
            """,
            (
                status_baru,
                alasan if status_baru == "ditolak" else klaim.get("alasan_penolakan"),
                g.user["id"],
                klaim_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO riwayat_status_klaim
                (klaim_id, status_sebelumnya, status_baru, diubah_oleh, catatan)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                klaim_id,
                klaim["status"],
                status_baru,
                g.user["id"],
                catatan_riwayat,
            ),
        )

        perlu_catatan_servis = any(
            [
                hasil_pemeriksaan,
                tindakan_perbaikan,
                komponen_diganti,
                catatan_tambahan,
                penggantian_produk,
            ]
        ) or status_baru in {"dalam_perbaikan", "selesai"}
        if perlu_catatan_servis:
            cursor.execute(
                """
                INSERT INTO catatan_servis
                    (klaim_id, petugas_id, hasil_pemeriksaan, tindakan_perbaikan,
                     komponen_diganti, penggantian_produk, catatan_tambahan, tanggal_proses)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    klaim_id,
                    g.user["id"],
                    hasil_pemeriksaan or None,
                    tindakan_perbaikan or None,
                    komponen_diganti or None,
                    penggantian_produk,
                    catatan_tambahan or None,
                    tanggal_proses,
                ),
            )

        tambah_notifikasi(
            cursor,
            klaim["pelanggan_id"],
            klaim_id,
            judul_notif,
            pesan_notif,
        )
        db.commit()
    except Exception:
        db.rollback()
        app.logger.exception("Gagal memperbarui status klaim %s.", klaim_id)
        flash("Gagal memperbarui status klaim. Silakan coba lagi.", "danger")
        return redirect(url_for("petugas_klaim_detail", klaim_id=klaim_id))
    finally:
        cursor.close()

    catat_log(
        "ubah_status_klaim",
        f"Klaim #{klaim_id}: {klaim['status']} -> {status_baru}.",
    )
    flash("Status klaim berhasil diperbarui.", "success")
    return redirect(url_for("petugas_klaim_detail", klaim_id=klaim_id))


# ---------------------------------------------------------------------------
# Route pelanggan
# ---------------------------------------------------------------------------


@app.route("/pelanggan/scan")
@role_required("pelanggan")
def pelanggan_scan():
    """Halaman scan QR / input token untuk registrasi produk atau klaim garansi."""
    return render_template("pelanggan/scan.html")


@app.route("/pelanggan/scan/cari", methods=["POST"])
@role_required("pelanggan")
def pelanggan_scan_cari():
    raw = (request.form.get("token") or "").strip()
    if not raw:
        flash("Masukkan token QR atau hasil scan terlebih dahulu.", "danger")
        return redirect(url_for("pelanggan_scan"))

    token = raw
    # Terima URL lengkap (mis. https://.../qr/TOKEN) maupun token mentah.
    if "/qr/" in token:
        token = token.rsplit("/qr/", 1)[-1]
    token = token.strip().strip("/").split("?")[0].split("#")[0]
    # Hanya izinkan karakter token yang aman.
    token = re.sub(r"[^A-Za-z0-9_-]", "", token)

    if not token:
        flash("Token QR tidak valid. Periksa kembali hasil scan.", "danger")
        return redirect(url_for("pelanggan_scan"))

    qr = query_one(
        "SELECT token_qr FROM kode_qr_produk WHERE token_qr = %s", (token,)
    )
    if not qr:
        flash(
            "Token QR tidak ditemukan. Pastikan Anda memindai QR Code produk yang benar.",
            "danger",
        )
        return redirect(url_for("pelanggan_scan"))

    return redirect(url_for("qr_detail", token_qr=qr["token_qr"]))


def daftar_registrasi_pelanggan(pelanggan_id, limit=None):
    sql = """
        SELECT
            r.id AS registrasi_id,
            r.tanggal_pembelian,
            r.tempat_pembelian,
            r.nomor_invoice,
            r.bukti_pembelian,
            r.status_registrasi,
            r.dibuat_pada,
            p.nama_produk,
            p.kategori_model,
            q.nomor_seri,
            q.token_qr,
            kg.nama AS nama_kebijakan,
            kg.durasi_bulan,
            g.tanggal_mulai,
            g.tanggal_berakhir,
            g.status AS status_garansi_tersimpan,
            (SELECT COUNT(*) FROM klaim_garansi k
             WHERE k.registrasi_produk_id = r.id) AS total_klaim
        FROM registrasi_produk r
        JOIN kode_qr_produk q ON q.id = r.kode_qr_id
        JOIN produk p ON p.id = q.produk_id
        JOIN kebijakan_garansi kg ON kg.id = p.kebijakan_garansi_id
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        WHERE r.pelanggan_id = %s AND r.status_registrasi = 'aktif'
        ORDER BY r.dibuat_pada DESC
    """
    params = [pelanggan_id]
    if limit:
        sql += " LIMIT %s"
        params.append(int(limit))
    rows = query_all(sql, tuple(params))
    for row in rows:
        row["status_garansi_aktual"] = status_garansi(row.get("tanggal_berakhir"))
    return rows


def daftar_klaim_pelanggan(pelanggan_id, limit=None):
    sql = """
        SELECT
            k.*,
            p.nama_produk,
            q.nomor_seri,
            g.tanggal_berakhir
        FROM klaim_garansi k
        JOIN registrasi_produk r ON r.id = k.registrasi_produk_id
        JOIN kode_qr_produk q ON q.id = r.kode_qr_id
        JOIN produk p ON p.id = q.produk_id
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        WHERE k.pelanggan_id = %s
        ORDER BY k.tanggal_klaim DESC
    """
    params = [pelanggan_id]
    if limit:
        sql += " LIMIT %s"
        params.append(int(limit))
    rows = query_all(sql, tuple(params))
    for row in rows:
        row["status_garansi_aktual"] = status_garansi(row.get("tanggal_berakhir"))
    return rows


@app.route("/pelanggan/dashboard")
@role_required("pelanggan")
def pelanggan_dashboard():
    registrasi = daftar_registrasi_pelanggan(g.user["id"], limit=8)
    klaim = daftar_klaim_pelanggan(g.user["id"], limit=8)
    notifikasi = query_all(
        """
        SELECT *
        FROM notifikasi
        WHERE pengguna_id = %s
        ORDER BY dibuat_pada DESC
        LIMIT 12
        """,
        (g.user["id"],),
    )
    status_counts = {}
    for item in daftar_klaim_pelanggan(g.user["id"]):
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1

    ringkasan = {
        "total_produk": len(daftar_registrasi_pelanggan(g.user["id"])),
        "garansi_aktif": sum(
            1
            for item in daftar_registrasi_pelanggan(g.user["id"])
            if item["status_garansi_aktual"] == "aktif"
        ),
        "klaim_aktif": sum(
            1 for item in daftar_klaim_pelanggan(g.user["id"]) if item["status"] in STATUS_KLAIM_AKTIF
        ),
        "notifikasi_baru": sum(1 for item in notifikasi if not item["dibaca"]),
    }
    return render_template(
        "pelanggan/dashboard.html",
        registrasi=registrasi,
        klaim=klaim,
        notifikasi=notifikasi,
        status_counts=status_counts,
        ringkasan=ringkasan,
    )


@app.route("/pelanggan/klaim/<int:klaim_id>/batal", methods=["POST"])
@role_required("pelanggan")
def pelanggan_dashboard_klaim_batal(klaim_id):
    klaim = query_one(
        "SELECT id, status FROM klaim_garansi WHERE id = %s AND pelanggan_id = %s",
        (klaim_id, g.user["id"]),
    )
    if not klaim:
        abort(404)

    if klaim["status"] != "menunggu_verifikasi":
        flash("Klaim hanya dapat dibatalkan saat masih menunggu verifikasi.", "danger")
        return redirect(url_for("pelanggan_dashboard"))

    execute("DELETE FROM klaim_garansi WHERE id = %s", (klaim_id,))
    catat_log("batal_klaim_dashboard", f"Pelanggan membatalkan klaim #{klaim_id}.")
    flash("Klaim berhasil dibatalkan.", "success")
    return redirect(url_for("pelanggan_dashboard"))


@app.route("/pelanggan/produk")
@role_required("pelanggan")
def pelanggan_produk():
    registrasi = daftar_registrasi_pelanggan(g.user["id"])
    return render_template("pelanggan/produk.html", registrasi=registrasi)


@app.route("/pelanggan/garansi/<int:registrasi_id>")
@role_required("pelanggan")
def pelanggan_garansi(registrasi_id):
    registrasi = ambil_registrasi(registrasi_id, pelanggan_id=g.user["id"])
    if not registrasi:
        abort(404)

    klaim = query_all(
        """
        SELECT k.*, pt.nama AS nama_petugas
        FROM klaim_garansi k
        LEFT JOIN pengguna pt ON pt.id = k.diproses_oleh
        WHERE k.registrasi_produk_id = %s
        ORDER BY k.tanggal_klaim DESC
        """,
        (registrasi_id,),
    )
    klaim_terbuka = klaim_aktif_untuk_registrasi(registrasi_id)
    bisa_klaim = (
        registrasi["status_garansi_aktual"] == "aktif"
        and klaim_terbuka is None
        and registrasi["status_produk"] == "aktif"
    )
    return render_template(
        "pelanggan/garansi.html",
        registrasi=registrasi,
        klaim=klaim,
        bisa_klaim=bisa_klaim,
        klaim_terbuka=klaim_terbuka,
    )


@app.route("/pelanggan/klaim")
@role_required("pelanggan")
def pelanggan_klaim():
    klaim = daftar_klaim_pelanggan(g.user["id"])
    status_counts = {}
    for item in klaim:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    return render_template(
        "pelanggan/klaim.html", klaim=klaim, status_counts=status_counts
    )


@app.route("/pelanggan/klaim/<int:registrasi_id>", methods=["GET", "POST"])
@role_required("pelanggan")
def pelanggan_klaim_form(registrasi_id):
    registrasi = ambil_registrasi(registrasi_id, pelanggan_id=g.user["id"])
    if not registrasi:
        abort(404)

    if registrasi["status_garansi_aktual"] != "aktif":
        flash("Garansi produk ini sudah berakhir. Klaim tidak dapat diajukan.", "danger")
        return redirect(url_for("pelanggan_garansi", registrasi_id=registrasi_id))

    klaim_terbuka = klaim_aktif_untuk_registrasi(registrasi_id)
    if klaim_terbuka:
        flash(
            "Masih ada klaim aktif untuk produk ini. Selesaikan klaim tersebut terlebih dahulu.",
            "warning",
        )
        return redirect(
            url_for("pelanggan_klaim_detail", klaim_id=klaim_terbuka["id"])
        )

    if request.method == "POST":
        deskripsi = (request.form.get("deskripsi_masalah") or "").strip()
        file_foto = request.files.get("foto_kerusakan")
        file_bukti = request.files.get("bukti_pembelian")

        tersimpan = []
        try:
            if len(deskripsi) < 10:
                raise ValidationError("Deskripsi masalah minimal 10 karakter.")
            if not file_foto or not file_foto.filename:
                raise ValidationError("Foto kerusakan wajib diunggah.")

            foto = simpan_upload(file_foto, "kerusakan")
            tersimpan.append(foto["path_file"])
            bukti = None
            if file_bukti and file_bukti.filename:
                bukti = simpan_upload(file_bukti, "klaim")
                tersimpan.append(bukti["path_file"])

            db = get_db()
            cursor = db.cursor(dictionary=True)
            try:
                cursor.execute(
                    """
                    INSERT INTO klaim_garansi
                        (registrasi_produk_id, pelanggan_id, deskripsi_masalah, status)
                    VALUES (%s, %s, %s, 'menunggu_verifikasi')
                    """,
                    (registrasi_id, g.user["id"], deskripsi),
                )
                klaim_id = cursor.lastrowid

                cursor.execute(
                    """
                    INSERT INTO lampiran_klaim
                        (klaim_id, jenis, nama_file, path_file, tipe_file, ukuran_file)
                    VALUES (%s, 'foto_kerusakan', %s, %s, %s, %s)
                    """,
                    (
                        klaim_id,
                        foto["nama_file"],
                        foto["path_file"],
                        foto["tipe_file"],
                        foto["ukuran_file"],
                    ),
                )

                if bukti:
                    cursor.execute(
                        """
                        INSERT INTO lampiran_klaim
                            (klaim_id, jenis, nama_file, path_file, tipe_file, ukuran_file)
                        VALUES (%s, 'bukti_pembelian', %s, %s, %s, %s)
                        """,
                        (
                            klaim_id,
                            bukti["nama_file"],
                            bukti["path_file"],
                            bukti["tipe_file"],
                            bukti["ukuran_file"],
                        ),
                    )
                elif registrasi.get("bukti_pembelian"):
                    path_bukti = registrasi["bukti_pembelian"]
                    nama_bukti = os.path.basename(path_bukti)
                    ekstensi_bukti = (
                        nama_bukti.rsplit(".", 1)[1].lower()
                        if "." in nama_bukti
                        else "jpg"
                    )
                    cursor.execute(
                        """
                        INSERT INTO lampiran_klaim
                            (klaim_id, jenis, nama_file, path_file, tipe_file, ukuran_file)
                        VALUES (%s, 'bukti_pembelian', %s, %s, %s, NULL)
                        """,
                        (klaim_id, nama_bukti, path_bukti, ekstensi_bukti),
                    )

                cursor.execute(
                    """
                    INSERT INTO riwayat_status_klaim
                        (klaim_id, status_sebelumnya, status_baru, diubah_oleh, catatan)
                    VALUES (%s, NULL, 'menunggu_verifikasi', %s, %s)
                    """,
                    (klaim_id, g.user["id"], "Klaim diajukan oleh pelanggan."),
                )
                tambah_notifikasi(
                    cursor,
                    g.user["id"],
                    klaim_id,
                    "Klaim Berhasil Diajukan",
                    f"Klaim #{klaim_id} untuk {registrasi['nama_produk']} sedang menunggu verifikasi petugas.",
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.close()
        except ValidationError as exc:
            for path in tersimpan:
                hapus_file(path)
            flash(str(exc), "danger")
            return render_template(
                "pelanggan/klaim_form.html", registrasi=registrasi
            )
        except Exception:
            for path in tersimpan:
                hapus_file(path)
            app.logger.exception("Gagal membuat klaim untuk registrasi %s.", registrasi_id)
            flash("Gagal mengajukan klaim. Silakan coba lagi.", "danger")
            return render_template(
                "pelanggan/klaim_form.html", registrasi=registrasi
            )

        catat_log("ajukan_klaim", f"Mengajukan klaim #{klaim_id}.")
        flash("Klaim berhasil diajukan. Silakan tunggu verifikasi petugas.", "success")
        return redirect(url_for("pelanggan_klaim_detail", klaim_id=klaim_id))

    return render_template("pelanggan/klaim_form.html", registrasi=registrasi)


@app.route("/pelanggan/klaim/<int:klaim_id>/detail")
@role_required("pelanggan")
def pelanggan_klaim_detail(klaim_id):
    klaim = query_one(
        """
        SELECT
            k.*,
            p.nama_produk,
            p.kategori_model,
            q.nomor_seri,
            q.token_qr,
            r.id AS registrasi_id,
            r.tanggal_pembelian,
            r.tempat_pembelian,
            r.nomor_invoice,
            g.tanggal_mulai,
            g.tanggal_berakhir,
            pt.nama AS nama_petugas
        FROM klaim_garansi k
        JOIN registrasi_produk r ON r.id = k.registrasi_produk_id
        JOIN kode_qr_produk q ON q.id = r.kode_qr_id
        JOIN produk p ON p.id = q.produk_id
        LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
        LEFT JOIN pengguna pt ON pt.id = k.diproses_oleh
        WHERE k.id = %s AND k.pelanggan_id = %s
        """,
        (klaim_id, g.user["id"]),
    )
    if not klaim:
        abort(404)

    klaim["status_garansi_aktual"] = status_garansi(klaim.get("tanggal_berakhir"))
    lampiran = query_all(
        "SELECT * FROM lampiran_klaim WHERE klaim_id = %s ORDER BY id",
        (klaim_id,),
    )
    riwayat = query_all(
        """
        SELECT rs.*, u.nama AS nama_pengguna, u.role
        FROM riwayat_status_klaim rs
        LEFT JOIN pengguna u ON u.id = rs.diubah_oleh
        WHERE rs.klaim_id = %s
        ORDER BY rs.dibuat_pada ASC, rs.id ASC
        """,
        (klaim_id,),
    )
    catatan_servis = query_all(
        """
        SELECT cs.*, u.nama AS nama_petugas
        FROM catatan_servis cs
        LEFT JOIN pengguna u ON u.id = cs.petugas_id
        WHERE cs.klaim_id = %s
        ORDER BY cs.dibuat_pada DESC, cs.id DESC
        """,
        (klaim_id,),
    )
    return render_template(
        "pelanggan/klaim_detail.html",
        klaim=klaim,
        lampiran=lampiran,
        riwayat=riwayat,
        catatan_servis=catatan_servis,
    )


@app.route("/pelanggan/notifikasi/baca", methods=["POST"])
@role_required("pelanggan")
def pelanggan_notifikasi_baca():
    execute(
        "UPDATE notifikasi SET dibaca = 1 WHERE pengguna_id = %s AND dibaca = 0",
        (g.user["id"],),
    )
    flash("Semua notifikasi ditandai sudah dibaca.", "success")
    return redirect(url_for("pelanggan_dashboard"))


# ---------------------------------------------------------------------------
# Route QR Code publik
# ---------------------------------------------------------------------------


@app.route("/qr/<token_qr>")
def qr_detail(token_qr):
    qr = ambil_qr(token_qr)
    if not qr:
        return (
            render_template(
                "qr_info.html",
                qr=None,
                pesan="QR Code tidak valid atau tidak terdaftar.",
            ),
            404,
        )

    is_owner = bool(
        g.get("user")
        and g.user["role"] == "pelanggan"
        and qr.get("pelanggan_id") == g.user["id"]
    )
    can_register = bool(
        g.get("user")
        and g.user["role"] == "pelanggan"
        and not qr.get("registrasi_id")
        and qr.get("status_qr") == "tersedia"
        and qr.get("status_produk") == "aktif"
        and qr.get("kebijakan_aktif")
    )
    bisa_klaim = bool(
        is_owner
        and qr.get("status_garansi_aktual") == "aktif"
        and not klaim_aktif_untuk_registrasi(qr["registrasi_id"])
    )

    return render_template(
        "qr_info.html",
        qr=qr,
        is_owner=is_owner,
        can_register=can_register,
        bisa_klaim=bisa_klaim,
        pesan=None,
    )


@app.route("/qr/<token_qr>/registrasi", methods=["GET", "POST"])
@role_required("pelanggan")
def qr_registrasi(token_qr):
    qr = ambil_qr(token_qr)
    if not qr:
        abort(404)

    if qr.get("registrasi_id"):
        flash("Produk ini sudah terdaftar.", "warning")
        return redirect(url_for("qr_detail", token_qr=token_qr))

    if qr["status_qr"] != "tersedia" or qr["status_produk"] != "aktif":
        flash("Produk ini tidak tersedia untuk registrasi.", "danger")
        return redirect(url_for("qr_detail", token_qr=token_qr))

    if not qr.get("kebijakan_aktif"):
        flash("Kebijakan garansi produk sedang tidak aktif.", "danger")
        return redirect(url_for("qr_detail", token_qr=token_qr))

    form = {
        "nama": g.user["nama"],
        "nomor_telepon": g.user.get("nomor_telepon") or "",
        "email": g.user["email"],
        "tanggal_pembelian": "",
        "tempat_pembelian": "",
        "nomor_invoice": "",
    }

    if request.method == "POST":
        form.update(
            {
                "nama": (request.form.get("nama") or "").strip(),
                "nomor_telepon": (request.form.get("nomor_telepon") or "").strip(),
                "email": g.user["email"],
                "tanggal_pembelian": (request.form.get("tanggal_pembelian") or "").strip(),
                "tempat_pembelian": (request.form.get("tempat_pembelian") or "").strip(),
                "nomor_invoice": (request.form.get("nomor_invoice") or "").strip(),
            }
        )
        file_bukti = request.files.get("bukti_pembelian")
        bukti = None
        try:
            if len(form["nama"]) < 3:
                raise ValidationError("Nama minimal 3 karakter.")
            if form["nomor_telepon"] and len(form["nomor_telepon"]) < 8:
                raise ValidationError("Nomor telepon tidak valid.")
            tanggal_pembelian = parse_tanggal(
                form["tanggal_pembelian"], "Tanggal pembelian"
            )
            if tanggal_pembelian > date.today():
                raise ValidationError("Tanggal pembelian tidak boleh di masa depan.")
            if tanggal_pembelian < date(2000, 1, 1):
                raise ValidationError("Tanggal pembelian tidak valid.")
            if not form["tempat_pembelian"]:
                raise ValidationError("Tempat pembelian wajib diisi.")
            if not form["nomor_invoice"]:
                raise ValidationError("Nomor invoice wajib diisi.")
            if not file_bukti or not file_bukti.filename:
                raise ValidationError("Bukti pembelian wajib diunggah.")

            bukti = simpan_upload(file_bukti, "bukti")
            tanggal_berakhir = add_months(
                tanggal_pembelian, qr["durasi_bulan"]
            )
            status_garansi_baru = status_garansi(tanggal_berakhir)

            db = get_db()
            cursor = db.cursor(dictionary=True)
            try:
                cursor.execute(
                    """
                    INSERT INTO registrasi_produk
                        (kode_qr_id, pelanggan_id, tanggal_pembelian, tempat_pembelian,
                         nomor_invoice, bukti_pembelian, status_registrasi)
                    VALUES (%s, %s, %s, %s, %s, %s, 'aktif')
                    """,
                    (
                        qr["qr_id"],
                        g.user["id"],
                        tanggal_pembelian,
                        form["tempat_pembelian"],
                        form["nomor_invoice"],
                        bukti["path_file"],
                    ),
                )
                registrasi_id = cursor.lastrowid

                cursor.execute(
                    """
                    INSERT INTO garansi
                        (registrasi_produk_id, tanggal_mulai, tanggal_berakhir, status)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        registrasi_id,
                        tanggal_pembelian,
                        tanggal_berakhir,
                        status_garansi_baru,
                    ),
                )
                cursor.execute(
                    "UPDATE kode_qr_produk SET status = 'terdaftar' WHERE id = %s",
                    (qr["qr_id"],),
                )
                cursor.execute(
                    """
                    UPDATE pengguna
                    SET nama = %s, nomor_telepon = %s
                    WHERE id = %s AND role = 'pelanggan'
                    """,
                    (
                        form["nama"],
                        form["nomor_telepon"] or None,
                        g.user["id"],
                    ),
                )
                tambah_notifikasi(
                    cursor,
                    g.user["id"],
                    None,
                    "Registrasi Produk Berhasil",
                    f"Produk {qr['nama_produk']} ({qr['nomor_seri']}) berhasil diregistrasikan. "
                    f"Garansi berlaku sampai {format_tanggal(tanggal_berakhir)}.",
                )
                db.commit()
            except IntegrityError:
                db.rollback()
                raise ValidationError(
                    "Produk ini sudah diregistrasikan oleh pengguna lain."
                )
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.close()
        except ValidationError as exc:
            if bukti:
                hapus_file(bukti["path_file"])
            flash(str(exc), "danger")
            return render_template(
                "pelanggan/registrasi.html", qr=qr, form=form
            )
        except Exception:
            if bukti:
                hapus_file(bukti["path_file"])
            app.logger.exception("Gagal membuat registrasi produk untuk QR %s.", token_qr)
            flash("Gagal menyimpan registrasi. Silakan coba lagi.", "danger")
            return render_template(
                "pelanggan/registrasi.html", qr=qr, form=form
            )

        catat_log(
            "registrasi_produk",
            f"Registrasi produk {qr['nama_produk']} ({qr['nomor_seri']}) berhasil.",
        )
        flash("Registrasi produk berhasil. Garansi Anda sudah aktif.", "success")
        return redirect(
            url_for("pelanggan_garansi", registrasi_id=registrasi_id)
        )

    return render_template("pelanggan/registrasi.html", qr=qr, form=form)


@app.route("/qr/<token_qr>/gambar.png")
def qr_gambar(token_qr):
    row = query_one(
        "SELECT token_qr FROM kode_qr_produk WHERE token_qr = %s", (token_qr,)
    )
    if not row:
        abort(404)

    gambar = qrcode.make(qr_target_url(row["token_qr"]))
    buffer = io.BytesIO()
    gambar.save(buffer, format="PNG")
    return Response(
        buffer.getvalue(),
        mimetype="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.route("/berkas/<path:filename>")
def berkas(filename):
    """Menyajikan file upload hanya kepada pemilik atau petugas/admin."""
    if g.get("user") is None:
        flash("Silakan login untuk melihat berkas.", "warning")
        return redirect(url_for("login", next=request.full_path))

    lampiran = query_one(
        """
        SELECT l.id, k.pelanggan_id
        FROM lampiran_klaim l
        JOIN klaim_garansi k ON k.id = l.klaim_id
        WHERE l.path_file = %s
        LIMIT 1
        """,
        (filename,),
    )
    if lampiran:
        if (
            g.user["role"] == "pelanggan"
            and lampiran["pelanggan_id"] != g.user["id"]
        ):
            abort(403)
    else:
        registrasi = query_one(
            """
            SELECT id, pelanggan_id
            FROM registrasi_produk
            WHERE bukti_pembelian = %s
            LIMIT 1
            """,
            (filename,),
        )
        if not registrasi:
            abort(404)
        if (
            g.user["role"] == "pelanggan"
            and registrasi["pelanggan_id"] != g.user["id"]
        ):
            abort(403)

    return send_from_directory(app.static_folder, filename)


# petugas manage aliases
app.add_url_rule('/petugas/manage/kebijakan', 'petugas_manage_kebijakan', admin_kebijakan)
app.add_url_rule('/petugas/manage/kebijakan/tambah', 'petugas_manage_kebijakan_tambah', admin_kebijakan_tambah, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/kebijakan/edit/<int:kebijakan_id>', 'petugas_manage_kebijakan_edit', admin_kebijakan_edit, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/kebijakan/<int:kebijakan_id>/hapus', 'petugas_manage_kebijakan_hapus', admin_kebijakan_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/pelanggan', 'petugas_manage_pelanggan', admin_pelanggan)
app.add_url_rule('/petugas/manage/pelanggan/tambah', 'petugas_manage_pelanggan_tambah', admin_pelanggan_tambah, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/pelanggan/edit/<int:pelanggan_id>', 'petugas_manage_pelanggan_edit', admin_pelanggan_edit, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/pelanggan/<int:pelanggan_id>/hapus', 'petugas_manage_pelanggan_hapus', admin_pelanggan_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/produk', 'petugas_manage_produk', admin_produk)
app.add_url_rule('/petugas/manage/produk/tambah', 'petugas_manage_produk_tambah', admin_produk_tambah, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/produk/edit/<int:produk_id>', 'petugas_manage_produk_edit', admin_produk_edit, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/produk/<int:produk_id>/hapus', 'petugas_manage_produk_hapus', admin_produk_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/qr', 'petugas_manage_qr', admin_qr)
app.add_url_rule('/petugas/manage/qr/tambah', 'petugas_manage_qr_tambah', admin_qr_tambah, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/qr/edit/<int:qr_id>', 'petugas_manage_qr_edit', admin_qr_edit, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/qr/<int:qr_id>/hapus', 'petugas_manage_qr_hapus', admin_qr_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/registrasi', 'petugas_manage_registrasi', admin_registrasi)
app.add_url_rule('/petugas/manage/registrasi/edit/<int:registrasi_id>', 'petugas_manage_registrasi_edit', admin_registrasi_edit, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/registrasi/<int:registrasi_id>/hapus', 'petugas_manage_registrasi_hapus', admin_registrasi_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/garansi', 'petugas_manage_garansi', admin_garansi)
app.add_url_rule('/petugas/manage/garansi/edit/<int:garansi_id>', 'petugas_manage_garansi_edit', admin_garansi_edit, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/garansi/<int:garansi_id>/hapus', 'petugas_manage_garansi_hapus', admin_garansi_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/klaim', 'petugas_manage_klaim', admin_klaim)
app.add_url_rule('/petugas/manage/klaim/edit/<int:klaim_id>', 'petugas_manage_klaim_edit', admin_klaim_edit, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/klaim/<int:klaim_id>/hapus', 'petugas_manage_klaim_hapus', admin_klaim_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/servis', 'petugas_manage_servis', admin_servis)
app.add_url_rule('/petugas/manage/servis/tambah', 'petugas_manage_servis_tambah', admin_servis_tambah, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/servis/edit/<int:servis_id>', 'petugas_manage_servis_edit', admin_servis_edit, methods=["GET", "POST"])
app.add_url_rule('/petugas/manage/servis/<int:servis_id>/hapus', 'petugas_manage_servis_hapus', admin_servis_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/notifikasi', 'petugas_manage_notifikasi', admin_notifikasi)
app.add_url_rule('/petugas/manage/notifikasi/<int:notif_id>/hapus', 'petugas_manage_notifikasi_hapus', admin_notifikasi_hapus, methods=["POST"])
app.add_url_rule('/petugas/manage/log', 'petugas_manage_log', admin_log)
app.add_url_rule('/petugas/manage/log/<int:log_id>/hapus', 'petugas_manage_log_hapus', admin_log_hapus, methods=["POST"])

# ---------------------------------------------------------------------------
# Filter dan context processor Jinja
# ---------------------------------------------------------------------------


@app.template_filter("tanggal")
def filter_tanggal(value):
    return format_tanggal(value)


@app.template_filter("tanggalwaktu")
def filter_tanggal_waktu(value):
    return format_tanggal_waktu(value)


@app.template_filter("ukuran")
def filter_ukuran(value):
    return format_ukuran(value)


@app.template_filter("status_label")
def filter_status_label(value):
    return (
        STATUS_KLAIM_LABELS.get(value)
        or STATUS_GARANSI_LABELS.get(value)
        or STATUS_LAIN_LABELS.get(value)
        or value
        or "-"
    )


@app.template_filter("status_kelas")
def filter_status_kelas(value):
    return f"badge-{STATUS_BADGES.get(value, 'neutral')}"


@app.context_processor
def inject_globals():
    return {
        "current_user": g.get("user"),
        "status_klaim_labels": STATUS_KLAIM_LABELS,
        "status_klaim_list": list(STATUS_KLAIM_LABELS.items()),
        "status_garansi_labels": STATUS_GARANSI_LABELS,
        "role_labels": ROLE_LABELS,
        "hari_ini": date.today(),
        "qr_url": qr_target_url,
    }


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


@app.errorhandler(403)
def forbidden(error):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("errors/404.html"), 404


@app.errorhandler(413)
def terlalu_besar(error):
    flash("Ukuran total file terlalu besar. Maksimal 12 MB per pengiriman.", "danger")
    return render_template("errors/413.html"), 413


@app.errorhandler(500)
def internal_error(error):
    try:
        db = g.get("db")
        if db:
            db.rollback()
    except Exception:
        app.logger.exception("Gagal rollback setelah error 500.")
    app.logger.exception("Terjadi kesalahan internal.")
    return render_template("errors/500.html"), 500


@app.errorhandler(MySQLError)
def database_error(error):
    try:
        db = g.get("db")
        if db:
            db.rollback()
    except Exception:
        pass
    app.logger.exception("Terjadi kesalahan database.")
    return render_template("errors/500.html"), 500


# ---------------------------------------------------------------------------
# Menjalankan aplikasi
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(
        host=app.config.get("HOST", "0.0.0.0"),
        port=app.config.get("PORT", 5000),
        debug=app.config.get("DEBUG", False),
    )
