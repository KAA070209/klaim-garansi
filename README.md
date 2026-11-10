# Sistem Klaim Garansi Berbasis QR Code

Aplikasi Flask + MySQL (MariaDB) untuk registrasi produk dan klaim garansi
berbasis QR Code. Frontend dirender server-side dengan Jinja2 tanpa
`base.html`; seluruh route dan logika backend berada di `app.py`.

## Fitur

- Autentikasi sesi dengan password hashing dan otorisasi berbasis role
  (`admin`, `petugas`, `pelanggan`).
- Admin: dashboard, pengelolaan akun petugas, laporan klaim, filter laporan,
  dan log aktivitas.
- Petugas: dashboard, pengelolaan produk, generate QR Code unik, daftar
  pelanggan/registrasi, verifikasi klaim, perubahan status, catatan servis.
- Pelanggan: registrasi akun, registrasi produk via QR, lihat garansi,
  ajukan klaim dengan lampiran, lihat riwayat/status, notifikasi.
- Halaman QR publik `/qr/<token_qr>` dan gambar QR `/qr/<token_qr>/gambar.png`.
- Perhitungan masa garansi otomatis dari tanggal pembelian + durasi kebijakan.
- Validasi upload (jpg/jpeg/png/webp, maks. 5 MB per file), nama file UUID,
  dan penyajian berkas melalui route terproteksi `/berkas/<path>`.
- Transisi status klaim dijaga:
  `menunggu_verifikasi -> sedang_ditinjau -> disetujui|ditolak`,
  lalu `disetujui -> dalam_perbaikan -> selesai`.
- Error handler 403/404/413/500 tanpa membocorkan detail sensitif.

## Struktur Proyek

```text
sistem-klaim-garansi/
├── app.py
├── config.py
├── requirements.txt
├── .env
├── .env.example
├── templates/
│   ├── login.html
│   ├── register.html
│   ├── qr_info.html
│   ├── errors/
│   ├── admin/
│   ├── petugas/
│   └── pelanggan/
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   └── uploads/{bukti,kerusakan,klaim}/
└── db/sistem_garansi_qr.sql
```

## Persiapan

1. Pastikan Python 3.11+ dan MySQL/MariaDB tersedia.
2. Buat virtual environment dan pasang dependensi:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Salin `.env.example` menjadi `.env`, lalu sesuaikan kredensial database
   dan `SECRET_KEY`.

4. Impor skema dan data demo:

   ```powershell
   mysql -u root -p < db/sistem_garansi_qr.sql
   ```

   Dengan XAMPP, gunakan `C:\xampp\mysql\bin\mysql.exe`.

## Menjalankan

```powershell
.\.venv\Scripts\python.exe app.py
```

Buka `http://127.0.0.1:5000`. Untuk production, gunakan Gunicorn:

```bash
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

## Akun Demo

| Role      | Email                    | Password      |
|-----------|--------------------------|---------------|
| Admin     | admin@garansi.local      | `Admin123!`   |
| Petugas   | petugas@garansi.local    | `Petugas123!` |
| Pelanggan | pelanggan@garansi.local  | `Pelanggan123!` |

Token QR demo: `DEMOQR0000000001` sampai `DEMOQR0000000005`.
Contoh: `http://127.0.0.1:5000/qr/DEMOQR0000000001`.

## Catatan Keamanan

- Folder `static/uploads/` tidak boleh diakses langsung; semua berkas
  dilayani lewat `/berkas/<path>` yang memeriksa kepemilikan.
- Ganti `SECRET_KEY` dan password database sebelum deployment.
- Set `SESSION_COOKIE_SECURE=1` jika aplikasi berjalan di HTTPS.
- Isi `PUBLIC_BASE_URL` bila aplikasi berada di balik proxy agar isi QR
  mengarah ke domain publik yang benar.
