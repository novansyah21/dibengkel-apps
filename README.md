# AutoWiring v0.3.18 — Enhanced Fuse Rating Recognition & Circuit Tracing

**Tujuan:** lanjutkan hasil v0.3.17 **tanpa mengulang proses sebelumnya**. Version ini tidak menjalankan ulang image-wide OCR, circle detection, segmentation, component discovery, maupun v0.3.17 trace.

## Jalankan di Windows

Pastikan folder **output/autowiring.db** dan **sample_assets** dari v0.3.17 masih ada. Jangan menghapus database!

~~~powershell
cd D:\dibengkelapp\AutoWiring-v0.3.3
git fetch origin
git switch --track origin/feature/v0.3.18
py viewer.py
~~~

Buka http://127.0.0.1:8765 lalu tekan **Ctrl+Shift+R**.

Pilih diagram **Junction Block**, lalu cukup klik **▶ Analyze saved results (v0.3.18)** di kartu biru paling atas. Tidak perlu klik tombol lama.

Hasil dapat dilihat lewat **Show updated path hypotheses**, expanded per-fuse **Original-image OCR crops + raw debug**, dan **Terminal candidates**. Klik **Export v0.3.18 trace & OCR evidence JSON** untuk mengirim hasil pengujian.

## Apa yang baru

- **Targeted rating OCR + crop evidence**: hanya gambar kecil **right_compact, right_above, right_below** pada fuse; garis diagram dapat dibersihkan jika mendominasi baris. Tiap crop punya preview PNG dan log token mentah OCR. Memanfaatkan rating dari v0.3.17 atau review manual jika tersedia; tidak memanggil ulang OCR lama.
- **Endpoint-only geometric tracing with bends**: menambahkan jalur saat endpoint segmen berikutnya menyentuh endpoint terakhir secara unik, termasuk belokan 90°. T-junction, cabang, intersection interior dan rangkaian ambigu tidak otomatis disambung.
- **Ranked terminal leads, including conflicts**: menggunakan circle OCR dan path match sebelumnya, bukan mendeteksi ulang. Kasus **BACK 14 vs 21** dipertahankan sebagai evidence conflict untuk review. OCR confidence bukan keyakinan koneksi listrik.
- **Incremental, deterministic SQLite cache**: bergantung pada run v0.3.17 + fingerprint. Klik ulang tombol dengan data yang sama → hasil cache; **0 tahap lama diulang**; tidak ada tambahan OCR baru yang diulang. Review fuse/rating manual bisa disimpan tanpa analisis ulang.
- **One-click UI**: hasil awal v0.3.17 tersembunyi dalam accordion "Alat v0.3.17" dan tetap bisa dibaca; dashboard v0.3.18 ada di atas.

## Status keamanan dan kejujuran inferensi

Semua link diagram ini adalah **geometric candidate / visual evidence**, bukan bukti listrik:
- **electrically_verified_connections: 0**
- Fuse rating OCR adalah *candidate* sampai dikonfirmasi visual.
- Nomor terminal OCR, kedekatan dan kelurusan garis bukan bukti kepemilikan pin connector.
- Diagram Suzuki SX4 2007 dalam repo masih berstatus vehicle applicability unverified.

## Tests

~~~powershell
py -m pip install "Pillow>=10,<13"
py -m unittest discover -s tests -p "test_trace_*.py" -v
~~~

GitHub Actions juga melakukan compileall, node --check, dan regression tests. Uji runtime Windows dengan gambar asli harus dilakukan oleh pengguna karena gambar itu tidak disertakan pada repository.
