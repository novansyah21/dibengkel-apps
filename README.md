# AutoWiring v0.3.19 — Fuse OCR & Pixel-aware Wiring Evidence

**Satu klik, tidak mengulang proses lama.** AutoWiring v0.3.19 melanjutkan database v0.3.18. Hasil v0.3.16 → v0.3.18 di-reuse, bukan diproses ulang.

## Jalankan

Di PC Windows, **jangan hapus output/autowiring.db maupun sample_assets**. Jika ingin backup, salin file database sebelum checkout.

~~~powershell
cd D:\dibengkelapp\AutoWiring-v0.3.3
git fetch origin
git switch --track origin/feature/v0.3.19
py viewer.py
~~~

Buka http://127.0.0.1:8765 lalu **Ctrl + Shift + R** supaya JavaScript tidak menggunakan versi lama.

1. Pilih **Junction Block**.
2. Klik tombol paling atas **▶ Fix saved results (v0.3.19)**.
3. Lihat ringkasan setiap fuse, OCR, kandidat lingkaran terminal yang sebelumnya unread, dan kandidat dot junction yang diberi tanda.
4. Klik **Export v0.3.19 correction & evidence JSON**.
5. File keluaran: **autowiring-junction_block-corrected-trace-v0319.json**.

**Jangan klik ulang** Automatic Analysis, Geometry Graph, Segmentation, Association, Terminal OCR, Gap Visual, Component Graph, maupun v0.3.17/v0.3.18. Semua hasil lama dibaca dari SQLite, tidak direbuild.

## Perbaikan akurasi berdasarkan hasil pengujian asli v0.3.18

### 1. Rescue rating MTR dari OCR lama

Output v0.3.18 menyimpan teks OCR dari right_compact berupa **10A.** dan dari right_above berupa **10A**. Parser sebelumnya menolak rating itu. v0.3.19 mengizinkan tanda baca terminal dan menerima rating hanya jika **dua ROI berbeda** memberi hasil yang sama. Karena confidence mentah yang gagal tidak disimpan, statusnya adalah **corroborated_cached_raw_ocr_review_required**, bukan angka terverifikasi.

Kandidat rating lainnya ABS 10A, BACK 10A, dan IG COIL 15A berasal dari run v0.3.18 dan dipakai tanpa OCR ulang.

### 2. Rescue terminal ABS dari lingkaran yang sebelumnya unread

Independent circle detection sudah menyimpan lingkaran tak terbaca di sekitar endpoint ABS. v0.3.19 **tidak mengulang deteksi keseluruhan diagram**: hanya crop interior lingkaran yang sudah ada dibaca memakai OCR lokal baru, maksimal dua PSM. Bukti disimpan dalam JSON: crop, teks, confidence, dan status. Pada gambar sumber terminal **9** terlihat; aplikasi tidak memaksakan angka 9 apabila OCR baru gagal.

### 3. Label 21 untuk BACK bukan terminal

Output BACK mengandung kandidat historis **21**. Pemeriksaan gambar menunjukkan lingkaran 21 berada di sekitar simbol fuse di kiri, bukan di kolom konektor. Di sisi kanan ada terminal **14**. Algoritma menggunakan posisi lingkaran dari **semua run OCR tersimpan**, termasuk run historis, untuk menandai 21 sebagai kemungkinan **fuse index circle**, bukan secara diam-diam menghilangkan bukti.

### 4. Pixel-aware dot-junction evidence

v0.3.18 masih single_segment untuk semua jalur. v0.3.19 membaca piksel asli sepanjang segmen horizontal yang tersimpan, mencari **titik hitam padat dengan goresan vertikal panjang**. Ini membantu mengidentifikasi kandidat titik percabangan, **bukan** membuktikan koneksi listrik. Perpotongan garis tipis tanpa titik dan tepi kotak putus-putus difilter berdasarkan kepadatan titik dan panjang goresan.

Garis cabang hasil inspeksi adalah overlay hijau putus-putus, tidak menyambung graph otomatis.

### 5. Header connector sebagai referensi kolom visual

Pada Junction Block sampel berukuran 1136×1598, header BCM, E323 hingga L315 ditranskripsikan sebagai referensi geometri. Hasil seperti **E325? / 9?** hanya merupakan **visual region hint**, tidak membuktikan kepemilikan pin atau pinout. Fitur ini hanya berlaku untuk diagram junction_block dan rasio gambar yang sesuai.

## Incremental processing, ketepatan, dan keselamatan

- Satu klik v0.3.19 membaca database dan mengerjakan **fokus OCR baru hanya untuk kandidat terminal yang belum terbaca**, jika ada, serta menginspeksi piksel sumber.
- SHA256 gambar, versi algoritma, dan run lama dimasukkan ke fingerprint. Klik ulang dengan input tidak berubah menghasilkan **cache_hit=true**, tanpa menjalankan OCR ulang.
- Jika gambar asli tidak sama dengan sumber analisis sebelumnya, proses dihentikan agar geometri lama tidak dianggap masih berlaku.
- Semua segmen, konektor, fuse, terminal, dan dot junction adalah **kandidat visual/geometris**.
- **electrically_verified_connections = 0**, sampai ada validasi teknis dan pinout yang sesuai.

## Tes otomatis

~~~powershell
py -m pip install "Pillow>=10,<13"
py -m unittest discover -s tests -p "test_trace_*.py" -v
~~~

GitHub Actions menjalankan Python/JS syntax check, tes SQLite migration, cached OCR rescue, focused terminal, dot-vs-crossing, konflik, dan cache. Evaluasi hasil di PC Windows dengan gambar asli tetap diperlukan.
