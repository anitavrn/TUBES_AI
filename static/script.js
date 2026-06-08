const input           = document.getElementById("question");
const sendBtn         = document.getElementById("sendBtn");
const chatBox         = document.getElementById("chatBox");
const historyList     = document.getElementById("historyList");
const newChatBtn      = document.getElementById("newChatBtn");
const clearHistoryBtn = document.getElementById("clearHistoryBtn");

let lastSources = [];
let sessionId   = null;


function getSavedSessions() {
    const raw = localStorage.getItem("ssc_sessions");
    return raw ? JSON.parse(raw) : [];
}

function getSessionMessages(id) {
    const raw = localStorage.getItem(`ssc_msg_${id}`);
    return raw ? JSON.parse(raw) : [];
}

function saveSessionMessages(id, messages) {
    localStorage.setItem(`ssc_msg_${id}`, JSON.stringify(messages));
}

function saveSession(id, firstMessage) {
    const sessions = getSavedSessions();
    if (!sessions.find(s => s.id === id)) {
        sessions.unshift({ id, title: firstMessage });
        localStorage.setItem("ssc_sessions", JSON.stringify(sessions));
    }
}

function deleteAllSessions() {
    const sessions = getSavedSessions();
    sessions.forEach(s => localStorage.removeItem(`ssc_msg_${s.id}`));
    localStorage.removeItem("ssc_sessions");
    localStorage.removeItem("ssc_session_id");
}

function generateId() {
    return "sess-" + Date.now() + "-" + Math.floor(Math.random() * 10000);
}

function initSession() {
    const saved = localStorage.getItem("ssc_session_id");
    if (saved) {
        sessionId = saved;
        loadSessionMessages(saved);
    } else {
        createNewSession();
    }
    renderSessionList();
}

function createNewSession() {
    sessionId = generateId();
    localStorage.setItem("ssc_session_id", sessionId);

    chatBox.innerHTML = "";
    addMessage("Halo! Kamu bisa bertanya tentang EPrT, yudisium, SKS, sidang TA, dan syarat kelulusan.", "bot");
    renderSessionList();
}

function loadSessionMessages(id) {
    const messages = getSessionMessages(id);
    chatBox.innerHTML = "";

    if (messages.length === 0) {
        addMessage("Halo! Kamu bisa bertanya tentang EPrT, yudisium, SKS, sidang TA, dan syarat kelulusan.", "bot");
    } else {
        messages.forEach(msg => {
            addMessage(msg.content, msg.role === "user" ? "user" : "bot");
        });
    }
}

function switchSession(id) {
    sessionId = id;
    localStorage.setItem("ssc_session_id", id);
    loadSessionMessages(id);
    renderSessionList();
}

function renderSessionList() {
    if (!historyList) return;
    historyList.innerHTML = "";

    const sessions = getSavedSessions();

    if (sessions.length === 0) {
        const empty = document.createElement("li");
        empty.className   = "history-empty";
        empty.textContent = "Belum ada riwayat.";
        historyList.appendChild(empty);
        return;
    }

    sessions.forEach(session => {
        const li = document.createElement("li");
        li.className  = "history-item" + (session.id === sessionId ? " active" : "");
        li.textContent = session.title.length > 38
            ? session.title.slice(0, 38) + "…"
            : session.title;
        li.title = session.title;
        li.addEventListener("click", () => switchSession(session.id));
        historyList.appendChild(li);
    });
}



sendBtn.addEventListener("click", sendQuestion);
input.addEventListener("keydown", e => { if (e.key === "Enter") sendQuestion(); });

if (newChatBtn) {
    newChatBtn.addEventListener("click", () => createNewSession());
}

if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener("click", () => {
        if (!confirm("Hapus semua riwayat percakapan?")) return;
        deleteAllSessions();
        createNewSession();
    });
}


async function sendQuestion() {
    const question = input.value.trim();
    if (!question) return;

    addMessage(question, "user");
    input.value = "";

    const messages = getSessionMessages(sessionId);
    messages.push({ role: "user", content: question });
    saveSessionMessages(sessionId, messages);

    saveSession(sessionId, question);
    renderSessionList();

    if (isAskingSource(question)) {
        if (lastSources.length > 0) {
            addMessage("Berikut sumber relevan dari jawaban sebelumnya:", "bot", lastSources, false, true);
        } else {
            addMessage("Belum ada sumber yang bisa ditampilkan. Tanyakan materi terlebih dahulu.", "bot");
        }
        return;
    }

    const typingId = addMessage("Mengetik...", "bot", [], true);

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            body: JSON.stringify({ message: question, session_id: sessionId })
        });

        const data = await response.json();

        const typingEl = document.getElementById(typingId);
        if (typingEl) typingEl.remove();

        lastSources = data.sources || [];
        addMessage(data.answer || "Tidak ada jawaban dari server.", "bot");

        const updated = getSessionMessages(sessionId);
        updated.push({ role: "bot", content: data.answer || "Tidak ada jawaban dari server." });
        saveSessionMessages(sessionId, updated);

    } catch (error) {
        const typingEl = document.getElementById(typingId);
        if (typingEl) typingEl.remove();
        addMessage("Gagal menghubungkan ke server.", "bot");
    }
}

function isAskingSource(text) {
    const lower = text.toLowerCase();
    return ["sumber", "rujukan", "referensi", "dari mana", "halaman berapa", "dokumen mana"]
        .some(k => lower.includes(k));
}


function addMessage(text, type, sources = [], isTyping = false, showSources = false) {
    const message     = document.createElement("div");
    const id          = "msg-" + Date.now() + Math.floor(Math.random() * 1000);
    message.id        = id;
    message.className = "message " + type;

    const avatar      = document.createElement("div");
    avatar.className  = "avatar";
    avatar.innerText  = type === "user" ? "👤" : "🤖";

    const bubble      = document.createElement("div");
    bubble.className  = isTyping ? "bubble typing-bubble" : "bubble";
    bubble.innerText  = text;

    if (showSources && sources.length > 0) {
        const sourceBox     = document.createElement("div");
        sourceBox.className = "source-box";

        const title       = document.createElement("p");
        title.className   = "source-title";
        title.innerText   = "Sumber dokumen:";
        sourceBox.appendChild(title);

        sources.forEach(src => {
            const link     = document.createElement("a");
            link.href      = src.url;
            link.target    = "_blank";
            link.innerText = `${src.file} — Halaman ${src.page}`;
            sourceBox.appendChild(link);
        });

        bubble.appendChild(sourceBox);
    }

    if (type === "user") {
        message.appendChild(bubble);
        message.appendChild(avatar);
    } else {
        message.appendChild(avatar);
        message.appendChild(bubble);
    }

    chatBox.appendChild(message);
    chatBox.scrollTop = chatBox.scrollHeight;
    return id;
}

initSession();