# AutoWiring v0.4.1 — Multi-Vehicle & PDF Source Library

**Status produk:** viewer dan manual wiring-map untuk diagram mobil apa pun, OCR/CV universal sebagai **kandidat visual**, katalog kendaraan, dan diagnosis awal kelistrikan 12V **berdasarkan gejala dan bukti pengukuran**. Aplikasi belum dapat membuktikan netlist listrik seluruh kendaraan atau menetapkan penyebab kerusakan otomatis dari gambar saja.

## v0.4.1 — PDF Source Library (rights-aware)

The 📚 Wiring PDF Source Library UI lists previously discussed references and locally archived PDFs:

- Operation CHARM: https://charm.li/ (HTML/images; not assumed to provide PDFs)
- BMW ETM Archive: https://shark.armchair.mb.ca/~dave/BMW/ (some historical PDF links)
- BMW WDS: https://wds.psjr.org/en/ (interactive diagram site)
- BMWTeka: https://bmwteka.com/en (service manual catalog)
- CarManualsOnline: https://www.carmanualsonline.info/ (online manual site)

These sources are **not automatically scraped or downloaded**. Their license status is unknown. No paywall, login, anti-bot or robots.txt bypass. If robots.txt cannot be checked or denies access, discovery/download fails closed. The app will not redistribute copyrighted manuals.

List sources and local PDFs:

~~~powershell
py pdf_sources.py sources
py pdf_sources.py list
~~~

Discover direct PDF links on one public HTML page (dry run, no download):

~~~powershell
py pdf_sources.py discover --url "https://example.org/public-index/"
~~~

Add a locally owned/authorized PDF:

~~~powershell
py pdf_sources.py add-local --file "C:\manuals\wiring.pdf" --title "Wiring diagram" --vehicle "Suzuki Swift 2007" --rights "licensed personal reference"
~~~

Download **one** direct HTTPS PDF only when authorized and robots.txt permits:

~~~powershell
py pdf_sources.py import-url --url "https://example.org/permitted-manual.pdf" --title "Wiring diagram" --vehicle "Suzuki Swift 2007" --rights "express permission from rights holder" --confirm-rights
~~~

Example.org URLs above are placeholders, not verified authorized sources.

Files are SHA256-deduplicated into output/pdf_library/ with metadata in SQLite. The UI lists only registered files and serves them from that folder. This feature does not yet convert PDF pages into diagram images or verified circuit graphs.

## Instalasi / upgrade Windows

Jangan hapus output/autowiring.db atau sample_assets. Gunakan folder dan database sebelumnya.

~~~powershell
cd D:\dibengkelapp\AutoWiring-v0.3.3
git fetch origin
git switch --track origin/feature/v0.4.0-multivehicle-diagnostics
py viewer.py
~~~

Buka http://127.0.0.1:8765, lalu Ctrl + Shift + R untuk refresh JS/CSS. Loading spinner sebelumnya tetap aktif selama permintaan API dan pemuatan gambar.

## A. Pilih kendaraan: Merk → Jenis → Nama → Varian → Tahun

Bagian 🚗 **Identitas Kendaraan** menyediakan:
1. **Merk**: Toyota, Daihatsu, Suzuki, Honda, Mitsubishi, Wuling, Hyundai, BMW dan lebih banyak.
2. **Jenis/Tipe bodi** berdasarkan merk: hatchback, MPV, SUV, sedan, city car, pickup dan lainnya.
3. **Nama mobil/model**, misalnya Suzuki Swift, Suzuki SX4, Wuling Air ev atau Toyota Avanza.
4. **Tipe/Varian**, teks yang lu masukkan secara manual (misalnya GL AT atau G CVT), tahun, dan jenis penggerak.
5. Klik **Simpan kendaraan & hubungkan ke diagram**; pilih profil tersimpan untuk menghubungkan diagram lain ke kendaraan tersebut.
6. Model/merk belum ada? Klik **＋ Merk / nama model belum tersedia?** untuk memasukkan ke katalog lokal.

Ada **21 merk awal** dengan banyak nama model contoh. Ini **bukan** database resmi kecocokan tahun, mesin, ECU, varian dan pinout. Lu tetap wajib menggunakan diagram servis yang cocok dengan kendaraan sebenarnya. Katalog user-custom tetap bisa diperluas, bukan daftar tertutup.

## B. Universal Diagram Reader (OCR/CV beta)

1. Klik **＋ Import wiring diagram (PNG/JPEG)** dan pilih gambar kendaraan.
2. Pilih diagram aktif.
3. Klik **▶ Analisis gambar aktif — OCR & kandidat kabel**.
4. Jika dependensi tersedia, sistem membaca label, rating fuse dan segmen garis memakai OCR/OpenCV; tampilkan hasil sebagai kandidat dengan OCR confidence.
5. Gunakan anotasi, jalur manual, dan konektor pada viewer untuk pemeriksaan lebih lanjut.

