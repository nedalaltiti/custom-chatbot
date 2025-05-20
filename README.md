# HR Teams Chatbot 🚀

A production-ready conversational assistant that lives inside Microsoft Teams and answers HR-related questions using **Google Gemini** plus your internal document knowledge-base (RAG).

---

## ✨ Key Features

| | |
|---|---|
| **Conversational HR assistant** | Warm, empathetic replies; automatically links to “Open an HR support request ➜ …” when needed |
| **Microsoft Teams native** | Shows typing indicators, progressive (“streaming”) answers and Adaptive Cards |
| **Retrieval-Augmented Generation** | Searches your own HR PDFs / docs, then lets Gemini craft an answer citing the sources |
| **Feedback-aware** | Collects 1–5 ★ ratings + free-text feedback to keep improving the bot |
| **Self-contained** | Pure FastAPI + NumPy, easier to deploy and debug |

---

## 🧠 How RAG Works

```text
User question
      │
      ▼
─── 1. Similarity search ───────────────────────────────
│   • Google Vertex AI embeddings (768-dim)             │
│   • In-house NumPy/ndarray store (disk-backed)        │
└───────── top-k relevant chunks ───────────────────────┘
      │
      ▼
─── 2. Prompt builder ──────────────────────────────────
│   SYSTEM + FLOW_RULES + KNOWLEDGE + HISTORY + USER    │
└───────── final prompt ────────────────────────────────┘
      │
      ▼
─── 3. Google Gemini                                    │
      │
      ▼
─── 4. Answer with citations ▶ Teams (streamed)         │
