"""
setup_admin.py - Jalankan SEKALI untuk membuat user admin di Supabase.
Pastikan .env sudah berisi SUPABASE_URL dan SUPABASE_KEY sebelum jalankan.

Usage:
    python setup_admin.py
"""

import os
import sys
import requests
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# Set encoding ke utf-8 agar aman di Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERROR] SUPABASE_URL atau SUPABASE_KEY tidak ditemukan di .env")
    exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=representation"
}

# ── Konfigurasi admin ─────────────────────────────────────────
ADMIN_EMAIL    = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"   # Ganti sesuai keinginan
# ─────────────────────────────────────────────────────────────

# Generate hash dengan werkzeug (pbkdf2:sha256) - kompatibel tanpa bcrypt
password_hash = generate_password_hash(ADMIN_PASSWORD)

try:
    url = f"{SUPABASE_URL}/rest/v1/users?on_conflict=email"
    r = requests.post(url, headers=HEADERS, json={
        "email": ADMIN_EMAIL,
        "password_hash": password_hash,
        "role": "admin"
    }, timeout=10)

    if r.status_code in (200, 201):
        print("[OK] Admin berhasil dibuat/diupdate!")
        print(f"   Email    : {ADMIN_EMAIL}")
        print(f"   Password : {ADMIN_PASSWORD}")
        print("\n[PENTING] Simpan password ini dan hapus file setup_admin.py setelah selesai!")
    else:
        print(f"[GAGAL] Status {r.status_code}: {r.text}")

except Exception as e:
    print(f"[GAGAL] Error: {e}")
