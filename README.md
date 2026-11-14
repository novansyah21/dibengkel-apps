# AutoWiring v0.3.20 — Multi-Branch Circuit Tracing

**Fokus versi ini:** lanjut dari database v0.3.19 dan telusuri hipotesis jalur bercabang pada gambar Junction Block Suzuki SX4 yang sudah ada, tanpa mengulang OCR/segmentasi/analisis versi lama.

## Cara menjalankan (Windows)

**Gunakan folder dan database yang sama**. Jangan menghapus output/autowiring.db maupun sample_assets.

~~~powershell
cd D:\dibengkelapp\AutoWiring-v0.3.3
git fetch origin
git switch --track origin/feature/v0.3.20
py viewer.py
~~~

Buka http://127.0.0.1:8765, lalu tekan **Ctrl + Shift + R** untuk memperbarui JavaScript dan CSS.

1. Pilih **Junction Block**.
2. Klik tombol biru paling atas **▶ Continue saved analysis — 6 fuse & branches (v0.3.20)**.
3. Periksa panel utama: enam kandidat fuse, main path (cyan), branch path (ungu), OCR terminal dan penanda continuation.
4. Kalau perlu, gunakan **Save visual review** untuk menandai kecocokan **visual**. Review ini tidak memverifikasi koneksi listrik.
5. Klik **Export v0.3.20 branches & evidence JSON**. Kirim **autowiring-junction_block-multi-branch-v0320.json** untuk evaluasi.

Tidak perlu klik ulang tahapan v0.3.16–v0.3.19 maupun tombol Automatic Analysis, segmentation, independent OCR atau Component Graph.

## Kemampuan tambahan

### 6 kandidat fuse dari gambar yang sama

Empat fuse (IG COIL, MTR, ABS, BACK) berasal dari run v0.3.19. Dua fuse **A/B dan IG1 SIG** ditambahkan melalui *source-locked visual anchor proposal* berdasarkan posisi label pada **gambar Junction Block yang sama persis**. Bukan klaim pendeteksi fuse generik atau inferensi tentang diagram kendaraan lain. Label/garis di posisi anchor dicocokkan ke piksel asli, rating kedua fuse dibaca menggunakan **targeted OCR baru hanya untuk dua row itu**. Semua tetap kandidat unverified.

Proses enam-fuse ini **dikunci ke SHA256 diagram sumber dan dimensi 1136×1598**. Jika gambar berbeda, aplikasi memberi pesan yang jelas dan tidak menerapkan koordinat dari diagram lain secara diam-diam.

### Branch-aware path proposals

- Mulai dari titik percabangan visual yang telah disimpan di v0.3.19; titik pada fuse baru ditinjau dari piksel asli secara lokal.
- Melacak goresan vertikal ke atas/bawah, lalu berbelok ke horizontal jika garis berakhir dan mempunyai dukungan piksel yang konsisten.
- **Tidak otomatis menyambung** garis yang hanya berpotongan; crossing tanpa dot tidak diartikan sebagai junction.
- Nomor terminal menggunakan **lingkaran OCR tersimpan** dari v0.3.9 / v0.3.19. Hanya lingkaran yang sebelumnya unread pada cabang baru/terminal baru yang boleh di-OCR lagi secara **lokal**, disertai crop untuk review.
- Jalur MTR yang menuju **kotak continuation 1** dibedakan dari terminal konektor nomor 1.
- Header kolom konektor (E325, G271, G272, L313, L315) dipakai hanya sebagai **hint lokasi visual**; bukan bukti pinout.

### Idempotent cache

Fingerprint SQLite menggunakan ID run v0.3.19, ID OCR lingkaran, SHA256 gambar dan versi algoritma. Klik kedua kali dengan input sama menjadi **cache_hit=true** dan tidak melakukan OCR tambahan. Review visual manual hanya menulis tabel review sendiri.

### Batas ketepatan

**Semua hasil adalah VISUAL/GEOMETRIC HYPOTHESES.** Bahkan jika garis pada gambar, fuse symbol, junction dot dan lingkaran terminal terlihat menyambung, aplikasi **tidak** mengklaim ada hubungan listrik yang diverifikasi: **electrically_verified_connections = 0**.

Gambar ini hanya satu contoh referensi, bukan general purpose wiring-netlist parser, dan vehicle applicability masih unverified. Jalur/fuse baru tidak boleh otomatis dikonversi ke hasil pemeriksaan teknisi tanpa validasi sumber dan konektivitas.

## Otomatisasi pengujian

~~~powershell
py -m pip install "Pillow>=10,<13"
py -m unittest discover -s tests -p "test_*trac*.py" -v
~~~

GitHub Actions menjalankan Python syntax, JavaScript syntax, migrasi SQLite, uji fungsional diagram sintetis dengan crossing tanpa dot, belokan, terminal OCR, continuation dan cache. Uji akhir pada gambar sumber asli dilakukan di PC dengan database user, kemudian dievaluasi lewat JSON ekspor.
