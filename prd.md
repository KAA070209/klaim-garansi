# PRODUCT REQUIREMENT DOCUMENT (PRD)

## Sistem Klaim Garansi Berbasis QR Code

**Versi:** 1.2  
**Status:** Draft  
**Backend:** Python Flask  
**Database:** MySQL  
**Frontend:** HTML, CSS, JavaScript, Jinja2  
**Arsitektur:** Flask Server-Side Rendering (SSR)

---

# 1. Gambaran Umum

Sistem Klaim Garansi Berbasis QR Code merupakan aplikasi yang digunakan untuk mempermudah proses registrasi produk dan pengajuan klaim garansi.

Setiap unit produk memiliki QR Code unik. Pelanggan dapat melakukan pemindaian QR Code pada kemasan produk untuk melihat informasi produk, melakukan registrasi pembelian, melihat masa berlaku garansi, serta mengajukan klaim garansi.

Petugas bertanggung jawab dalam pengelolaan produk, QR Code, pelanggan, verifikasi klaim, serta proses perbaikan atau penggantian produk. Admin bertanggung jawab dalam pengelolaan petugas dan pemantauan aktivitas serta laporan sistem.

Sistem menggunakan **Python Flask** sebagai backend, **MySQL** sebagai database, dan **Jinja2** untuk menghasilkan halaman HTML secara server-side.

---

# 2. Tujuan Sistem

Sistem bertujuan untuk:

1. Mempermudah pelanggan dalam melakukan registrasi produk.
2. Mengidentifikasi produk menggunakan QR Code unik.
3. Mempermudah pelanggan dalam mengajukan klaim garansi.
4. Membantu petugas melakukan verifikasi dan pengelolaan klaim.
5. Menampilkan status klaim kepada pelanggan.
6. Membantu admin memantau aktivitas dan laporan klaim.
7. Menyimpan riwayat proses klaim secara terstruktur.
8. Mengurangi proses manual dalam pengelolaan garansi produk.

---

# 3. Ruang Lingkup

## 3.1 Pengelolaan Pengguna

Sistem memiliki tiga jenis pengguna:

- Admin
- Petugas
- Pelanggan

Setiap pengguna memiliki hak akses yang berbeda sesuai dengan perannya.

## 3.2 Pengelolaan Produk

Petugas dapat:

- Menambahkan produk.
- Mengubah data produk.
- Melihat data produk.
- Mengelola nomor seri produk.
- Menghasilkan QR Code unik untuk setiap unit produk.

## 3.3 Registrasi Produk

Pelanggan dapat:

- Memindai QR Code.
- Melihat informasi produk.
- Mengisi data pembelian.
- Mengunggah bukti pembelian.
- Melakukan registrasi produk.

## 3.4 Garansi

Sistem menentukan masa berlaku garansi berdasarkan:

- Tanggal pembelian.
- Kebijakan garansi produk.

Sistem menampilkan status garansi kepada pelanggan.

## 3.5 Klaim Garansi

Pelanggan dapat:

- Membuat pengajuan klaim.
- Menjelaskan masalah produk.
- Mengunggah foto kerusakan.
- Mengunggah bukti pembelian.
- Melihat status klaim.

Petugas dapat melakukan verifikasi dan memperbarui status klaim.

## 3.6 Pelaporan

Admin dapat melihat:

- Jumlah produk.
- Jumlah pelanggan.
- Jumlah klaim.
- Klaim berdasarkan status.
- Aktivitas petugas.
- Laporan klaim garansi.

---

# 4. Aktor Sistem

## 4.1 Admin

Admin memiliki akses untuk:

- Login.
- Melihat dashboard.
- Mengelola akun petugas.
- Melihat data produk.
- Melihat data pelanggan.
- Melihat klaim garansi.
- Melihat laporan.
- Memantau aktivitas sistem.

Admin tidak bertugas melakukan proses klaim secara langsung.

## 4.2 Petugas

Petugas memiliki akses untuk:

- Login.
- Mengelola produk.
- Membuat QR Code.
- Melihat pelanggan.
- Melihat registrasi produk.
- Memverifikasi klaim.
- Mengubah status klaim.
- Menambahkan catatan pemeriksaan.
- Menambahkan catatan perbaikan atau penggantian.
- Menyelesaikan klaim.

