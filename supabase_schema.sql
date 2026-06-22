-- ============================================================
-- TUBES AI - SSC Chatbot: Supabase Schema
-- Jalankan script ini di Supabase SQL Editor
-- ============================================================

-- Tabel users untuk autentikasi admin panel
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT DEFAULT 'admin',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabel chat_history untuk menyimpan riwayat percakapan
CREATE TABLE IF NOT EXISTS chat_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT,
  user_message TEXT NOT NULL,
  bot_answer TEXT NOT NULL,
  sources JSONB DEFAULT '[]',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabel documents untuk mencatat PDF yang di-upload
CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filename TEXT UNIQUE NOT NULL,
  uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  is_active BOOLEAN DEFAULT TRUE
);

-- Index untuk performa query
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_documents_active ON documents(is_active);

-- ============================================================
-- CATATAN: Setelah jalankan schema ini, jalankan juga
-- script setup_admin.py untuk membuat user admin pertama
-- ============================================================
