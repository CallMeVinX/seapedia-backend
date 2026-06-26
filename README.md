# 🌊 SEAPEDIA - Multi-Role E-Commerce Platform

SEAPEDIA adalah platform *e-commerce* komprehensif yang dirancang dengan arsitektur **Multi-Role** (Admin, Seller, Buyer, dan Driver) dalam satu akun pengguna. Proyek ini dibangun untuk memenuhi kriteria ketat dengan fitur-fitur transaksi tingkat lanjut seperti perhitungan pajak PPN, logika diskon ganda (Promo & Voucher), serta manajemen keranjang per-toko (Single-Store Cart).

---

## 🚀 Fitur Utama & Aturan Bisnis

### 1. Single-Store Cart (Keranjang Per-Toko)
Untuk mempermudah manajemen logistik dan pengiriman, SEAPEDIA menerapkan kebijakan **Single-Store Checkout**. 
- Satu keranjang (Cart) **hanya dapat memuat produk dari satu toko yang sama**. 
- Jika Buyer mencoba memasukkan produk dari toko lain, sistem akan memblokir tindakan tersebut atau meminta Buyer untuk mengosongkan keranjang sebelumnya.

### 2. Kalkulasi Checkout & PPN 12%
Setiap transaksi yang dilakukan di SEAPEDIA tunduk pada aturan pajak yang berlaku.
- **Subtotal:** Total harga produk setelah dikurangi Diskon/Promo/Voucher.
- **Delivery Fee:** Dihitung berdasarkan metode pengiriman (Instan: 50.000, Next Day: 30.000, Reguler: 10.000).
- **PPN 12%:** Dihitung secara otomatis dari nilai pesanan.
- **Final Total:** `Subtotal + Delivery Fee + PPN 12%`.

### 3. Aturan Diskon (Promo vs Voucher)
- **Promo (Tingkat Toko):** Dibuat oleh Seller untuk produk tertentu. Hanya dibatasi oleh **Waktu Kedaluwarsa (Expiry Date)**. Harga produk akan otomatis terpotong di katalog publik.
- **Voucher (Tingkat Global):** Dibuat oleh Admin. Memiliki batasan ganda: **Batas Kuota Penggunaan (Max Usage)** dan **Waktu Kedaluwarsa**. Tervalidasi langsung di halaman *Checkout*.

### 4. SLA Pengiriman & Simulasi Overdue
Sistem dilengkapi mitigasi keterlambatan pengiriman melalui mekanisme SLA (Service Level Agreement) yang dihitung secara presisi dalam satuan jam:
- **Batas Waktu Pengiriman (Due Date):**
  - **Instan**: 4 Jam setelah pesanan dibuat
  - **Next Day**: 24 Jam (1 hari pas) setelah pesanan dibuat
  - **Reguler**: 96 Jam (4 hari) setelah pesanan dibuat
- **Mekanisme Overdue:** Jika pesanan belum dikirim/selesai melewati batas waktu SLA (Due Date) di atas, pesanan berstatus **Overdue** dan memicu mekanisme **Auto-Refund** atau **Auto-Return**.
- **Dampak Auto-Refund:** Uang dikembalikan penuh ke *Wallet* Buyer, stok produk dikembalikan ke toko, dan potensi pendapatan Seller dibatalkan. Status pesanan menjadi `"Dikembalikan"`.
- **Simulasi (Time Travel):** Anda dapat menyimulasikan sistem *Overdue* ini dengan menekan tombol **"Simulasi (+1 Hari)"** di Dashboard Admin. Sebagai contoh: Jika Anda baru saja memesan dengan metode *Next Day* (SLA 24 jam), menekan simulasi maju 1 hari akan memicu waktu sistem mencapai *Due Date*, sehingga pesanan tersebut akan otomatis terdeteksi *Overdue* dan langsung di-refund. Ini mempermudah juri untuk menguji efektivitas cron-job atau pengecekan *overdue* secara instan.

