-- Basis Data: Sistem Klaim Garansi Produk Elektronik melalui QR Code
-- Nama tabel dan kolom menggunakan Bahasa Indonesia.
-- Target: MySQL 8.0+
-- PERINGATAN: Skrip ini menghapus tabel bernama sama jika sudah ada di basis data tujuan.
-- Cadangkan data terlebih dahulu sebelum menjalankan ulang pada basis data yang berisi data penting.

CREATE DATABASE IF NOT EXISTS sistem_garansi_qr
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE sistem_garansi_qr;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP VIEW IF EXISTS v_laporan_klaim_garansi;
DROP TABLE IF EXISTS log_aktivitas;
DROP TABLE IF EXISTS notifikasi;
DROP TABLE IF EXISTS catatan_servis;
DROP TABLE IF EXISTS riwayat_status_klaim;
DROP TABLE IF EXISTS lampiran_klaim;
DROP TABLE IF EXISTS klaim_garansi;
DROP TABLE IF EXISTS garansi;
DROP TABLE IF EXISTS registrasi_produk;
DROP TABLE IF EXISTS kode_qr_produk;
DROP TABLE IF EXISTS produk;
DROP TABLE IF EXISTS kebijakan_garansi;
DROP TABLE IF EXISTS pengguna;

SET FOREIGN_KEY_CHECKS = 1;

-- 1. Akun Admin, Petugas, dan Pelanggan
CREATE TABLE pengguna (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    nama_lengkap VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    kata_sandi VARCHAR(255) NOT NULL COMMENT 'Simpan hash kata sandi, bukan teks asli',
    peran ENUM('admin', 'petugas', 'pelanggan') NOT NULL,
    nomor_telepon VARCHAR(20) NULL,
    status_aktif TINYINT(1) NOT NULL DEFAULT 1,
    email_terverifikasi_pada DATETIME NULL,
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unik_pengguna_email (email),
    KEY indeks_pengguna_peran_status (peran, status_aktif)
) ENGINE=InnoDB;