## 4.3 Pelanggan

Pelanggan dapat:

- Membuat akun atau login.
- Memindai QR Code.
- Melakukan registrasi produk.
- Melihat masa berlaku garansi.
- Mengajukan klaim.
- Mengunggah dokumen pendukung.
- Melihat status klaim.
- Melihat riwayat klaim.

---

# 5. Alur Utama Sistem

## 5.1 Pembuatan QR Code Produk

1. Petugas login.
2. Petugas membuka halaman produk.
3. Petugas memasukkan data produk.
4. Sistem membuat nomor seri/unit produk.
5. Sistem menghasilkan `token_qr` yang unik.
6. Token disimpan ke database.
7. QR Code dibuat berdasarkan token tersebut.
8. QR Code dapat dicetak dan ditempel pada kemasan produk.

---

# 6. Alur Pelanggan

## 6.1 Pemindaian QR Code

Pelanggan melakukan scan QR Code pada produk.

Sistem menerima token QR melalui URL:

```text
/qr/<token_qr>
```

Sistem kemudian mencari token tersebut di database.

Jika token tidak ditemukan:

```text
QR Code tidak valid.
```

Proses dihentikan.

Jika token ditemukan, sistem menampilkan informasi produk.

---

# 7. Registrasi Produk

Jika produk belum pernah diregistrasikan:

Pelanggan mengisi:

- Nama.
- Nomor telepon.
- Email.
- Tanggal pembelian.
- Tempat pembelian.
- Nomor invoice.
- Bukti pembelian.

Setelah data berhasil disimpan, sistem membuat data registrasi dan menentukan masa garansi.

Jika produk sudah terdaftar, pelanggan tidak perlu melakukan registrasi ulang.

---

# 8. Perhitungan Garansi

Masa garansi ditentukan berdasarkan kebijakan garansi.

Contoh:

```text
Tanggal pembelian : 1 Januari 2026
Durasi garansi    : 12 bulan
Tanggal berakhir  : 1 Januari 2027
```

Sistem menentukan status garansi berdasarkan tanggal saat pelanggan mengakses sistem.

Status dapat berupa:

- Aktif
- Berakhir

---

# 9. Pengajuan Klaim

Pelanggan dapat mengajukan klaim apabila produk memiliki garansi yang masih aktif.

Data klaim meliputi:

- Produk.
- Deskripsi masalah.
- Foto kerusakan.
- Bukti pembelian.
- Data pendukung lainnya.

Setelah pengajuan berhasil:

```text
Status = menunggu_verifikasi
```

Klaim kemudian dapat diproses oleh petugas.

---

# 10. Verifikasi Klaim

Petugas membuka daftar klaim.

Petugas dapat melihat:

- Data pelanggan.
- Data produk.
- Data registrasi.
- Masa garansi.
- Deskripsi kerusakan.
- Lampiran klaim.
- Riwayat klaim.

Petugas kemudian menentukan keputusan.

Jika klaim diterima:

```text
menunggu_verifikasi
        ↓
sedang_ditinjau
        ↓
disetujui
```

Jika klaim ditolak:

```text
menunggu_verifikasi
        ↓
sedang_ditinjau
        ↓
ditolak
```

Alasan penolakan wajib dicatat.

---

# 11. Proses Perbaikan

Jika klaim disetujui dan membutuhkan perbaikan:

```text
disetujui
    ↓
dalam_perbaikan
    ↓
selesai
```

Petugas dapat mencatat:

- Hasil pemeriksaan.
- Tindakan perbaikan.
- Penggantian komponen.
- Penggantian produk.
- Catatan tambahan.
- Tanggal proses.

---

# 12. Status Klaim

Status utama yang digunakan:

| Status | Keterangan |
|---|---|
| `menunggu_verifikasi` | Klaim baru dibuat dan menunggu pemeriksaan |
| `sedang_ditinjau` | Klaim sedang diperiksa oleh petugas |
| `disetujui` | Klaim disetujui |
| `ditolak` | Klaim ditolak |
| `dalam_perbaikan` | Produk sedang diperbaiki/diproses |
| `selesai` | Proses klaim telah selesai |

Setiap perubahan status disimpan pada tabel riwayat status klaim.

---

# 13. Functional Requirements

## FR-01 Login

