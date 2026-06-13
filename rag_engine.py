"""
rag_engine.py  ─  Week 3-4 Enhanced
RAG engine with:
  • Adaptive explanation levels  (beginner / intermediate / advanced)
  • Content synthesis            (cross-document comparison)
  • Learning path generator      (theory → examples → assessment)
  • Prerequisite identifier
  • Topic-to-exam mapper
"""

import os
import google.generativeai as genai
from dotenv import load_dotenv
from vector_store import search, search_cross_document

load_dotenv()
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))

_MODEL = "gemini-2.5-flash"


# ── Shared helpers ────────────────────────────────────────────────────────────
def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        chap = c.get("chapter", "")
        chap_tag = f" | {chap}" if chap and chap not in ("General", "") else ""
        parts.append(
            f"[Source {i}: {c['source']} ({c['content_type']}){chap_tag}]\n{c['text']}"
        )
    return "\n\n---\n\n".join(parts)


def _call_gemini(system_prompt: str, user_message: str, model_name: str = None, api_key: str = None) -> str:
    import llm_client
    return llm_client.call_llm(
        system_prompt=system_prompt,
        user_message=user_message,
        model_name=model_name or _MODEL,
        gemini_key=api_key,
    )



# ══════════════════════════════════════════════════════════════════════════════
#  1. ADAPTIVE TOPIC EXPLANATION
# ══════════════════════════════════════════════════════════════════════════════

_LEVEL_CFG = {
    "beginner": {
        "audience": "a complete beginner with no prior knowledge of this subject",
        "style":    "Use very simple language, avoid all jargon (explain any you must use), "
                    "use everyday analogies and real-life examples, short sentences.",
        "depth":    "Cover only the fundamental ideas. Nothing advanced.",
    },
    "intermediate": {
        "audience": "a student who knows the basics and wants deeper understanding",
        "style":    "Use standard academic language, balance theory with worked examples.",
        "depth":    "Cover core concepts, nuances, typical exam-tested points.",
    },
    "advanced": {
        "audience": "an advanced student or researcher seeking expert-level insight",
        "style":    "Use technical terminology freely; discuss edge cases, trade-offs, "
                    "alternative approaches, and connections to related research.",
        "depth":    "Cover advanced theory, complexity analysis, design decisions, "
                    "and open problems where relevant.",
    },
}


def _topic_system_prompt(level: str) -> str:
    cfg = _LEVEL_CFG.get(level, _LEVEL_CFG["intermediate"])
    return f"""\
You are an expert academic tutor. Your audience is {cfg['audience']}.

Writing style: {cfg['style']}
Required depth: {cfg['depth']}

Instructions:
- Use the provided CONTEXT as your primary source; supplement with your knowledge if needed.
- Structure with Markdown headings, bullets, bold key terms, and code blocks where relevant.
- Include definitions, key concepts, and worked examples appropriate to the level.
- End with a "🔑 Key Takeaways" section (3–5 concise bullet points).
- Do NOT copy-paste from context — synthesise and explain in your own words.
"""


def answer_topic(
    query: str, k: int = 6,
    level: str = "intermediate",
    subject: str = None,
    model_name: str = None,
    api_key: str = None,
) -> tuple[str, list[dict]]:
    """Explain a topic at the requested level (beginner/intermediate/advanced)."""
    sources = search(query, k=k, subject=subject, api_key=api_key)
    if not sources:
        return (
            "⚠️ No relevant content found in your uploaded documents. "
            "Please upload study materials related to this topic.",
            [],
        )
    context  = _build_context(sources)
    user_msg = (
        f"QUESTION / TOPIC:\n{query}\n\n"
        f"CONTEXT FROM STUDY MATERIALS:\n{context}\n\n"
        f"Explain this topic for a {level}-level student."
    )
    return _call_gemini(_topic_system_prompt(level), user_msg, model_name, api_key), sources


