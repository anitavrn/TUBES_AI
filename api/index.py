import os
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from groq import Groq

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_FOLDER = os.path.join(BASE_DIR, "data")
ROOT_DIR = os.path.dirname(BASE_DIR)

app = Flask(
    __name__,
    template_folder=os.path.join(ROOT_DIR, "templates"),
    static_folder=os.path.join(ROOT_DIR, "static")
)

# Kunci rahasia untuk menjalankan fitur "session" (login)
app.secret_key = "kunci_rahasia_tubes_ssc"

api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

documents = []
vectorizer = None
tfidf_matrix = None


def chunk_text(text, chunk_size=1000, overlap=200):
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


def init_index():
    global documents, vectorizer, tfidf_matrix
    documents.clear()

    if not os.path.exists(PDF_FOLDER):
        os.makedirs(PDF_FOLDER, exist_ok=True)
        return False

    pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")]
    if not pdf_files:
        return False

    for filename in pdf_files:
        pdf_path = os.path.join(PDF_FOLDER, filename)
        reader = PdfReader(pdf_path)
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text:
                for chunk in chunk_text(text):
                    documents.append({
                        "content": chunk,
                        "source": filename,
                        "page": page_number
                    })

    if not documents:
        return False

    texts = [doc["content"] for doc in documents]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), lowercase=True)
    tfidf_matrix = vectorizer.fit_transform(texts)
    return True


# Jalankan indeks PDF di awal
init_index()


def search_docs(query, k=5):
    if not documents or vectorizer is None:
        return []
    query_vec = vectorizer.transform([query.lower()])
    scores = cosine_similarity(query_vec, tfidf_matrix).flatten()
    top_indices = scores.argsort()[-k:][::-1]
    return [documents[i] for i in top_indices if scores[i] > 0.01]


# ── Helper: wajib login ──────────────────────────────────────────────────────
def login_required():
    """Return redirect jika belum login, None jika sudah."""
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
        email = request.form.get("email")
        password = request.form.get("password")

        if email == "admin@gmail.com" and password == "password":
            session["logged_in"] = True
            return redirect(url_for("admin_page"))
        else:
            error = "Email atau password salah!"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("home"))


# ============================================================
# ROUTING ADMIN PANEL
# ============================================================

@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    guard = login_required()
    if guard:
        return guard

    if request.method == "POST":
        if "file" not in request.files:
            return redirect(request.url)
        file = request.files["file"]
        if file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join(PDF_FOLDER, filename))
            init_index()  # Re-index otomatis setelah upload
            return redirect(url_for("admin_page", uploaded=1))

    if not os.path.exists(PDF_FOLDER):
        os.makedirs(PDF_FOLDER, exist_ok=True)
    files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")]

    return render_template("admin.html", files=files)


@app.route("/admin/riwayat")
def admin_riwayat():
    guard = login_required()
    if guard:
        return guard

    # Ambil semua sesi dari log (placeholder — bisa disambungkan ke DB)
    return render_template("riwayat.html")


@app.route("/admin/statistik")
def admin_statistik():
    guard = login_required()
    if guard:
        return guard

    # Statistik dokumen aktif bisa dikirim ke template
    total_docs = len(set(doc["source"] for doc in documents))
    total_chunks = len(documents)
    return render_template("statistik.html", total_docs=total_docs, total_chunks=total_chunks)


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


# Proses Hapus PDF
@app.route("/delete/<filename>")
def delete_file(filename):
    guard = login_required()
    if guard:
        return guard

    file_path = os.path.join(PDF_FOLDER, secure_filename(filename))
    if os.path.exists(file_path):
        os.remove(file_path)
        init_index()  # Re-index otomatis setelah hapus
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
    return send_from_directory(PDF_FOLDER, filename)


@app.route("/api/chat", methods=["POST"])
def chat_api():
    if client is None:
        return jsonify({"answer": "GROQ_API_KEY belum diatur.", "sources": []})

    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"answer": "Pertanyaan tidak boleh kosong.", "sources": []})

    docs = search_docs(user_message, k=6)
    if not docs:
        return jsonify({"answer": "Saya tidak menemukan jawabannya di dokumen akademik.", "sources": []})

    context = "\n\n".join(doc["content"] for doc in docs)
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
        answer = response.choices[0].message.content
        sources = []
        seen = set()
        for doc in docs:
            key = (doc["source"], doc["page"])
            if key not in seen:
                seen.add(key)
                sources.append({
                    "file": doc["source"],
                    "page": doc["page"],
                    "url": f"/api/data/{doc['source']}#page={doc['page']}"
                })
        return jsonify({"answer": answer, "sources": sources})
    except Exception as e:
        return jsonify({"answer": f"Error Groq: {str(e)}", "sources": []})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