Kandidat OCR dan potongan garis **tidak** membuktikan kontinuitas. Scanner **tidak** menyambungkan crossing, tidak otomatis mengenali tipe ECU, dan tidak mengonversi gambar apa pun menjadi netlist elektrik tepercaya. Hasil scan disimpan berdasarkan checksum gambar agar tombol yang sama tidak mengulang OCR/CV.

Paket Python opsional untuk OCR/CV:

~~~powershell
py -m pip install pillow pytesseract opencv-python numpy
~~~

Tesseract juga membutuhkan executable Tesseract OCR pada sistem operasi. Tanpa Tesseract/OpenCV, import gambar, viewer, katalog dan rule-assisted 12V triage tetap tersedia; aplikasi akan menandai OCR/CV unavailable.

## C. Diagnosis Awal Gangguan Listrik 12V (Beta)

Buka bagian **🧰 Pemeriksaan Gangguan Listrik**:
1. Pilih gejala (misalnya lampu mati, starter tidak berputar, fuse putus berulang, gangguan intermiten atau aki melemah).
2. Pilih sistem: starting, lighting, body, charging 12V, general 12V, ABS, SRS atau high-voltage.
3. Bila sudah diukur dengan benar, masukkan nilai yang tersedia saja: tegangan aki 12V dalam kondisi mesin mati, input/output fuse, suplai beban, ground drop dan status continuity fuse.
4. Klik **Analisis kemungkinan penyebab & pemeriksaan berikutnya**.

Contoh: jika input fuse dilaporkan 12,4 V dan output 0,1 V, aplikasi mengeluarkan **hipotesis** fuse terbuka/kontak holder buruk, bukan vonis komponen yang pasti rusak. Tanpa pengukuran, hasilnya **insufficient_evidence**, bukan kepastian. Hasil identik disimpan satu kali dalam SQLite, dengan riwayat per diagram.

**Safety:** pemeriksaan high-voltage EV/hybrid dan airbag/SRS dibatasi ke teknisi tersertifikasi. Jangan menjumper sekering, menaikkan rating sekering, atau melakukan continuity probing pada sirkuit airbag/SRS dan HV.

Diagnosis di sini masih **rule-based triage**, bukan AI yang otomatis mengetahui semua kerusakan pada seluruh merek dan tahun kendaraan. Angka OCR/garis dari gambar tidak dipakai untuk mengklaim koneksi atau ECU tertentu sebagai sumber masalah.

## D. Legacy MVP tidak hilang

MVP 0.1 untuk Junction Block Suzuki SX4: enam fuse, lima branch candidates, empat terminal perlu review, snapshot/ekspor dan manual mapping tetap ada. Pipeline enam-fuse spesifik source **tidak diterapkan** pada diagram lain. Tahapan sebelumnya hanya dibaca, tidak dihitung ulang.

## Acceptance & keterbatasan

| Target | Kondisi |
|---|---|
| Pemilihan merk / jenis / model / varian / tahun | Tersedia, contoh katalog dapat ditambah |
| Import diagram apa pun | Tersedia untuk review manual |
| OCR label dan line candidates generik | Beta, jika deps lokal terpasang |
| Circuit graph listrik untuk seluruh jenis kendaraan | **Belum dapat diverifikasi** |
| Diagnosis awal berbasis data gejala dan pengukuran | Beta, output conditional hypotheses |
| Diagnosis otomatis tanpa bukti pengukuran atau manual | **Tidak didukung** |
| Electrical continuity verified | **0** |
| Diagnosis siap digunakan tanpa validasi teknisi | **Tidak** |

Hasil triage menyimpan automatic_diagnosis_verified=false dan electrical_continuity_verified=false.

## Pengujian

~~~powershell
py -m unittest discover -s tests -p "test_vehicle_diagnosis.py" -v
py -m unittest discover -s tests -p "test_universal_scan.py" -v
py -m unittest discover -s tests -p "test_vehicle_api_http.py" -v
~~~

GitHub Actions menjalankan regresi versi lama, compile Python, syntax JS, katalog/konektivitas antar-dropdown, API HTTP, generic OCR scan hash cache, penolakan input tak valid, serta guardrails SRS/high-voltage.

**Untuk mencapai diagnosis listrik otomatis yang layak digunakan bengkel**, dibutuhkan dataset diagram lintas mobil dengan referensi service-manual, anotasi simbol/pinout dan pengukuran teknisi yang telah diverifikasi. Benchmark harus mengukur false connections, kesalahan OCR terminal, serta akurasi rekomendasi fault. Jangan mengklaim hasil sempurna pada seluruh jenis kendaraan tanpa validasi tersebut.
