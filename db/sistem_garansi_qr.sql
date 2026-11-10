-- =====================================================================
-- Sistem Klaim Garansi Berbasis QR Code
-- Skema database MySQL 8+
-- Jalankan: mysql -u root -p < db/sistem_garansi_qr.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS sistem_garansi_qr
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE sistem_garansi_qr;

-- ---------------------------------------------------------------------
-- 1. Pengguna
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pengguna (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(120) NOT NULL,
    email VARCHAR(160) NOT NULL,
    nomor_telepon VARCHAR(30) NULL,
    alamat TEXT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'petugas', 'pelanggan') NOT NULL,
    aktif TINYINT(1) NOT NULL DEFAULT 1,
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_pengguna_email (email),
    KEY idx_pengguna_role (role),
    KEY idx_pengguna_aktif (aktif)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 2. Kebijakan garansi
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kebijakan_garansi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(120) NOT NULL,
    durasi_bulan INT NOT NULL,
    deskripsi TEXT NULL,
    aktif TINYINT(1) NOT NULL DEFAULT 1,
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_kebijakan_aktif (aktif)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 3. Produk
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS produk (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama_produk VARCHAR(150) NOT NULL,
    kategori_model VARCHAR(120) NOT NULL,
    kebijakan_garansi_id INT NOT NULL,
    deskripsi TEXT NULL,
    status ENUM('aktif', 'nonaktif') NOT NULL DEFAULT 'aktif',
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_produk_status (status),
    KEY idx_produk_kebijakan (kebijakan_garansi_id),
    CONSTRAINT fk_produk_kebijakan
        FOREIGN KEY (kebijakan_garansi_id) REFERENCES kebijakan_garansi (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 4. Kode QR produk (satu baris = satu unit produk)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kode_qr_produk (
    id INT AUTO_INCREMENT PRIMARY KEY,
    produk_id INT NOT NULL,
    nomor_seri VARCHAR(80) NOT NULL,
    token_qr VARCHAR(80) NOT NULL,
    status ENUM('tersedia', 'terdaftar', 'nonaktif') NOT NULL DEFAULT 'tersedia',
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_qr_nomor_seri (nomor_seri),
    UNIQUE KEY uq_qr_token (token_qr),
    KEY idx_qr_produk (produk_id),
    KEY idx_qr_status (status),
    CONSTRAINT fk_qr_produk
        FOREIGN KEY (produk_id) REFERENCES produk (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 5. Registrasi produk
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS registrasi_produk (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kode_qr_id INT NOT NULL,
    pelanggan_id INT NOT NULL,
    tanggal_pembelian DATE NOT NULL,
    tempat_pembelian VARCHAR(180) NOT NULL,
    nomor_invoice VARCHAR(100) NOT NULL,
    bukti_pembelian VARCHAR(255) NOT NULL,
    status_registrasi ENUM('aktif', 'dibatalkan') NOT NULL DEFAULT 'aktif',
    diverifikasi_oleh INT NULL,
    diverifikasi_pada DATETIME NULL,
    catatan_verifikasi TEXT NULL,
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_registrasi_qr (kode_qr_id),
    KEY idx_registrasi_pelanggan (pelanggan_id),
    KEY idx_registrasi_status (status_registrasi),
    KEY idx_registrasi_verifikator (diverifikasi_oleh),
    CONSTRAINT fk_registrasi_qr
        FOREIGN KEY (kode_qr_id) REFERENCES kode_qr_produk (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT fk_registrasi_pelanggan
        FOREIGN KEY (pelanggan_id) REFERENCES pengguna (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT fk_registrasi_verifikator
        FOREIGN KEY (diverifikasi_oleh) REFERENCES pengguna (id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 6. Garansi
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS garansi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    registrasi_produk_id INT NOT NULL,
    tanggal_mulai DATE NOT NULL,
    tanggal_berakhir DATE NOT NULL,
    status ENUM('aktif', 'berakhir', 'dibatalkan') NOT NULL DEFAULT 'aktif',
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_garansi_registrasi (registrasi_produk_id),
    KEY idx_garansi_status (status),
    KEY idx_garansi_berakhir (tanggal_berakhir),
    CONSTRAINT fk_garansi_registrasi
        FOREIGN KEY (registrasi_produk_id) REFERENCES registrasi_produk (id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 7. Klaim garansi
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS klaim_garansi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    registrasi_produk_id INT NOT NULL,
    pelanggan_id INT NOT NULL,
    deskripsi_masalah TEXT NOT NULL,
    status ENUM(
        'menunggu_verifikasi',
        'sedang_ditinjau',
        'disetujui',
        'ditolak',
        'dalam_perbaikan',
        'selesai'
    ) NOT NULL DEFAULT 'menunggu_verifikasi',
    alasan_penolakan TEXT NULL,
    tanggal_klaim DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diproses_oleh INT NULL,
    tanggal_verifikasi DATETIME NULL,
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_klaim_registrasi (registrasi_produk_id),
    KEY idx_klaim_pelanggan (pelanggan_id),
    KEY idx_klaim_status (status),
    KEY idx_klaim_tanggal (tanggal_klaim),
    KEY idx_klaim_petugas (diproses_oleh),
    CONSTRAINT fk_klaim_registrasi
        FOREIGN KEY (registrasi_produk_id) REFERENCES registrasi_produk (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT fk_klaim_pelanggan
        FOREIGN KEY (pelanggan_id) REFERENCES pengguna (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT fk_klaim_petugas
        FOREIGN KEY (diproses_oleh) REFERENCES pengguna (id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 8. Lampiran klaim
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lampiran_klaim (
    id INT AUTO_INCREMENT PRIMARY KEY,
    klaim_id INT NOT NULL,
    jenis ENUM('foto_kerusakan', 'bukti_pembelian', 'lainnya') NOT NULL,
    nama_file VARCHAR(255) NOT NULL,
    path_file VARCHAR(255) NOT NULL,
    tipe_file VARCHAR(50) NULL,
    ukuran_file INT NULL,
    diunggah_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_lampiran_klaim (klaim_id),
    KEY idx_lampiran_path (path_file),
    CONSTRAINT fk_lampiran_klaim
        FOREIGN KEY (klaim_id) REFERENCES klaim_garansi (id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 9. Riwayat status klaim
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS riwayat_status_klaim (
    id INT AUTO_INCREMENT PRIMARY KEY,
    klaim_id INT NOT NULL,
    status_sebelumnya ENUM(
        'menunggu_verifikasi',
        'sedang_ditinjau',
        'disetujui',
        'ditolak',
        'dalam_perbaikan',
        'selesai'
    ) NULL,
    status_baru ENUM(
        'menunggu_verifikasi',
        'sedang_ditinjau',
        'disetujui',
        'ditolak',
        'dalam_perbaikan',
        'selesai'
    ) NOT NULL,
    diubah_oleh INT NULL,
    catatan TEXT NULL,
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_riwayat_klaim (klaim_id),
    KEY idx_riwayat_pengguna (diubah_oleh),
    CONSTRAINT fk_riwayat_klaim
        FOREIGN KEY (klaim_id) REFERENCES klaim_garansi (id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_riwayat_pengguna
        FOREIGN KEY (diubah_oleh) REFERENCES pengguna (id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 10. Catatan servis
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catatan_servis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    klaim_id INT NOT NULL,
    petugas_id INT NULL,
    hasil_pemeriksaan TEXT NULL,
    tindakan_perbaikan TEXT NULL,
    komponen_diganti VARCHAR(255) NULL,
    penggantian_produk TINYINT(1) NOT NULL DEFAULT 0,
    catatan_tambahan TEXT NULL,
    tanggal_proses DATE NULL,
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_servis_klaim (klaim_id),
    KEY idx_servis_petugas (petugas_id),
    CONSTRAINT fk_servis_klaim
        FOREIGN KEY (klaim_id) REFERENCES klaim_garansi (id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_servis_petugas
        FOREIGN KEY (petugas_id) REFERENCES pengguna (id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 11. Notifikasi
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifikasi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pengguna_id INT NOT NULL,
    klaim_id INT NULL,
    judul VARCHAR(150) NOT NULL,
    pesan TEXT NOT NULL,
    dibaca TINYINT(1) NOT NULL DEFAULT 0,
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_notifikasi_pengguna (pengguna_id),
    KEY idx_notifikasi_dibaca (dibaca),
    KEY idx_notifikasi_klaim (klaim_id),
    CONSTRAINT fk_notifikasi_pengguna
        FOREIGN KEY (pengguna_id) REFERENCES pengguna (id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_notifikasi_klaim
        FOREIGN KEY (klaim_id) REFERENCES klaim_garansi (id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- 12. Log aktivitas
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS log_aktivitas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pengguna_id INT NULL,
    aksi VARCHAR(100) NOT NULL,
    deskripsi TEXT NULL,
    alamat_ip VARCHAR(45) NULL,
    dibuat_pada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_log_pengguna (pengguna_id),
    KEY idx_log_dibuat (dibuat_pada),
    CONSTRAINT fk_log_pengguna
        FOREIGN KEY (pengguna_id) REFERENCES pengguna (id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- View laporan
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_laporan_klaim_garansi AS
SELECT
    k.id AS klaim_id,
    k.tanggal_klaim,
    k.status AS status_klaim,
    k.alasan_penolakan,
    u.id AS pelanggan_id,
    u.nama AS nama_pelanggan,
    u.email AS email_pelanggan,
    u.nomor_telepon AS telepon_pelanggan,
    p.id AS produk_id,
    p.nama_produk,
    p.kategori_model,
    q.nomor_seri,
    q.token_qr,
    r.id AS registrasi_id,
    r.tanggal_pembelian,
    r.tempat_pembelian,
    r.nomor_invoice,
    g.tanggal_mulai AS tanggal_mulai_garansi,
    g.tanggal_berakhir AS tanggal_berakhir_garansi,
    g.status AS status_garansi,
    k.diproses_oleh AS petugas_id,
    pt.nama AS nama_petugas,
    k.tanggal_verifikasi
FROM klaim_garansi k
JOIN pengguna u ON u.id = k.pelanggan_id
JOIN registrasi_produk r ON r.id = k.registrasi_produk_id
JOIN kode_qr_produk q ON q.id = r.kode_qr_id
JOIN produk p ON p.id = q.produk_id
LEFT JOIN garansi g ON g.registrasi_produk_id = r.id
LEFT JOIN pengguna pt ON pt.id = k.diproses_oleh;

-- ---------------------------------------------------------------------
-- Data awal / demo
-- Password:
--   admin@garansi.local     -> Admin123!
--   petugas@garansi.local   -> Petugas123!
--   pelanggan@garansi.local -> Pelanggan123!
-- ---------------------------------------------------------------------
INSERT INTO kebijakan_garansi (id, nama, durasi_bulan, deskripsi, aktif)
VALUES
    (1, 'Garansi Standar 12 Bulan', 12, 'Garansi standar untuk produk elektronik rumah tangga.', 1),
    (2, 'Garansi Premium 24 Bulan', 24, 'Garansi diperpanjang untuk produk premium.', 1),
    (3, 'Garansi Dasar 6 Bulan', 6, 'Garansi dasar untuk aksesori dan produk pendukung.', 1)
ON DUPLICATE KEY UPDATE
    nama = VALUES(nama),
    durasi_bulan = VALUES(durasi_bulan),
    deskripsi = VALUES(deskripsi),
    aktif = VALUES(aktif);

INSERT INTO produk
    (id, nama_produk, kategori_model, kebijakan_garansi_id, deskripsi, status)
VALUES
    (1, 'Air Purifier A1', 'Elektronik Rumah Tangga', 1,
     'Pembersih udara dengan filter HEPA dan mode otomatis.', 'aktif'),
    (2, 'Smart Blender B2', 'Elektronik Dapur', 2,
     'Blender pintar dengan pengaturan kecepatan otomatis.', 'aktif'),
    (3, 'Lampu LED Portabel L3', 'Aksesori', 3,
     'Lampu LED portabel dengan baterai isi ulang.', 'aktif')
ON DUPLICATE KEY UPDATE
    nama_produk = VALUES(nama_produk),
    kategori_model = VALUES(kategori_model),
    kebijakan_garansi_id = VALUES(kebijakan_garansi_id),
    deskripsi = VALUES(deskripsi),
    status = VALUES(status);

INSERT INTO kode_qr_produk (id, produk_id, nomor_seri, token_qr, status)
VALUES
    (1, 1, 'PRD001-DEMO-0001', 'DEMOQR0000000001', 'tersedia'),
    (2, 1, 'PRD001-DEMO-0002', 'DEMOQR0000000002', 'tersedia'),
    (3, 2, 'PRD002-DEMO-0001', 'DEMOQR0000000003', 'tersedia'),
    (4, 2, 'PRD002-DEMO-0002', 'DEMOQR0000000004', 'tersedia'),
    (5, 3, 'PRD003-DEMO-0001', 'DEMOQR0000000005', 'tersedia')
ON DUPLICATE KEY UPDATE
    produk_id = VALUES(produk_id),
    nomor_seri = VALUES(nomor_seri),
    status = VALUES(status);

INSERT INTO pengguna
    (id, nama, email, nomor_telepon, alamat, password_hash, role, aktif)
VALUES
    (
        1,
        'Administrator',
        'admin@garansi.local',
        '081100000001',
        'Kantor Pusat',
        'scrypt:32768:8:1$jckplK11eCBDESJs$9684d1dda7116561bf6441fd17fd3e7fed79b3774d07c4d88ff612f744d71003c743368de6a568d232c41bde5fdaedfc737bd61b7b04324d05a73f097c4e3cbf',
        'admin',
        1
    ),
    (
        2,
        'Petugas Demo',
        'petugas@garansi.local',
        '081100000002',
        'Kantor Layanan',
        'scrypt:32768:8:1$VWHB5bVO6EZl2icP$3d5edc5eea96d7002d955f74f26e867f58225614a08936e39ae44e9aa9efc1ed4c5c161b6fe82729536f3b8993a741394805c9f7d58a1ddeca18edcd919363e3',
        'petugas',
        1
    ),
    (
        3,
        'Pelanggan Demo',
        'pelanggan@garansi.local',
        '081100000003',
        'Jl. Contoh No. 1',
        'scrypt:32768:8:1$waKb5rtRHl8lmjXm$f3aacf85b15c9290ac344dad543791259f80033652f5254a00e8fcf54c4af63c00aecb1370036ff4dc5114eb01584b63b54c434876f76bf6a164dadfced134e4',
        'pelanggan',
        1
    )
ON DUPLICATE KEY UPDATE
    nama = VALUES(nama),
    nomor_telepon = VALUES(nomor_telepon),
    alamat = VALUES(alamat),
    password_hash = VALUES(password_hash),
    role = VALUES(role),
    aktif = VALUES(aktif);