Sistem harus menyediakan halaman login untuk pengguna.

Sistem melakukan:

1. Validasi email/username.
2. Validasi password.
3. Pemeriksaan akun.
4. Penyimpanan informasi pengguna pada session.
5. Pengalihan pengguna ke dashboard sesuai role.

---

## FR-02 Logout

Pengguna dapat melakukan logout.

Sistem menghapus session pengguna.

---

## FR-03 Pengelolaan Petugas

Admin dapat:

- Melihat daftar petugas.
- Menambahkan petugas.
- Mengubah data petugas.
- Mengaktifkan/nonaktifkan akun petugas.

Password harus disimpan menggunakan password hashing.

---

# 14. Pengelolaan Produk

Petugas dapat:

- Menambahkan produk.
- Mengubah produk.
- Melihat produk.
- Menghapus/nonaktifkan produk sesuai kebutuhan sistem.

Data produk minimal meliputi:

- Nama produk.
- Kategori/model.
- Kebijakan garansi.
- Status produk.

---

# 15. Pengelolaan QR Code

Setiap unit produk memiliki:

```text
nomor_seri
token_qr
```

`token_qr` harus unik.

QR Code tidak boleh menggunakan ID database secara langsung sebagai satu-satunya token identifikasi.

Contoh URL:

```text
https://domain.com/qr/ABX92KLM72PQR
```

---

# 16. Pelanggan

Sistem menyimpan data pelanggan seperti:

- Nama.
- Email.
- Nomor telepon.
- Alamat jika diperlukan.

Pelanggan dapat melihat produk yang telah diregistrasikan.

---

# 17. Registrasi Produk

Sistem menyimpan:

- Pelanggan.
- Produk.
- Nomor seri.
- Tanggal pembelian.
- Tempat pembelian.
- Nomor invoice.
- Bukti pembelian.
- Status registrasi.
- Data verifikasi.

Satu unit produk tidak boleh memiliki registrasi aktif ganda.

---

# 18. Klaim Garansi

Sistem harus menyediakan halaman pengajuan klaim.

Form klaim minimal:

```text
Deskripsi masalah
Foto kerusakan
Bukti pembelian
```

Sistem harus memeriksa status garansi sebelum klaim dibuat.

Jika garansi tidak aktif, sistem menampilkan alasan klaim tidak dapat diajukan.

---

# 19. Lampiran Klaim

File yang diunggah pelanggan disimpan pada folder upload.

Format yang diperbolehkan:

```text
jpg
jpeg
png
webp
```

Nama file harus dibuat aman dan tidak menggunakan nama file asli secara langsung.

Ukuran file harus dibatasi.

---

# 20. Notifikasi

Sistem menyediakan notifikasi kepada pelanggan ketika terjadi perubahan status klaim.

Contoh:

```text
Klaim Anda telah disetujui.
```

atau:

```text
Klaim Anda ditolak karena garansi telah berakhir.
```

---

# 21. Riwayat Status Klaim

Setiap perubahan status klaim dicatat.

Data riwayat meliputi:

- Klaim.
- Status sebelumnya.
- Status baru.
- Pengguna yang melakukan perubahan.
- Waktu perubahan.
- Catatan.

---

# 22. Catatan Servis

Petugas dapat mencatat proses servis.

Catatan dapat berisi:

- Hasil pemeriksaan.
- Kerusakan.
- Tindakan perbaikan.
- Komponen yang diganti.
- Penggantian produk.
- Catatan tambahan.

---

# 23. Database

Database menggunakan MySQL.

Tabel utama:

1. `pengguna`
2. `kebijakan_garansi`
3. `produk`
4. `kode_qr_produk`
5. `registrasi_produk`
6. `garansi`
7. `klaim_garansi`
8. `lampiran_klaim`
9. `riwayat_status_klaim`
10. `catatan_servis`
11. `notifikasi`
12. `log_aktivitas`

View:

```text
v_laporan_klaim_garansi
```

Database harus menggunakan relasi foreign key untuk menjaga integritas data.

---

# 24. Arsitektur Backend

Backend menggunakan arsitektur Flask monolithic sederhana.

Seluruh proses utama berada di:

```text
app.py
```

`app.py` menangani:

