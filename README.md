# ♠ Capsa Royale

Aplikasi web pencatat skor Capsa untuk main bareng teman. Tema casino premium: hitam, gold, hijau felt.

## Cara Menjalankan (VS Code)

1. **Buka folder ini di VS Code.**

2. **Buat virtual environment** (opsional tapi disarankan):
   ```bash
   python -m venv venv
   ```
   Aktifkan:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Jalankan aplikasi:**
   ```bash
   python app.py
   ```

5. **Buka browser** ke `http://127.0.0.1:5000`

Database SQLite (`capsa_royale.db`) akan otomatis dibuat di folder yang sama saat pertama kali `app.py` dijalankan.

## Struktur Folder

```
capsa-royale/
├── app.py                 # Flask backend + routes + logic poin
├── requirements.txt
├── capsa_royale.db         # dibuat otomatis saat run pertama
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── new_game.html
│   ├── game.html
│   └── history.html
└── static/
    ├── css/style.css
    └── js/game.js
```

## Fitur

- Target poin bebas & preset cepat (10/25/50/100)
- Pemain fleksibel 2–8 orang
- Sistem poin: ⭐+3, 🥈+2, 🥉+1, 😐0, ❌-1, 💣-2
- Leaderboard otomatis terurut
- Riwayat tiap ronde
- Popup pemenang otomatis saat target tercapai
- Reset game & hapus riwayat

## Catatan

Kalau mau ganti port, ubah baris terakhir di `app.py`:
```python
app.run(debug=True, port=5000)
```
