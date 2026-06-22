import os
import uuid
import requests as req_lib
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from groq import Groq

load_dotenv()

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
PDF_FOLDER = os.path.join(BASE_DIR, "data")          # PDF bawaan di repo
TMP_DIR    = "/tmp/pdf_cache"                          # Writable di Vercel
ROOT_DIR   = os.path.dirname(BASE_DIR)

IS_VERCEL = bool(os.getenv("VERCEL"))                 # True saat jalan di Vercel

app = Flask(
    __name__,
    template_folder=os.path.join(ROOT_DIR, "templates"),
    static_folder=os.path.join(ROOT_DIR, "static")
)
app.secret_key = "kunci_rahasia_tubes_ssc"

# ── Groq client ───────────────────────────────────────────────
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

# ── Supabase config ───────────────────────────────────────────
SUPABASE_URL     = os.getenv("SUPABASE_URL")
SUPABASE_KEY     = os.getenv("SUPABASE_KEY")
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)

_SB_HEADERS = {
    "apikey":        SUPABASE_KEY or "",
    "Authorization": f"Bearer {SUPABASE_KEY or ''}",
    "Content-Type":  "application/json",
}


# ============================================================
# SUPABASE HELPERS — Database (PostgREST)
# ============================================================

def sb_select(table, filters=None, order=None, limit=None, count=False):
    if not SUPABASE_ENABLED:
        return [], 0
    try:
        headers = dict(_SB_HEADERS)
        if count:
            headers["Prefer"] = "count=exact"
        params = {}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit:
            params["limit"] = limit
        r = req_lib.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=params, timeout=10)
        if count:
            total = int(r.headers.get("content-range", "0/0").split("/")[-1] or 0)
            return r.json(), total
        return r.json(), 0
    except Exception as e:
        print(f"[DB] sb_select error ({table}): {e}")
        return [], 0


def sb_insert(table, data):
    if not SUPABASE_ENABLED:
        return None
    try:
        headers = {**_SB_HEADERS, "Prefer": "return=representation"}
        r = req_lib.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, json=data, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[DB] sb_insert error ({table}): {e}")
        return None


def sb_upsert(table, data, on_conflict):
    if not SUPABASE_ENABLED:
        return None
    try:
        headers = {**_SB_HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"}
        r = req_lib.post(f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}", headers=headers, json=data, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[DB] sb_upsert error ({table}): {e}")
        return None


def sb_update(table, data, eq_col, eq_val):
    if not SUPABASE_ENABLED:
        return None
    try:
        headers = {**_SB_HEADERS, "Prefer": "return=representation"}
        r = req_lib.patch(f"{SUPABASE_URL}/rest/v1/{table}?{eq_col}=eq.{eq_val}", headers=headers, json=data, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[DB] sb_update error ({table}): {e}")
        return None


# ============================================================
# SUPABASE HELPERS — Storage (bucket: pdfs)
# ============================================================

STORAGE_BUCKET = "pdfs"

def sb_storage_upload(filename, file_bytes):
    """Upload PDF ke Supabase Storage bucket 'pdfs'."""
    if not SUPABASE_ENABLED:
        return False
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{filename}"
        headers = {
            "apikey":        SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type":  "application/pdf",
            "x-upsert":      "true",
        }
        r = req_lib.post(url, headers=headers, data=file_bytes, timeout=60)
        return r.ok
    except Exception as e:
        print(f"[Storage] upload error: {e}")
        return False


def sb_storage_list():
    """List semua PDF di bucket 'pdfs'."""
    if not SUPABASE_ENABLED:
        return []
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/list/{STORAGE_BUCKET}"
        headers = {
            "apikey":        SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type":  "application/json",
        }
        r = req_lib.post(url, headers=headers, json={"prefix": "", "limit": 100, "sortBy": {"column": "name", "order": "asc"}}, timeout=10)
        if r.ok:
            return [f["name"] for f in r.json() if f.get("name", "").lower().endswith(".pdf")]
        return []
    except Exception as e:
        print(f"[Storage] list error: {e}")
        return []


def sb_storage_download(filename, dest_path):
    """Download PDF dari Supabase Storage ke path lokal."""
    if not SUPABASE_ENABLED:
        return False
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{filename}"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        r = req_lib.get(url, headers=headers, timeout=30)
        if r.ok:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(r.content)
            return True
        return False
    except Exception as e:
        print(f"[Storage] download error: {e}")
        return False


def sb_storage_delete(filename):
    """Hapus PDF dari Supabase Storage."""
    if not SUPABASE_ENABLED:
        return False
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}"
        headers = {
            "apikey":        SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type":  "application/json",
        }
        r = req_lib.delete(url, headers=headers, json={"prefixes": [filename]}, timeout=10)
        return r.ok
    except Exception as e:
        print(f"[Storage] delete error: {e}")
        return False


def sb_storage_public_url(filename):
    """Ambil public URL dari file di Supabase Storage."""
    return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{filename}"