- Flask application.
- Routing.
- Session.
- Authentication.
- Authorization.
- Query database.
- Business logic.
- Validasi form.
- Upload file.
- QR Code.
- Notifikasi.
- Activity log.
- `render_template()`.
- Error handling.

Tidak menggunakan folder/module terpisah seperti:

```text
routes/
models/
services/
middleware/
```

---

# 25. Config

Konfigurasi dipisahkan dari `app.py`.

File:

```text
config.py
```

Berisi konfigurasi seperti:

```text
SECRET_KEY
MYSQL_HOST
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DATABASE
MYSQL_PORT
UPLOAD_FOLDER
```

Nilai rahasia disimpan melalui:

```text
.env
```

`config.py` bertugas membaca konfigurasi dari environment.

Logika aplikasi tidak diletakkan di `config.py`.

---

# 26. Template HTML

Sistem **tidak menggunakan `base.html`**.

Setiap halaman HTML merupakan file mandiri.

Contoh:

```text
templates/
├── login.html
├── admin/
│   ├── dashboard.html
│   ├── petugas.html
│   ├── petugas_tambah.html
│   ├── petugas_edit.html
│   └── laporan.html
├── petugas/
│   ├── dashboard.html
│   ├── produk.html
│   ├── produk_tambah.html
│   ├── produk_edit.html
│   ├── qr.html
│   ├── pelanggan.html
│   ├── klaim.html
│   └── klaim_detail.html
└── pelanggan/
    ├── dashboard.html
    ├── produk.html
    ├── registrasi.html
    ├── garansi.html
    ├── klaim.html
    └── klaim_detail.html
```

Setiap file dapat memiliki:

- Struktur HTML sendiri.
- Navbar sendiri jika diperlukan.
- Sidebar sendiri jika diperlukan.
- CSS yang dibutuhkan.
- JavaScript yang dibutuhkan.

Tidak ada:

```text
{% extends "base.html" %}
```

dan tidak ada:

```text
{% include "base.html" %}
```

---

# 27. Server-Side Rendering

Flask menggunakan Jinja2 untuk menghasilkan HTML.

Contoh:

```python
return render_template(
    "petugas/klaim.html",
    klaim=klaim
)
```

Data dari database dikirim langsung ke template.

Template menampilkan data menggunakan Jinja2.

Contoh:

```html
{% for item in klaim %}
<tr>
    <td>{{ item.id }}</td>
    <td>{{ item.nama_pelanggan }}</td>
    <td>{{ item.status }}</td>
</tr>
{% endfor %}
```

---

# 28. Struktur `app.py`

Semua route berada dalam satu file:

```text
app.py
```

Struktur logika secara umum:

```text
Import
↓
Konfigurasi Flask
↓
Koneksi database
↓
Helper function
↓
Authentication
↓
Authorization
↓
Route Admin
↓
Route Petugas
↓
Route Pelanggan
↓
Route QR Code
↓
Error Handler
↓
app.run()
```

---

# 29. Routing Flask

## Authentication

```text
/login
/logout
```

## Admin

```text
/admin/dashboard
/admin/petugas
/admin/petugas/tambah
/admin/petugas/edit/<id>
/admin/laporan
```

## Petugas

```text
/petugas/dashboard
/petugas/produk
/petugas/produk/tambah
/petugas/produk/edit/<id>
/petugas/qr
/petugas/qr/generate
/petugas/pelanggan
/petugas/klaim
/petugas/klaim/<id>
/petugas/klaim/<id>/status
```

## Pelanggan

```text
/pelanggan/dashboard
/pelanggan/produk
/pelanggan/garansi/<id>
/pelanggan/klaim/<id>
/pelanggan/klaim/<id>/detail
```

## QR Code

```text
/qr/<token_qr>
```

---

# 30. Authentication

Sistem menggunakan Flask Session.

Informasi pengguna yang diperlukan dapat disimpan seperti:

```python
session["user_id"]
session["role"]
```

Password tidak boleh disimpan dalam bentuk plaintext.

Sistem menggunakan password hashing.

---

# 31. Authorization

Setiap route harus melakukan pemeriksaan role.

Contoh konsep:

```text
Admin → halaman admin
Petugas → halaman petugas
Pelanggan → halaman pelanggan
```

Pengguna yang tidak memiliki hak akses tidak boleh membuka halaman dengan mengganti URL secara manual.

