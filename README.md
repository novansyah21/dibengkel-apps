# AutoWiring v0.3.21 — Focused Terminal OCR & Loading Feedback

Versi ini melanjutkan **hasil yang sudah tersimpan dari v0.3.20**, tanpa mengulang seluruh analisis diagram, deteksi lingkaran, fuse, graph maupun penelusuran jalur.

## Cara menjalankan (Windows)

Tetap gunakan folder sebelumnya. **Jangan menghapus file output/autowiring.db atau gambar dalam sample_assets.**

~~~powershell
cd D:\dibengkelapp\AutoWiring-v0.3.3
git fetch origin
git switch --track origin/feature/v0.3.21
py viewer.py
~~~

Buka http://127.0.0.1:8765 dan tekan **Ctrl + Shift + R** agar loading.js/app.js baru digunakan.

Pilih **Junction Block**. Klik **▶ Refine 4 terminal OCR candidates (v0.3.21)** pada kartu biru paling atas. Tidak perlu klik tombol proses lama. Setelah hasil muncul, klik **Export v0.3.21 OCR & visual evidence JSON**. File keluarannya adalah **autowiring-junction_block-terminal-accuracy-v0321.json**.

## Perubahan penting

### A. Loading process saat klik tombol — seluruh aplikasi

**Setiap tombol**, termasuk tombol-tombol legacy, sekarang memunculkan **indikator aktivitas di atas gambar diagram** segera saat diklik. Indikator memperlihatkan:

- Spinner dan garis gerak **indeterminate** (bukan persentase palsu).
- Nama tombol/aksi yang sedang dijalankan.
- Jumlah permintaan API yang sudah selesai serta yang masih berjalan.
- Waktu proses yang benar-benar berlalu.
- Menunggu file gambar **selesai di-decode** dan overlay terlukis sebelum menyatakan proses selesai.
- Tanda **Selesai** atau **Gagal** setelah proses.

Ganti diagram, toggle layer dan simpan formulir juga menampilkan indikator. Proses berjalan ketika koneksi atau decode sedang aktif; kegiatan singkat tetap memberi feedback singkat. Banyak permintaan API berurutan dalam satu aksi tidak membuat spinner berkedip-kedip. Gagal memuat jaringan/gambar tidak ditandai sebagai sukses.

Di bawah ini semua adalah state UI saja, **bukan aktivitas OCR/graph tambahan**.

### B. Hanya empat terminal yang bermasalah

Semua gambar crop diambil dari lingkaran yang **sudah tersimpan dalam SQLite v0.3.20**, tidak ada circle detection ulang.

| Fuse | Posisi | Nomor lama | Pembacaan visual gambar spesifik ini |
|---|---|---|---|
| IG1 SIG | E325 main | unread | 12 |
| IG1 SIG | G272 branch | unread | 16 |
| ABS | L315 branch | unread | 6 |
| BACK | G272 branch | 2 (suspect) | 8 |

Sistem melakukan **maksimum 3 preprocessing/PSM baru per lingkaran (12 total)**, dengan crop dan raw OCR log untuk pemeriksaan. Hanya menerima kandidat OCR jika minimal **dua variant independen sepakat**. Kalau OCR membaca angka berbeda, statusnya tetap **conflict**. OCR confidence bukan confidence hubungan listrik.

**Penting:** Kolom “pembacaan visual” ditranskripsi manusia setelah memeriksa **gambar Junction Block asli yang tepat sama**; itu merupakan **referensi manual**, **bukan keluaran OCR mesin** dan **bukan pinout yang diverifikasi secara elektrik**. Referensi ini hanya aktif apabila SHA256 gambar cocok dengan sampel asli (`c9954639ad0fb133cedbe6591fd75325b6517a06239f51b3069c285d2972fde5`) dan dimensinya **1136×1598**. Pada diagram lain, sistem berhenti dengan error jelas dan tidak berpura-pura mengenali nomor terminal.

### C. Visual review & cache

Hasil empat lingkaran disimpan ke tabel terminal_accuracy_*_v0321 di database yang sama; data v0.3.16 sampai v0.3.20 **tidak diubah**. Klik kedua dengan image dan prior run sama menghasilkan **cache_hit=true**, tidak mengulang OCR baru maupun proses lama.

Pengguna bisa memilih “visually confirmed” dan memasukkan nomor terminal manual untuk dirinya sendiri, tapi **tidak melakukan verifikasi konektivitas listrik**.

Status kelistrikan tetap **electrically_verified_connections = 0**.

## Pengujian otomatis

~~~powershell
py -m pip install "Pillow>=10,<13"
py -m unittest discover -s tests -p "test_*trac*.py" -v
py -m unittest discover -s tests -p "test_terminal_accuracy.py" -v
node --test tests/test_loading_progress.cjs
~~~

GitHub Actions memeriksa compile Python, syntax JS, ketepatan empat target, konflik OCR, fingerprint cache, loading/holding gambar, route baru, dan tidak adanya pemanggilan tahapan lama dari tombol v0.3.21. Evaluasi efektivitas OCR pada gambar asli pengguna tetap dilakukan dari file JSON ekspor.