### 5. Alur Kerja & Pendapatan Driver
Sistem memastikan satu pesanan diantar oleh satu pengemudi secara eksklusif.
- Driver hanya dapat melihat daftar pekerjaan (Job) untuk pesanan yang telah dikonfirmasi penjual (Status: `"Menunggu Pengirim"`).
- Saat Driver menekan **"Take Job"**, status pesanan berubah menjadi `"Sedang Dikirim"`.
- Setelah barang tiba, Driver mengonfirmasi penyelesaian, yang otomatis memberikan **Komisi Driver (Earning)** sebesar **80% dari total biaya ongkos kirim (Delivery Fee)** langsung ke dompet *Driver*. Sisa 20% adalah potongan sistem.

---

## 🛠️ Setup & Instalasi Lokal

Proyek ini terdiri dari dua bagian: **Frontend** (Next.js) dan **Backend** (FastAPI).

### Persyaratan Sistem
- Node.js (v18+)
- Python (v3.10+)
- PostgreSQL Database

### Menjalankan Backend (FastAPI)
1. Buka terminal dan masuk ke direktori backend: `cd seapedia-backend`
2. Buat Virtual Environment: `python -m venv venv` dan aktifkan.
3. Install dependensi: `pip install -r requirements.txt`
4. Buat file `.env` di root direktori `seapedia-backend` dan sesuaikan dengan kredensial database Supabase Anda. Berikut adalah variabel yang perlu diisi:
   ```env
   # URI Koneksi Database (Bisa didapat di Supabase: Project Settings -> Database)
   # Pastikan Anda menggunakan driver `postgresql+asyncpg`
   DATABASE_URL="postgresql+asyncpg://postgres.[YOUR_PROJECT_REF]:[YOUR_DB_PASSWORD]@[YOUR_DB_HOST]:6543/postgres"

   # JWT Secret (Bisa didapat di Supabase: Project Settings -> API)
   SECRET_KEY="your_supabase_jwt_secret"

   # URL Project Supabase (Bisa didapat di Supabase: Project Settings -> API)
   SUPABASE_URL="https://[YOUR_PROJECT_REF].supabase.co"

   # Anon/Service Role Key Supabase (Bisa didapat di Supabase: Project Settings -> API)
   SUPABASE_KEY="your_supabase_service_role_key"
   ```
5. Jalankan migrasi database (Alembic): `alembic upgrade head`
6. Jalankan server: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
*Swagger UI API Documentation dapat diakses di `https://seapedia-backend.onrender.com/docs`*

### Menjalankan Frontend (Next.js)
1. Buka terminal baru dan masuk ke direktori frontend: `cd seapedia-frontend`
2. Install dependensi: `npm install`
3. Sesuaikan file `.env` jika diperlukan (atur `NEXT_PUBLIC_API_URL=http://localhost:8000/api`).
4. Jalankan development server: `npm run dev`
5. Akses aplikasi di browser melalui `http://localhost:3000`

---

## 👥 Demo Accounts (Testing)

Gunakan akun berikut untuk menguji aplikasi sesuai dengan peran masing-masing (Pastikan Anda mendaftarkannya terlebih dahulu jika database masih kosong):

| Role | Email | Password | Catatan |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@gmail.com` | `AdminGanteng` | Memiliki akses ke Dashboard Admin & Vouchers |
| **Seller** | `budi@seller.com` | `AlvinGanteng` | Memiliki toko "Toko Makmur" & Manajemen Produk/Promo |
| **Buyer** | `alvindinata1998@gmail.com` | `AlvinGanteng` | Dilengkapi saldo dompet simulasi untuk transaksi |
| **Driver** | `alvindinata1998@gmail.com` | `AlvinGanteng` | Akses untuk *Take Job* dan *Complete Delivery* |

---
*Dibuat untuk evaluasi proyek multi-peran - COMPFEST BEM FASILKOM UI.*
