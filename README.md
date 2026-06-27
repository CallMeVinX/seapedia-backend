# 🌊 SEAPEDIA - Multi-Role E-Commerce Platform

SEAPEDIA adalah platform *e-commerce* komprehensif yang dirancang dengan arsitektur **Multi-Role** (Admin, Seller, Buyer, dan Driver) dalam satu akun pengguna. Proyek ini dibangun untuk memenuhi kriteria validasi bisnis dan keamanan ketat pada **Level 7 (Delivery)**.

---

## 🌐 Akses Deploy (Live App)

Aplikasi SEAPEDIA telah di-deploy dan dapat diakses publik melalui tautan berikut:

- **Frontend (Web App):** [https://seapedia-frontend.vercel.app/](https://seapedia-frontend.vercel.app/)
- **Backend (API):** [https://seapedia-backend.onrender.com](https://seapedia-backend.onrender.com)
- **API Documentation (Swagger UI):** [https://seapedia-backend.onrender.com/docs](https://seapedia-backend.onrender.com/docs)

### 👥 Kredensial Testing (Demo Accounts)

Gunakan akun berikut untuk menguji aplikasi sesuai dengan peran masing-masing:

| Role | Email | Password | Catatan |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@gmail.com` | `AdminGanteng` | Akses ke Dashboard Admin & Vouchers |
| **Seller** | `budi@seller.com` | `AlvinGanteng` | Toko "Toko Makmur", Manajemen Produk/Promo |
| **Buyer** | `alvindinata1998@gmail.com` | `AlvinGanteng` | Saldo dompet simulasi penuh untuk transaksi |
| **Driver** | `alvindinata1998@gmail.com` | `AlvinGanteng` | Akses untuk *Take Job* dan *Complete Delivery* |

---

## 🚀 Dokumentasi Aturan Bisnis

Proyek ini mendemonstrasikan logika transaksi *e-commerce* tingkat lanjut:

### 1. Single-Store Cart (Keranjang Per-Toko)
- Satu keranjang (Cart) **hanya dapat memuat produk dari satu toko yang sama**. 
- Jika Buyer mencoba memasukkan produk dari toko lain, sistem memblokir tindakan tersebut atau meminta Buyer mengosongkan keranjang sebelumnya. Ini menyederhanakan logika logistik/pengiriman.

### 2. Kalkulasi Checkout & PPN 12%
- **Subtotal:** Total harga produk dikurangi Diskon Promo/Voucher.
- **Delivery Fee:** Dihitung berdasarkan metode (Instan: 50.000, Next Day: 30.000, Reguler: 10.000).
- **PPN 12%:** Dihitung secara otomatis dari nilai pesanan kotor (gross).
- **Final Total:** `Subtotal + Delivery Fee + PPN 12%`.

### 3. Aturan Diskon (Promo vs Voucher)
- **Promo (Tingkat Toko):** Dibuat Seller untuk produk tertentu. Dibatasi oleh *Expiry Date*. Harga tercoret otomatis di katalog.
- **Voucher (Tingkat Global):** Dibuat Admin. Divalidasi saat *Checkout* dengan batasan *Max Usage* dan *Expiry Date*.

### 4. SLA Pengiriman & Simulasi Waktu (Overdue)
- **SLA (Due Date):** Instan (4 Jam), Next Day (24 Jam), Reguler (96 Jam).
- **Auto-Refund:** Jika pesanan melewati batas waktu (Overdue) dan belum diantar, dana dikembalikan ke dompet Buyer, dan pesanan dibatalkan ("Dikembalikan").
- **Cara Simulasi Waktu:** Terdapat tombol **"Simulasi (+1 Hari)"** di Dashboard Admin. Menekan tombol ini akan memanipulasi waktu sistem maju 1 hari untuk memicu *cron-job/overdue checking* secara instan.

### 5. Komisi Driver (Earning)
- Driver hanya bisa melihat pesanan berstatus "Menunggu Pengirim".
- Setelah pengiriman selesai, Driver otomatis menerima komisi sebesar **80% dari total biaya ongkos kirim (Delivery Fee)**, dan masuk langsung ke saldo dompet Driver. Sisa 20% merupakan potongan sistem.

---

## 🛡️ Dokumentasi Keamanan (Level 7)

Aplikasi ini diarsiteki dengan lapis keamanan tinggi yang diwajibkan dalam produksi nyata:

1. **SQL Injection Prevention:** Backend menggunakan *ORM (Object-Relational Mapping)* berbasis SQLAlchemy/Asyncpg. Semua variabel diikat (bind parameter) secara aman sehingga injeksi string raw SQL mustahil terjadi.
2. **XSS (Cross-Site Scripting) Prevention:** Frontend menggunakan React (Next.js) yang melakukan *auto-escaping* pada semua data yang dirender. Dilarang keras penggunaan *dangerouslySetInnerHTML* kecuali telah disanitasi.
3. **Input Validation:** Terdapat validasi dua lapis (Dual-Layer Validation). Frontend memvalidasi *form* sebelum *submit*, dan Backend menggunakan **Pydantic schemas** untuk memastikan tipe data & *constraints* wajib terpenuhi (HTTP 422 Unprocessable Entity).
4. **Session Management (First-Party Cookies):** Token otentikasi (JWT) **tidak disimpan** di *localStorage* karena rentan dicuri lewat *script*. JWT disimpan dalam *HttpOnly Cookies*. Mekanisme *Next.js Rewrites* digunakan untuk menghindari pemblokiran *third-party cookies* pada *browser* dengan privasi ketat.
5. **RBAC (Role-Based Access Control):** 
   - **Frontend:** Menggunakan *Guard Agents (Route Layouts)* yang merender halaman hanya jika sesi peran *user* valid, jika tidak dialihkan kembali (Redirect).
   - **Backend:** Menggunakan mekanisme *Dependency Injection* yang menolak API *request* (HTTP 403 Forbidden) jika pengguna tidak menggunakan peran yang sah pada sesinya.

---

## 🔄 Mekanisme Ganti Peran (Role Switching)

Karena SEAPEDIA menggunakan satu akun untuk banyak peran (Multi-Role), Anda dapat beralih peran (Buyer/Seller/Driver/Admin) kapan saja tanpa perlu login ulang. Antarmuka (UI) untuk mengganti peran akan menyesuaikan dengan perangkat yang Anda gunakan:

- **Desktop / Layar Lebar:** Gunakan tombol **Role Switcher** (menampilkan peran aktif Anda) yang terletak langsung di *Top Navbar* (berada tepat di sebelah kiri nama dan foto profil Anda).
- **Mobile / Layar Kecil (HP):** Karena keterbatasan ruang pada *Top Navbar*, menu ganti peran dipindahkan ke dalam **Dropdown Profil**. Ketuk foto profil Anda di pojok kanan atas, lalu pilih opsi **"Ganti Peran (Role)"** berikon *Users* yang muncul di dalam menu *dropdown*. *(Catatan: Menu ini otomatis muncul hanya jika akun tersebut memiliki lebih dari 1 peran).*

---

## 🧪 Panduan Testing (End-to-End)

Untuk juri atau tim penilai, berikut adalah alur simulasi lengkap:

1. **Akses Sebagai Buyer:** 
   - Login dengan akun `alvindinata1998@gmail.com`. Masuk ke halaman Katalog, tambahkan beberapa produk dari satu toko ke *cart*.
   - Lakukan Checkout menggunakan saldo Dompet dan gunakan voucher admin (jika ada).
2. **Akses Sebagai Seller:** 
   - Ganti peran *active role* ke Seller. (Atau buka tab Incognito lain dengan akun `budi@seller.com`).
   - Masuk ke Dashboard Seller -> Pesanan. Ubah status pesanan yang baru masuk dari "Menunggu Konfirmasi" menjadi "Menunggu Pengirim".
3. **Akses Sebagai Driver:** 
   - Ganti peran ke Driver. Masuk ke halaman Daftar Pekerjaan (Job).
   - Tekan "Take Job" lalu ubah status pesanan menjadi selesai (Barang Diterima). Cek dompet Driver bertambah dari komisi ongkir.
4. **Simulasi SLA (Auto-Refund):** 
   - Buat pesanan baru dengan metode Next Day (SLA 24 Jam). Konfirmasi pesanan lewat Seller, biarkan status "Menunggu Pengirim".
   - Login sebagai Admin. Tekan tombol **Simulasi (+1 Hari)** di Dashboard.
   - Periksa kembali status pesanan, sistem otomatis membatalkannya (Overdue), mengembalikan stok produk, dan me-refund saldo Buyer.

---

## ⚠️ Batasan Sistem (Known Limitations) & Future Work

Mengingat aplikasi ini dikembangkan dalam lingkup waktu dan prioritas fitur inti *e-commerce*, terdapat beberapa fitur pendukung yang saat ini belum diimplementasikan:
- **Visit Store / Profil Toko Publik:** Halaman khusus untuk melihat informasi dan katalog utuh dari satu toko secara terpisah belum tersedia. Katalog saat ini terpusat di halaman beranda.
- **Lupa Password (Reset Password):** Alur pemulihan kata sandi via email belum diaktifkan (sementara hanya ada UI). Harap ingat kata sandi Anda atau gunakan akun demo yang tersedia.
- **Payment Gateway Real-Time:** Simulasi pembayaran saat ini dipotong langsung dari saldo *Wallet* virtual bawaan sistem, belum terintegrasi dengan *payment gateway* pihak ketiga (seperti Midtrans/Stripe).

---

## 🛠️ Setup & Instalasi Lokal

### Persyaratan Sistem
- Node.js (v18+)
- Python (v3.10+)
- PostgreSQL Database (diutamakan Supabase)

### Menjalankan Backend (FastAPI)
1. Buka terminal: `cd seapedia-backend`
2. Buat & aktifkan Virtual Environment: `python -m venv venv`
3. Install dependensi: `pip install -r requirements.txt`
4. Buat file `.env` di root direktori `seapedia-backend` dengan isi:
   ```env
   DATABASE_URL="postgresql+asyncpg://postgres.[YOUR_PROJECT_REF]:[YOUR_PASSWORD]@[YOUR_DB_HOST]:6543/postgres"
   SECRET_KEY="your_supabase_jwt_secret"
   SUPABASE_URL="https://[YOUR_PROJECT_REF].supabase.co"
   SUPABASE_KEY="your_supabase_service_role_key"
   ```
5. Migrasi database (Alembic): `alembic upgrade head`
6. Jalankan server: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`

### Menjalankan Frontend (Next.js)
1. Buka terminal baru: `cd seapedia-frontend`
2. Install dependensi: `npm install`
3. Jalankan development server: `npm run dev`
4. Akses aplikasi di browser melalui `http://localhost:3000`

---
*Dibuat untuk evaluasi proyek multi-peran - COMPFEST BEM FASILKOM UI.*