---

# 32. Koneksi Database

Backend menggunakan:

```text
mysql.connector
```

Koneksi database menggunakan konfigurasi dari environment.

Contoh konfigurasi:

```text
MYSQL_HOST
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DATABASE
MYSQL_PORT
```

Setiap proses database harus memastikan koneksi dan transaksi ditangani dengan benar.

Jika terjadi error pada proses transaksi:

```text
ROLLBACK
```

Jika berhasil:

```text
COMMIT
```

---

# 33. Keamanan

Sistem harus menerapkan:

- Password hashing.
- Session authentication.
- Role authorization.
- Validasi input.
- Validasi upload file.
- Batas ukuran file.
- Nama file upload yang aman.
- Token QR unik.
- Validasi kepemilikan data pelanggan.
- Pencegahan akses route berdasarkan role.
- Penggunaan environment variable untuk password database.
- Error handling tanpa menampilkan informasi sensitif.

---

# 34. Dashboard Admin

Dashboard admin menampilkan informasi seperti:

```text
Total Petugas
Total Pelanggan
Total Produk
Total Klaim
Klaim Menunggu
Klaim Disetujui
Klaim Ditolak
Klaim Selesai
```

Admin juga dapat melihat laporan klaim.

---

# 35. Dashboard Petugas

Dashboard petugas menampilkan:

```text
Total Produk
Total Pelanggan
Klaim Baru
Klaim Sedang Ditinjau
Klaim Disetujui
Klaim Dalam Perbaikan
Klaim Selesai
```

---

# 36. Dashboard Pelanggan

Dashboard pelanggan menampilkan:

- Produk yang telah diregistrasikan.
- Status garansi.
- Klaim yang sedang diproses.
- Riwayat klaim.
- Notifikasi.

---

# 37. Business Rules

## BR-01

Setiap unit produk memiliki satu `token_qr` unik.

## BR-02

QR Code yang tidak terdaftar tidak dapat digunakan untuk registrasi.

## BR-03

Produk yang sudah memiliki registrasi aktif tidak dapat diregistrasikan kembali.

## BR-04

Klaim hanya dapat dibuat jika garansi masih berlaku.

## BR-05

Klaim yang telah dibuat memiliki status awal:

```text
menunggu_verifikasi
```

## BR-06

Klaim yang ditolak harus memiliki alasan penolakan.

## BR-07

Perubahan status klaim harus dicatat dalam riwayat.

## BR-08

Proses perbaikan hanya dapat dilakukan terhadap klaim yang disetujui.

## BR-09

Pelanggan hanya dapat melihat data produk dan klaim miliknya sendiri.

## BR-10

Petugas hanya dapat melakukan fungsi sesuai dengan role petugas.

---

# 38. Non-Functional Requirements

## Performance

Halaman harus dapat ditampilkan dengan waktu respons yang wajar pada kondisi server normal.

## Security

Data pengguna dan informasi klaim harus dilindungi dari akses yang tidak sah.

## Maintainability

Kode backend harus terstruktur dengan jelas walaupun seluruh route berada di dalam `app.py`.

## Reliability

Sistem harus menangani error database dan kegagalan transaksi dengan aman.

## Usability

Antarmuka harus mudah dipahami oleh admin, petugas, dan pelanggan.

---

# 39. Struktur Folder Final

Struktur proyek:

```text
sistem-garansi-qr/
│
├── app.py
├── config.py
├── requirements.txt
├── .env
│
├── templates/
│   ├── login.html
│   │
│   ├── admin/
│   │   ├── dashboard.html
│   │   ├── petugas.html
│   │   ├── petugas_tambah.html
│   │   ├── petugas_edit.html
│   │   └── laporan.html
│   │
│   ├── petugas/
│   │   ├── dashboard.html
│   │   ├── produk.html
│   │   ├── produk_tambah.html
│   │   ├── produk_edit.html
│   │   ├── qr.html
│   │   ├── pelanggan.html
│   │   ├── klaim.html
│   │   └── klaim_detail.html
│   │
│   └── pelanggan/
│       ├── dashboard.html
│       ├── produk.html
│       ├── registrasi.html
│       ├── garansi.html
│       ├── klaim.html
│       └── klaim_detail.html
│
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── script.js
│   └── uploads/
│
└── db/
    └── sistem_garansi_qr.sql
```

