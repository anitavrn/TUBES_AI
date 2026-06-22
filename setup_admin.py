"""
setup_admin.py - Jalankan SEKALI untuk membuat user admin di Supabase.
Pastikan .env sudah berisi SUPABASE_URL dan SUPABASE_KEY sebelum jalankan.

Usage:
    python setup_admin.py
"""

import os
import sys
import bcrypt
from dotenv import load_dotenv
from supabase import create_client

# Set encoding ke utf-8 agar aman di Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERROR] SUPABASE_URL atau SUPABASE_KEY tidak ditemukan di .env")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Konfigurasi admin ─────────────────────────────────────────
ADMIN_EMAIL    = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"   # Ganti sesuai keinginan
# ─────────────────────────────────────────────────────────────

password_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()

try:
    result = supabase.table("users").upsert({
        "email": ADMIN_EMAIL,
        "password_hash": password_hash,
        "role": "admin"
    }, on_conflict="email").execute()

    print("[OK] Admin berhasil dibuat!")
    print(f"   Email    : {ADMIN_EMAIL}")
    print(f"   Password : {ADMIN_PASSWORD}")
    print("\n[PENTING] Simpan password ini dan hapus file setup_admin.py setelah selesai!")

except Exception as e:
    print(f"[GAGAL] Gagal membuat admin: {e}")