# ══════════════════════════════════════════════════════════════════════════════
#  2. EXAM QUESTION SOLVER
# ══════════════════════════════════════════════════════════════════════════════

_EXAM_PROMPT = """\
You are an expert academic tutor helping students solve university exam questions.

Given an EXAM QUESTION and CONTEXT from study materials:
- Provide a complete, exam-ready answer structured for the marks allocated.
- Aim for ~1 key point per mark if marks are specified.
- Use clear Markdown headings and sub-sections.
- Include: definitions of key terms, explanations with examples, described diagrams,
  and any relevant formulas or algorithms.
- End with a concise "📌 Exam Tip".

Write as if this answer would score full marks in a university exam.
"""


def solve_question(
    query: str, k: int = 6, subject: str = None,
    model_name: str = None, api_key: str = None
) -> tuple[str, list[dict]]:
    """Generate a model exam answer for the given question."""
    sources = search(query, k=k, subject=subject, api_key=api_key)
    if not sources:
        return (
            "⚠️ No relevant content found. Please upload study materials first.",
            [],
        )
    context  = _build_context(sources)
    user_msg = (
        f"EXAM QUESTION:\n{query}\n\n"
        f"CONTEXT FROM STUDY MATERIALS:\n{context}\n\n"
        "Provide a complete, exam-ready answer."
    )
    return _call_gemini(_EXAM_PROMPT, user_msg, model_name, api_key), sources


# ══════════════════════════════════════════════════════════════════════════════
#  3. CONTENT SYNTHESIS  (cross-document)
# ══════════════════════════════════════════════════════════════════════════════

def _synthesis_system_prompt(level: str) -> str:
    cfg = _LEVEL_CFG.get(level, _LEVEL_CFG["intermediate"])
    return f"""\
You are a senior academic researcher synthesising information from MULTIPLE study documents.
Your audience is {cfg['audience']}.

Writing style: {cfg['style']}
Required depth: {cfg['depth']}

Given a TOPIC and excerpts from several sources, your task is to:
1. Identify where sources AGREE, COMPLEMENT, or CONTRADICT each other.
2. Build a comprehensive, unified understanding of the topic.
3. Cite which source covers which aspect inline (e.g. "Source 1 covers X while Source 2 adds Y").

Structure your response as:
### 📌 Overview
### 🔍 Key Concepts (with cross-source comparison)
### 🔗 Synthesis
### ⚠️ Gaps or Contradictions
### 📝 Synthesis Summary (3–5 unified sentences)

Use Markdown throughout. Go beyond simple retrieval — reason and synthesise.
"""


def synthesize_topic(
    query: str, k_per_doc: int = 2,
    level: str = "intermediate", subject: str = None,
    model_name: str = None, api_key: str = None
) -> tuple[str, list[dict]]:
    """Synthesise a topic across all indexed documents."""
    sources = search_cross_document(query, k_per_doc=k_per_doc, subject=subject, api_key=api_key)
    if not sources:
        return (
            "⚠️ No relevant content found across your documents. "
            "Upload multiple related materials for synthesis.",
            [],
        )
    context  = _build_context(sources)
    user_msg = (
        f"TOPIC TO SYNTHESISE:\n{query}\n\n"
        f"CONTEXT FROM MULTIPLE DOCUMENTS:\n{context}"
    )
    return _call_gemini(_synthesis_system_prompt(level), user_msg, model_name, api_key), sources


# ══════════════════════════════════════════════════════════════════════════════
#  4. LEARNING PATH GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

_LEARNING_PATH_PROMPT = """\
You are an expert curriculum designer creating a personalised learning path.

Given a TOPIC and CONTEXT from study materials, produce a structured learning progression.

Use EXACTLY these sections:

### 🧠 Theory Foundation
- Core concepts, definitions, underlying principles
- How it fits into the broader subject

### 📖 Worked Examples
- 2–3 concrete, step-by-step examples (simple → complex)

### 🔗 Connections & Applications
- Real-world applications
- Links to related topics in the materials
- How this knowledge is used in practice

### 📝 Self-Assessment Questions
- 3 questions of increasing difficulty
- Provide answers in `> blockquote` format labelled "Answer:"

### 🎯 Mastery Checklist
- 5–7 "I can…" statements a student should confirm after studying this topic

Be thorough yet student-friendly. Use clean Markdown throughout.
"""