**Catatan:** `base.html` tidak digunakan dan tidak dibuat.

---

# 40. Teknologi

| Komponen | Teknologi |
|---|---|
| Backend | Python |
| Framework | Flask |
| Database | MySQL |
| Database Driver | mysql-connector-python |
| Template Engine | Jinja2 |
| Frontend | HTML, CSS, JavaScript |
| Rendering | Server-Side Rendering |
| Authentication | Flask Session |
| Password | Password Hashing |
| QR Code | QR Code Generator |
| Environment | `.env` |
| Server | Gunicorn untuk deployment |

---

# 41. Prioritas Pengembangan

## Prioritas 1 — Authentication

- Login.
- Logout.
- Session.
- Role authorization.

## Prioritas 2 — Produk dan QR Code

- Produk.
- Nomor seri.
- QR token.
- Generate QR Code.

## Prioritas 3 — Registrasi Produk

- Scan QR.
- Data pelanggan.
- Data pembelian.
- Aktivasi garansi.

## Prioritas 4 — Klaim

- Pengajuan klaim.
- Upload lampiran.
- Verifikasi petugas.
- Status klaim.

## Prioritas 5 — Servis

- Pemeriksaan.
- Perbaikan.
- Penggantian.
- Penyelesaian klaim.

## Prioritas 6 — Dashboard dan Laporan

- Dashboard admin.
- Dashboard petugas.
- Dashboard pelanggan.
- Laporan klaim.
- Notifikasi.
- Activity log.

---

# 42. Acceptance Criteria

Sistem dinyatakan memenuhi kebutuhan apabila:

1. Pengguna dapat login sesuai role.
2. Admin dapat mengelola petugas.
3. Petugas dapat mengelola produk.
4. Petugas dapat membuat QR Code unik.
5. QR Code dapat digunakan untuk menemukan produk.
6. Pelanggan dapat melakukan registrasi produk.
7. Sistem dapat menentukan masa berlaku garansi.
8. Pelanggan dapat mengajukan klaim.
9. Petugas dapat memverifikasi klaim.
10. Petugas dapat mengubah status klaim.
11. Pelanggan dapat melihat status klaim.
12. Riwayat perubahan status tersimpan.
13. Petugas dapat mencatat proses servis.
14. Admin dapat melihat laporan.
15. Pengguna tidak dapat mengakses halaman yang bukan haknya.
16. Password tidak disimpan dalam bentuk plaintext.
17. File upload tervalidasi.
18. Database memiliki relasi yang sesuai.
19. Sistem tidak menggunakan `base.html`.
20. Seluruh route Flask berada di `app.py`.

---

# 43. Definition of Done

Fitur dianggap selesai apabila:

- Backend Flask telah dibuat.
- Database telah terhubung.
- Route telah tersedia.
- Validasi input telah diterapkan.
- Authentication telah berjalan.
- Authorization telah berjalan.
- Template HTML telah dibuat.
- Tidak terdapat penggunaan `base.html`.
- Data dapat disimpan dan dibaca dari MySQL.
- QR Code dapat dibuat dan digunakan.
- Upload file dapat berjalan.
- Klaim dapat diproses.
- Status klaim dapat diperbarui.
- Riwayat klaim tersimpan.
- Dashboard dapat menampilkan data.
- Error handling telah diterapkan.
- Aplikasi dapat dijalankan pada environment deployment.

---

# 44. Kesimpulan

Sistem Klaim Garansi Berbasis QR Code dirancang untuk mendigitalisasi proses registrasi produk dan klaim garansi.

Pelanggan menggunakan QR Code untuk mengakses informasi produk, melakukan registrasi, dan mengajukan klaim. Petugas bertanggung jawab dalam pengelolaan produk, verifikasi klaim, serta proses perbaikan atau penggantian. Admin bertugas mengelola petugas dan memantau aktivitas serta laporan sistem.

Sistem dibangun menggunakan **Python Flask dan MySQL** dengan pendekatan **Server-Side Rendering menggunakan Jinja2**. Seluruh routing dan logika backend ditempatkan dalam **`app.py`**, konfigurasi ditempatkan pada **`config.py`**, dan setiap halaman HTML dibuat sebagai file mandiri tanpa menggunakan `base.html`.