-- 2. Aturan dan durasi garansi
CREATE TABLE kebijakan_garansi (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    nama_kebijakan VARCHAR(100) NOT NULL,
    durasi_bulan INT UNSIGNED NOT NULL,
    syarat_ketentuan TEXT NULL,
    status_aktif TINYINT(1) NOT NULL DEFAULT 1,
    dibuat_oleh BIGINT UNSIGNED NULL,
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY indeks_kebijakan_status (status_aktif),
    CONSTRAINT fk_kebijakan_dibuat_oleh
        FOREIGN KEY (dibuat_oleh) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 3. Model atau jenis produk elektronik
CREATE TABLE produk (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    kode_produk VARCHAR(50) NOT NULL,
    nama_produk VARCHAR(150) NOT NULL,
    merek VARCHAR(100) NOT NULL,
    kategori VARCHAR(100) NOT NULL,
    deskripsi TEXT NULL,
    kebijakan_garansi_id BIGINT UNSIGNED NOT NULL,
    dibuat_oleh BIGINT UNSIGNED NULL,
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unik_produk_kode (kode_produk),
    KEY indeks_produk_nama (nama_produk),
    KEY indeks_produk_merek_kategori (merek, kategori),
    CONSTRAINT fk_produk_kebijakan
        FOREIGN KEY (kebijakan_garansi_id) REFERENCES kebijakan_garansi(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_produk_dibuat_oleh
        FOREIGN KEY (dibuat_oleh) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 4. Identitas setiap unit fisik dan token QR unik
CREATE TABLE kode_qr_produk (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    produk_id BIGINT UNSIGNED NOT NULL,
    nomor_seri VARCHAR(100) NOT NULL,
    token_qr CHAR(64) NOT NULL COMMENT 'Token acak unik; QR mengarah ke URL verifikasi',
    status ENUM('aktif', 'terdaftar', 'diblokir') NOT NULL DEFAULT 'aktif',
    dibuat_oleh BIGINT UNSIGNED NULL,
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unik_qr_nomor_seri (nomor_seri),
    UNIQUE KEY unik_qr_token (token_qr),
    KEY indeks_qr_produk_status (produk_id, status),
    CONSTRAINT fk_qr_produk
        FOREIGN KEY (produk_id) REFERENCES produk(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_qr_dibuat_oleh
        FOREIGN KEY (dibuat_oleh) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 5. Registrasi produk oleh pelanggan
CREATE TABLE registrasi_produk (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    pelanggan_id BIGINT UNSIGNED NOT NULL,
    kode_qr_produk_id BIGINT UNSIGNED NOT NULL,
    tanggal_pembelian DATE NOT NULL,
    tempat_pembelian VARCHAR(150) NULL,
    nomor_nota VARCHAR(100) NULL,
    status_registrasi ENUM('menunggu', 'terverifikasi', 'ditolak') NOT NULL DEFAULT 'menunggu',
    diverifikasi_oleh BIGINT UNSIGNED NULL,
    diverifikasi_pada DATETIME NULL,
    didaftarkan_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unik_registrasi_qr (kode_qr_produk_id),
    KEY indeks_registrasi_pelanggan (pelanggan_id, didaftarkan_pada),
    KEY indeks_registrasi_status (status_registrasi),
    CONSTRAINT fk_registrasi_pelanggan
        FOREIGN KEY (pelanggan_id) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_registrasi_qr
        FOREIGN KEY (kode_qr_produk_id) REFERENCES kode_qr_produk(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_registrasi_verifikator
        FOREIGN KEY (diverifikasi_oleh) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 6. Catatan masa berlaku garansi per unit produk terdaftar
CREATE TABLE garansi (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    registrasi_produk_id BIGINT UNSIGNED NOT NULL,
    tanggal_mulai DATE NOT NULL,
    tanggal_berakhir DATE NOT NULL,
    status_garansi ENUM('aktif', 'kedaluwarsa', 'dibatalkan') NOT NULL DEFAULT 'aktif',
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unik_garansi_registrasi (registrasi_produk_id),
    KEY indeks_garansi_status_tanggal (status_garansi, tanggal_mulai, tanggal_berakhir),
    CONSTRAINT fk_garansi_registrasi
        FOREIGN KEY (registrasi_produk_id) REFERENCES registrasi_produk(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT cek_tanggal_garansi CHECK (tanggal_berakhir >= tanggal_mulai)
) ENGINE=InnoDB;

-- 7. Pengajuan klaim garansi oleh pelanggan
CREATE TABLE klaim_garansi (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    nomor_klaim VARCHAR(50) NOT NULL,
    garansi_id BIGINT UNSIGNED NOT NULL,
    pelanggan_id BIGINT UNSIGNED NOT NULL,
    petugas_penanggung_jawab_id BIGINT UNSIGNED NULL,
    deskripsi_kerusakan TEXT NOT NULL,
    diajukan_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status_klaim ENUM(
        'menunggu_verifikasi',
        'sedang_ditinjau',
        'disetujui',
        'ditolak',
        'dalam_perbaikan',
        'selesai'
    ) NOT NULL DEFAULT 'menunggu_verifikasi',
    catatan_keputusan TEXT NULL,
    diputuskan_oleh BIGINT UNSIGNED NULL,
    diputuskan_pada DATETIME NULL,
    diperbarui_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unik_nomor_klaim (nomor_klaim),
    KEY indeks_klaim_pelanggan (pelanggan_id, diajukan_pada),
    KEY indeks_klaim_status (status_klaim, diajukan_pada),
    KEY indeks_klaim_petugas (petugas_penanggung_jawab_id, status_klaim),
    CONSTRAINT fk_klaim_garansi
        FOREIGN KEY (garansi_id) REFERENCES garansi(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_klaim_pelanggan
        FOREIGN KEY (pelanggan_id) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_klaim_petugas
        FOREIGN KEY (petugas_penanggung_jawab_id) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_klaim_diputuskan_oleh
        FOREIGN KEY (diputuskan_oleh) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 8. Foto kerusakan, nota, dan dokumen pendukung klaim
CREATE TABLE lampiran_klaim (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    klaim_garansi_id BIGINT UNSIGNED NOT NULL,
    lokasi_berkas VARCHAR(500) NOT NULL,
    jenis_berkas VARCHAR(100) NULL,
    keterangan VARCHAR(255) NULL,
    diunggah_oleh BIGINT UNSIGNED NULL,
    diunggah_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY indeks_lampiran_klaim (klaim_garansi_id),
    CONSTRAINT fk_lampiran_klaim
        FOREIGN KEY (klaim_garansi_id) REFERENCES klaim_garansi(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_lampiran_pengunggah
        FOREIGN KEY (diunggah_oleh) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 9. Riwayat perubahan status klaim
CREATE TABLE riwayat_status_klaim (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    klaim_garansi_id BIGINT UNSIGNED NOT NULL,
    diubah_oleh BIGINT UNSIGNED NULL,
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
    catatan TEXT NULL,
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY indeks_riwayat_klaim_waktu (klaim_garansi_id, dibuat_pada),
    CONSTRAINT fk_riwayat_klaim
        FOREIGN KEY (klaim_garansi_id) REFERENCES klaim_garansi(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_riwayat_pengubah
        FOREIGN KEY (diubah_oleh) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 10. Catatan pemeriksaan, perbaikan, atau penggantian produk
CREATE TABLE catatan_servis (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    klaim_garansi_id BIGINT UNSIGNED NOT NULL,
    jenis_tindakan ENUM('pemeriksaan', 'perbaikan', 'penggantian') NOT NULL,
    deskripsi TEXT NULL,
    status_servis ENUM('menunggu', 'sedang_dikerjakan', 'selesai') NOT NULL DEFAULT 'menunggu',
    mulai_pada DATETIME NULL,
    selesai_pada DATETIME NULL,
    dibuat_oleh BIGINT UNSIGNED NULL,
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    diperbarui_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY indeks_servis_klaim_status (klaim_garansi_id, status_servis),
    CONSTRAINT fk_servis_klaim
        FOREIGN KEY (klaim_garansi_id) REFERENCES klaim_garansi(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_servis_dibuat_oleh
        FOREIGN KEY (dibuat_oleh) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 11. Notifikasi di dalam aplikasi
CREATE TABLE notifikasi (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    pengguna_id BIGINT UNSIGNED NOT NULL,
    klaim_garansi_id BIGINT UNSIGNED NULL,
    judul VARCHAR(150) NOT NULL,
    pesan TEXT NOT NULL,
    sudah_dibaca TINYINT(1) NOT NULL DEFAULT 0,
    dibaca_pada DATETIME NULL,
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY indeks_notifikasi_pengguna_baca (pengguna_id, sudah_dibaca, dibuat_pada),
    CONSTRAINT fk_notifikasi_pengguna
        FOREIGN KEY (pengguna_id) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_notifikasi_klaim
        FOREIGN KEY (klaim_garansi_id) REFERENCES klaim_garansi(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- 12. Catatan aktivitas Admin dan Petugas
CREATE TABLE log_aktivitas (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    pengguna_id BIGINT UNSIGNED NULL,
    tindakan VARCHAR(100) NOT NULL,
    jenis_data VARCHAR(100) NULL,
    id_data BIGINT UNSIGNED NULL,
    rincian JSON NULL,
    alamat_ip VARCHAR(45) NULL,
    peramban VARCHAR(500) NULL,
    dibuat_pada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY indeks_log_pengguna_waktu (pengguna_id, dibuat_pada),
    KEY indeks_log_data (jenis_data, id_data),
    CONSTRAINT fk_log_pengguna
        FOREIGN KEY (pengguna_id) REFERENCES pengguna(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- Tampilan laporan klaim untuk Admin/Petugas
CREATE OR REPLACE VIEW v_laporan_klaim_garansi AS
SELECT
    kg.id AS id_klaim,
    kg.nomor_klaim,
    kg.status_klaim,
    kg.diajukan_pada,
    pl.id AS id_pelanggan,
    pl.nama_lengkap AS nama_pelanggan,
    pl.email AS email_pelanggan,
    pr.id AS id_produk,
    pr.kode_produk,
    pr.nama_produk,
    pr.merek,
    pr.kategori,
    qrp.nomor_seri,
    g.tanggal_mulai AS tanggal_mulai_garansi,
    g.tanggal_berakhir AS tanggal_akhir_garansi,
    pt.id AS id_petugas,
    pt.nama_lengkap AS nama_petugas
FROM klaim_garansi kg
JOIN garansi g ON g.id = kg.garansi_id
JOIN registrasi_produk rp ON rp.id = g.registrasi_produk_id
JOIN kode_qr_produk qrp ON qrp.id = rp.kode_qr_produk_id
JOIN produk pr ON pr.id = qrp.produk_id
JOIN pengguna pl ON pl.id = kg.pelanggan_id
LEFT JOIN pengguna pt ON pt.id = kg.petugas_penanggung_jawab_id;

-- Tidak ada akun bawaan.
-- Buat akun Admin melalui proses seed yang aman dan simpan kata sandi dalam bentuk hash.
-- Alur: Admin membuat akun Petugas; Petugas mengelola produk dan QR;
-- Pelanggan memindai QR, mendaftarkan produk, lalu garansi dibuat setelah data pembelian
-- memenuhi aturan perusahaan. Pelanggan mengajukan klaim dan Petugas memprosesnya.