def generate_learning_path(
    topic: str, k: int = 8, subject: str = None,
    model_name: str = None, api_key: str = None
) -> tuple[str, list[dict]]:
    """Generate a full theory → examples → assessment learning path."""
    sources = search(topic, k=k, subject=subject, api_key=api_key)
    if not sources:
        return (
            "⚠️ No relevant content found. Please upload study materials.",
            [],
        )
    context  = _build_context(sources)
    user_msg = f"TOPIC:\n{topic}\n\nCONTEXT FROM STUDY MATERIALS:\n{context}"
    return _call_gemini(_LEARNING_PATH_PROMPT, user_msg, model_name, api_key), sources


# ══════════════════════════════════════════════════════════════════════════════
#  5. PREREQUISITE IDENTIFIER
# ══════════════════════════════════════════════════════════════════════════════

_PREREQ_PROMPT = """\
You are an academic curriculum advisor identifying prerequisite knowledge for a topic.

Given a TOPIC and CONTEXT from study materials, produce:

### 🔑 Direct Prerequisites
Topics/concepts the student MUST know before studying this topic.

### 💡 Helpful Background
Topics that would enrich understanding but are not strictly required.

### 📋 Suggested Learning Sequence
A numbered step-by-step order: prerequisites → this topic.

### ✅ Pre-Check Questions
3 quick questions to verify the student is ready to begin this topic.

Be specific, actionable, and grounded in the provided context.
"""


def identify_prerequisites(
    topic: str, k: int = 6, subject: str = None,
    model_name: str = None, api_key: str = None
) -> tuple[str, list[dict]]:
    """Identify what topics should be mastered before studying this one."""
    sources = search(topic, k=k, subject=subject, api_key=api_key)
    if not sources:
        return ("⚠️ No relevant content found.", [])
    context  = _build_context(sources)
    user_msg = f"TOPIC:\n{topic}\n\nCONTEXT:\n{context}"
    return _call_gemini(_PREREQ_PROMPT, user_msg, model_name, api_key), sources


# ══════════════════════════════════════════════════════════════════════════════
#  6. TOPIC-TO-EXAM MAPPER  (intelligent content mapping)
# ══════════════════════════════════════════════════════════════════════════════

_EXAM_MAP_PROMPT = """\
You are an expert at mapping academic topics to exam question patterns.

Given a TOPIC and CONTEXT (which may include question papers, notes, textbooks):

### 📊 How This Topic Is Examined
Common question formats, typical marks allocation, frequency.

### 🎯 Frequently Tested Sub-topics
Break down the most exam-relevant aspects with brief notes.

### 📝 Sample Questions (easy → hard)
- **2-mark question** (with model answer)
- **5-mark question** (with answer outline)
- **10-mark question** (with marking scheme)

### 📖 Key Definitions to Memorise
Terms the examiner expects precise definitions for.

### ⚠️ Common Mistakes
Pitfalls students make when answering questions on this topic.

Focus on exam strategy and high-yield preparation.
"""


def map_topic_to_exam(
    topic: str, k: int = 8, subject: str = None,
    model_name: str = None, api_key: str = None
) -> tuple[str, list[dict]]:
    """Map a topic to its typical exam question patterns and high-yield content."""
    sources = search(topic, k=k, subject=subject, api_key=api_key)
    if not sources:
        return ("⚠️ No relevant content found.", [])
    context  = _build_context(sources)
    user_msg = f"TOPIC:\n{topic}\n\nCONTEXT:\n{context}"
    return _call_gemini(_EXAM_MAP_PROMPT, user_msg, model_name, api_key), sources