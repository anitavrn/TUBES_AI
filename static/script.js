const input = document.getElementById("question");
const sendBtn = document.getElementById("sendBtn");
const chatBox = document.getElementById("chatBox");

let lastSources = [];

sendBtn.addEventListener("click", sendQuestion);

input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
        sendQuestion();
    }
});

async function sendQuestion() {
    const question = input.value.trim();
    if (!question) return;

    addMessage(question, "user");
    input.value = "";

    if (isAskingSource(question)) {
        if (lastSources.length > 0) {
            addMessage("Berikut sumber relevan dari jawaban sebelumnya:", "bot", lastSources, false, true);
        } else {
            addMessage("Belum ada sumber yang bisa ditampilkan. Tanyakan materi terlebih dahulu.", "bot");
        }
        return;
    }

    const typingId = addMessage("Typing...", "bot", [], true);

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            body: JSON.stringify({ message: question })
        });

        const data = await response.json();

        const typingElement = document.getElementById(typingId);
        if (typingElement) typingElement.remove();

        lastSources = data.sources || [];

        // Jawaban biasa TIDAK menampilkan sumber
        addMessage(data.answer || "Tidak ada jawaban dari server.", "bot");

    } catch (error) {
        const typingElement = document.getElementById(typingId);
        if (typingElement) typingElement.remove();

        addMessage("Gagal menghubungkan ke server.", "bot");
    }
}

function isAskingSource(text) {
    const lower = text.toLowerCase();

    return lower.includes("sumber") ||
           lower.includes("rujukan") ||
           lower.includes("referensi") ||
           lower.includes("dari mana") ||
           lower.includes("halaman berapa") ||
           lower.includes("dokumen mana");
}

function addMessage(text, type, sources = [], isTyping = false, showSources = false) {
    const message = document.createElement("div");
    const id = "msg-" + Date.now() + Math.floor(Math.random() * 1000);

    message.id = id;
    message.className = "message " + type;

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.innerText = type === "user" ? "👤" : "🤖";

    const bubble = document.createElement("div");
    bubble.className = isTyping ? "bubble typing-bubble" : "bubble";
    bubble.innerText = text;

    if (showSources && sources.length > 0) {
        const sourceBox = document.createElement("div");
        sourceBox.className = "source-box";

        const title = document.createElement("p");
        title.className = "source-title";
        title.innerText = "Sumber dokumen:";
        sourceBox.appendChild(title);

        sources.forEach((src) => {
            const link = document.createElement("a");
            link.href = src.url;
            link.target = "_blank";
            link.innerText = `${src.file} - Halaman ${src.page}`;
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