# ============================================================
# RAG — Indexing PDF
# ============================================================

documents    = []
vectorizer   = None
tfidf_matrix = None


def chunk_text(text, chunk_size=1000, overlap=200):
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


def _index_pdf_file(pdf_path, filename):
    """Baca satu PDF dan tambahkan chunk ke documents."""
    try:
        reader = PdfReader(pdf_path)
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text:
                for chunk in chunk_text(text):
                    documents.append({
                        "content": chunk,
                        "source":  filename,
                        "page":    page_number
                    })
    except Exception as e:
        print(f"[Index] Gagal baca {filename}: {e}")


def init_index():
    """Index semua PDF dari repo (api/data/) dan Supabase Storage."""
    global documents, vectorizer, tfidf_matrix
    documents.clear()

    # 1. Index PDF yang sudah ada di repo (api/data/)
    if os.path.exists(PDF_FOLDER):
        for fname in os.listdir(PDF_FOLDER):
            if fname.lower().endswith(".pdf"):
                _index_pdf_file(os.path.join(PDF_FOLDER, fname), fname)

    # 2. Index PDF dari Supabase Storage (download ke /tmp dulu)
    if SUPABASE_ENABLED:
        storage_files = sb_storage_list()
        # Hindari duplikasi dengan yang sudah ada di repo
        local_files = set(os.listdir(PDF_FOLDER)) if os.path.exists(PDF_FOLDER) else set()
        os.makedirs(TMP_DIR, exist_ok=True)
        for fname in storage_files:
            if fname in local_files:
                continue   # sudah di-index dari repo
            tmp_path = os.path.join(TMP_DIR, fname)
            # Download jika belum ada di /tmp
            if not os.path.exists(tmp_path):
                sb_storage_download(fname, tmp_path)
            if os.path.exists(tmp_path):
                _index_pdf_file(tmp_path, fname)

    if not documents:
        return False

    texts        = [doc["content"] for doc in documents]
    vectorizer   = TfidfVectorizer(ngram_range=(1, 2), lowercase=True)
    tfidf_matrix = vectorizer.fit_transform(texts)
    return True


# Jalankan indeks di awal (cold start)
try:
    init_index()
except Exception as e:
    print(f"[Init] init_index gagal: {e}")


def search_docs(query, k=5):
    if not documents or vectorizer is None:
        return []
    query_vec   = vectorizer.transform([query.lower()])
    scores      = cosine_similarity(query_vec, tfidf_matrix).flatten()
    top_indices = scores.argsort()[-k:][::-1]
    return [documents[i] for i in top_indices if scores[i] > 0.01]


# ── Helper: wajib login ───────────────────────────────────────
def login_required():
    if not session.get("logged_in"):
        return redirect(url_for("login_page"))
    return None


# ============================================================
# ROUTING HALAMAN PUBLIK
# ============================================================

@app.route("/")
def home():
    return render_template("welcome.html")


# ============================================================
# AUTH: LOGIN / LOGOUT
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if SUPABASE_ENABLED:
            users, _ = sb_select("users", filters={"email": f"eq.{email}"})
            if users:
                user = users[0]
                try:
                    if check_password_hash(user.get("password_hash", ""), password):
                        session["logged_in"]   = True
                        session["user_email"]  = email
                        session["user_role"]   = user.get("role", "admin")
                        return redirect(url_for("admin_page"))
                except Exception:
                    pass
            error = "Email atau password salah!"
        else:
            # Fallback hardcoded jika Supabase tidak tersedia
            if email == "admin@gmail.com" and password == "password":
                session["logged_in"] = True
                return redirect(url_for("admin_page"))
            error = "Email atau password salah!"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ============================================================
# ROUTING ADMIN PANEL
# ============================================================

@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    guard = login_required()
    if guard:
        return guard

    upload_error = None

    if request.method == "POST":
        if "file" not in request.files:
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            return redirect(request.url)

        filename   = secure_filename(file.filename)
        file_bytes = file.read()

        if IS_VERCEL or SUPABASE_ENABLED:
            # ── Upload ke Supabase Storage ─────────────────────
            ok = sb_storage_upload(filename, file_bytes)
            if ok:
                # Simpan ke /tmp agar bisa langsung di-index
                tmp_path = os.path.join(TMP_DIR, filename)
                os.makedirs(TMP_DIR, exist_ok=True)
                with open(tmp_path, "wb") as f:
                    f.write(file_bytes)
                # Catat ke tabel documents
                sb_upsert("documents", {"filename": filename, "is_active": True}, "filename")
                init_index()
                return redirect(url_for("admin_page", uploaded=1))
            else:
                upload_error = "Gagal upload ke Supabase Storage. Pastikan bucket 'pdfs' sudah dibuat dan bersifat Public."
        else:
            # ── Lokal: simpan ke api/data/ ─────────────────────
            os.makedirs(PDF_FOLDER, exist_ok=True)
            save_path = os.path.join(PDF_FOLDER, filename)
            with open(save_path, "wb") as f:
                f.write(file_bytes)
            sb_upsert("documents", {"filename": filename, "is_active": True}, "filename")
            init_index()
            return redirect(url_for("admin_page", uploaded=1))

    # Gabungkan file dari repo + Supabase Storage
    local_files   = set(os.listdir(PDF_FOLDER)) if os.path.exists(PDF_FOLDER) else set()
    storage_files = set(sb_storage_list()) if SUPABASE_ENABLED else set()
    files = sorted(local_files | storage_files)

    return render_template("admin.html", files=files, upload_error=upload_error)


