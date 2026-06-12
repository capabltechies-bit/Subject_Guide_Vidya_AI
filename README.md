# 📚 Subject Guide & Question Bank Assistant

> **Capabl.in · AI Agent Development Project — Week 1–2 Milestone**
>
> A multi-document academic assistant that explains topics and solves exam questions using Retrieval-Augmented Generation (RAG).

---

## 🚀 Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/<your-team>/subject-guide-assistant.git
cd subject-guide-assistant
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set your API key
Create a `.env` file (never commit this!):
```
GOOGLE_API_KEY=your-google-api-key-here
```

### 5. Run the app
```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## 🏗️ Project Structure

```
subject-guide-assistant/
├── app.py                  # Streamlit UI (Chat + Upload views)
├── document_processor.py   # PDF / DOCX / PPTX / TXT extraction + chunking
├── vector_store.py         # FAISS vector store + Google Gemini embeddings
├── rag_engine.py           # RAG pipeline — topic explainer & exam solver
├── requirements.txt        # Python dependencies
├── .env                    # API keys (never commit!)
└── README.md               # This file
```

---

## 🌟 Features (Week 1–2)

| Feature | Status |
|---|---|
| Multi-format upload (PDF, DOCX, PPTX, TXT) | ✅ |
| Auto content-type detection (textbook / notes / question paper / lab) | ✅ |
| FAISS-powered semantic search | ✅ |
| Google Gemini embeddings (text-embedding-004) | ✅ |
| Topic explanation with structured output | ✅ |
| Exam question solving with mark-aware breakdown | ✅ |
| Source attribution for every answer | ✅ |
| Chat-style conversation history | ✅ |
| Modern dark-themed Streamlit UI | ✅ |
| Streamlit Cloud deployment | ✅ |

---

## ☁️ Deploy to Streamlit Cloud

1. Push this repo to GitHub (make sure `.env` is in `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo → select `app.py`
4. Add your API key in **Secrets** (Settings → Secrets):
   ```toml
   GOOGLE_API_KEY = "your-google-api-key-here"
   ```
5. Click **Deploy** 🎉

---

## 📖 How It Works

```
Upload PDF / DOCX / PPTX / TXT
        │
        ▼
document_processor.py
  • Extracts text by format (pdfplumber, python-docx, python-pptx)
  • Detects content type via keyword heuristics
    (textbook / notes / question_paper / lab_manual)
  • Splits into overlapping 800-char chunks (150-char overlap)
        │
        ▼
vector_store.py
  • Embeds chunks via Google Gemini text-embedding-004
  • Stores vectors in FAISS IndexFlatL2 (in-memory)
        │
        ▼
User Query (Chat UI)
  • Embed query → FAISS similarity search → top-k chunks
  • Build prompt with retrieved context + question
  • Call Gemini 1.5 Flash via rag_engine.py
  • Return structured answer + source attribution
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit 1.35+ |
| Backend | Python 3.11 |
| Vector DB | FAISS (local, in-memory) |
| LLM | Google Gemini 1.5 Flash |
| Embeddings | Google Gemini text-embedding-004 |
| PDF parsing | pdfplumber + PyPDF2 |
| DOCX parsing | python-docx |
| PPTX parsing | python-pptx |
| API SDK | google-generativeai / google-genai |

---

## 📦 Requirements

```
streamlit
google-generativeai
google-genai
faiss-cpu
pdfplumber
PyPDF2
python-docx
python-pptx
python-dotenv
numpy
```

Install all at once:
```bash
pip install -r requirements.txt
```

---

## 👥 Team Checklist (Week 1–2)

- [x] GitHub repo with project structure
- [x] Development environment (Python, Streamlit, FAISS, Gemini)
- [x] Multi-format document processing (PDF, DOCX, PPTX, TXT)
- [x] Content categorization (notes / textbook / question paper / lab)
- [x] Topic-based retrieval system (FAISS + Gemini embeddings)
- [x] RAG pipeline with topic explainer and exam solver modes
- [x] Streamlit chat UI with upload + query views
- [x] Modern dark-themed UI with custom CSS
- [ ] Deploy on Streamlit Cloud ← **do this as a team**
- [ ] Record 2-minute demo video

---

## 📝 .gitignore Template

```
.env
venv/
__pycache__/
*.pyc
*.faiss
*.meta
.streamlit/secrets.toml
```

---

*Built as part of the Capabl.in Subject Guide & QBank AI Agent project.*
