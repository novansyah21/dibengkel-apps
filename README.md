# AutoWiring MVP 0.1 — Assisted Wiring Review (v0.3.22)

**Status: MVP review-assist untuk satu gambar Junction Block. Bukan diagnostic assistant otomatis.**

Setelah pengujian v0.3.21, keempat nomor terminal bermasalah masih **0/4 lolos OCR consensus**. Menaikkan confidence atau memaksakan nomor dari referensi manusia akan menyembunyikan kesalahan. Eksperimen lokal circle-border suppression memperjelas bentuk angka pada beberapa crop tetapi juga **menghapus sebagian guratan digit**, sehingga **bukan pengenal angka yang tervalidasi**. v0.3.22 menyediakan tampilan original vs masked untuk **pemeriksaan manusia**, tanpa menyebutnya machine recognition.

## Jalankan di Windows — tetap dengan database lama

**Jangan menghapus folder output atau file output/autowiring.db.** Semua hasil sebelumnya disimpan di sana. Pastikan gambar Junction Block sumber tetap ada di sample_assets.

~~~powershell
cd D:\dibengkelapp\AutoWiring-v0.3.3
git fetch origin
git switch --track origin/feature/v0.3.22-mvp
py viewer.py
~~~

Buka **http://127.0.0.1:8765**, kemudian tekan **Ctrl + Shift + R** sekali.

## Cara pakai MVP

1. Pilih **Junction Block**.
2. Klik tombol hijau/biru **▶ Load saved six-fuse MVP report** di bagian paling atas.
3. Tinjau **6 kandidat fuse**, rating, jalur utama, 5 cabang/continuation dan tanda putus-putus pada gambar.
4. Di bagian **4 terminal requiring manual visual review**, bandingkan gambar lingkaran asli dan gambar experimental border mask. Masukkan **nomor yang lu lihat sendiri**, pilih **Confirm number VISUALLY**, lalu **Save manual visual decision**. Jangan mengisi nomor hanya karena visual reference menunjukkan angka tertentu jika belum diperiksa.
5. Gunakan **Save audit snapshot** untuk menyimpan hasil saat ini (idempotent, tidak membuat salinan baru jika review tidak berubah).
6. **Export MVP review JSON** atau **Export wiring checklist CSV**. Bagikan file JSON untuk evaluasi berikutnya.

Semua tombol, termasuk tombol analisis lama, tetap menampilkan **spinner/loading di atas gambar**, penghitung request yang selesai/belum, waktu berjalan, dan notifikasi selesai/gagal. **Tidak ada persentase palsu.**

## Cakupan MVP yang faktual

| Kemampuan | Status |
|---|---|
| Viewer/zoom/pan/annotation | Ada |
| Kandidat fuse pada gambar Junction Block tertentu | 6 (source-locked, tidak generik) |
| Rating kandidat | 6 |
| Kandidat main path | 6 |
| Kandidat cabang/continuation | 5, termasuk satu off-page continuation |
| Terminal visual reference yang butuh review | 4 |
| OCR otomatis baru yang lolos v0.3.21 | 0/4 |
| Elektrikal continuity yang diverifikasi | **0** |
| Diagnosis otomatis / dukungan diagram kendaraan lain | **Tidak tersedia** |

Berikut **empat nomor yang tampil sebagai referensi visual manusia, BUKAN machine OCR**:

- IG1 SIG main: E325 / **12**
- IG1 SIG branch: G272 / **16**
- ABS branch: L315 / **6**
- BACK branch: G272 / **8** (mesin sebelumnya membaca **2**, yang tidak boleh otomatis dianggap benar)

Laporan tidak diam-diam mengubah angka mesin dari 2 menjadi 8. Sebelum review, nomor efektif untuk empat target masih **unknown**, dan referensi visual disimpan di kolom terpisah. Ketika pengguna mengonfirmasi, status menjadi **human_visual_review_only** — **bukan electrically verified**.

## Apa arti tombol "Save audit snapshot"?

Menyimpan salinan immutable laporan review di tabel SQLite mvp_snapshots_v0322, termasuk ID run v0.3.20 dan v0.3.21, SHA gambar, keputusan manual, kandidat fuse, dan status bukti. Bila tidak ada keputusan baru, fingerprint menghasilkan cache hit dan tidak menambah snapshot duplikat. OCR/graph/segmentation/branch tracing **tidak diulang**.

CSV sengaja menampilkan kolom **Electrical verified: NO** untuk seluruh baris.

## Batas keandalan dan acceptance gate

**MVP ini layak hanya sebagai aplikasi pendamping review visual pada satu diagram sampel dengan supervisi manusia.** Tidak layak sebagai netlist elektrik otomatis, rekomendasi penggantian komponen, atau dasar tindakan pada kendaraan.

Untuk menyatakan satu wiring diagram lain didukung, perlu benchmark terpisah terhadap gambar baru: identifikasi komponen, deteksi percabangan, nomor terminal, kelengkapan jalur, *false joins*, dan validasi oleh teknisi. Contoh ini memakai source-locked layout anchors, sehingga **tidak dapat diklaim digeneralisasi**.

Pengguna dapat menyelesaikan empat review visual sehingga laporan menyatakan "assisted_visual_review_ready". Status **diagnostic_ready tetap false** dan **electrically_verified_connections tetap 0**.

## Testing

~~~powershell
py -m pip install "Pillow>=10,<13"
py -m unittest discover -s tests -p "test_*trac*.py" -v
py -m unittest discover -s tests -p "test_terminal_accuracy.py" -v
py -m unittest discover -s tests -p "test_mvp_review.py" -v
node --test tests/test_loading_progress.cjs
~~~

GitHub Actions menjalankan regresi seluruh versi sebelumnya dan tes tambahan untuk snapshot, manual overrides, source lock, konflik OCR historis dan indikator loading. Hasil runtime yang diharapkan untuk evaluasi adalah **autowiring-junction_block-assisted-mvp-v0322.json**.