@app.route("/admin/riwayat")
def admin_riwayat():
    guard = login_required()
    if guard:
        return guard

    riwayat, _ = sb_select("chat_history", order="created_at.desc", limit=100)
    return render_template("riwayat.html", riwayat=riwayat, total_chat=len(riwayat))


@app.route("/admin/statistik")
def admin_statistik():
    guard = login_required()
    if guard:
        return guard

    total_docs   = len(set(doc["source"] for doc in documents))
    total_chunks = len(documents)
    _, total_chat = sb_select("chat_history", count=True)

    return render_template("statistik.html",
                           total_docs=total_docs,
                           total_chunks=total_chunks,
                           total_chat=total_chat)


@app.route("/admin/pengaturan")
def admin_pengaturan():
    guard = login_required()
    if guard:
        return guard
    return render_template("pengaturan.html")


@app.route("/admin/keamanan")
def admin_keamanan():
    guard = login_required()
    if guard:
        return guard
    return render_template("keamanan.html")


@app.route("/delete/<filename>")
def delete_file(filename):
    guard = login_required()
    if guard:
        return guard

    safe_name = secure_filename(filename)

    # Hapus dari filesystem lokal (jika ada)
    local_path = os.path.join(PDF_FOLDER, safe_name)
    if os.path.exists(local_path):
        os.remove(local_path)

    # Hapus dari /tmp (jika ada)
    tmp_path = os.path.join(TMP_DIR, safe_name)
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # Hapus dari Supabase Storage
    sb_storage_delete(safe_name)

    # Update tabel documents
    sb_update("documents", {"is_active": False}, "filename", safe_name)

    init_index()
    return redirect(url_for("admin_page", deleted=1))


# ============================================================
# ROUTING API CHATBOT & DATA PDF
# ============================================================

@app.route("/api/documents", methods=["GET"])
def get_documents():
    files = sorted(set(doc["source"] for doc in documents))
    return jsonify({"status": "success", "files": files})


@app.route("/api/data/<path:filename>")
def serve_pdf(filename):
    # Jika ada di repo, serve langsung
    local_path = os.path.join(PDF_FOLDER, secure_filename(filename))
    if os.path.exists(local_path):
        return send_from_directory(PDF_FOLDER, filename)

    # Redirect ke Supabase Storage public URL
    if SUPABASE_ENABLED:
        return redirect(sb_storage_public_url(filename))

    return "File tidak ditemukan", 404


@app.route("/api/chat", methods=["POST"])
def chat_api():
    if client is None:
        return jsonify({"answer": "GROQ_API_KEY belum diatur.", "sources": []})

    data         = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"answer": "Pertanyaan tidak boleh kosong.", "sources": []})

    docs = search_docs(user_message, k=6)
    if not docs:
        return jsonify({"answer": "Saya tidak menemukan jawabannya di dokumen akademik.", "sources": []})

    context     = "\n\n".join(doc["content"] for doc in docs)
    user_prompt = (
        f"Jawab pertanyaan hanya berdasarkan konteks dokumen berikut.\n"
        f"Konteks:\n{context}\n\n"
        f"Pertanyaan:\n{user_message}"
    )

    messages_payload = [
        {
            "role": "system",
            "content": (
                "Kamu adalah asisten akademik SSC (Student Service Center) Telkom University. "
                "Jawab singkat, jelas, dan hanya berdasarkan dokumen yang diberikan. "
                "Selalu sebutkan sumber dokumen dan nomor halaman jika relevan."
            )
        },
        {"role": "user", "content": user_prompt}
    ]

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages_payload,
            temperature=0.2
        )
        answer  = response.choices[0].message.content
        sources = []
        seen    = set()
        for doc in docs:
            key = (doc["source"], doc["page"])
            if key not in seen:
                seen.add(key)
                sources.append({
                    "file": doc["source"],
                    "page": doc["page"],
                    "url":  f"/api/data/{doc['source']}#page={doc['page']}"
                })

        # Simpan riwayat ke Supabase
        session_id = session.get("chat_session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
            session["chat_session_id"] = session_id

        sb_insert("chat_history", {
            "session_id":   session_id,
            "user_message": user_message,
            "bot_answer":   answer,
            "sources":      sources
        })

        return jsonify({"answer": answer, "sources": sources})

    except Exception as e:
        return jsonify({"answer": f"Error Groq: {str(e)}", "sources": []})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
