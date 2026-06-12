"""
question_bank.py  ─  Week 3-4 New
AI-powered question bank generator.
Generates MCQ, Short Answer, Long Answer, and Full Assessments
from indexed study materials using Gemini.
"""

import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv
from vector_store import search

load_dotenv()
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))

_MODEL = "gemini-2.5-flash"


# ── Shared helpers ────────────────────────────────────────────────────────────
def _call_gemini(system_prompt: str, user_msg: str, model_name: str = None, api_key: str = None) -> str:
    import llm_client
    return llm_client.call_llm(
        system_prompt=system_prompt,
        user_message=user_msg,
        model_name=model_name or _MODEL,
        gemini_key=api_key,
    )



def _safe_json(text: str) -> dict | list | None:
    """Strip markdown fences and parse JSON safely."""
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    # Try to find JSON array/object if there's extra text
    for pattern in [r"(\[.*\])", r"(\{.*\})"]:
        m = re.search(pattern, clean, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None


def _build_context(chunks: list[dict]) -> str:
    return "\n\n---\n\n".join(
        f"[{c['source']}]\n{c['text']}" for c in chunks
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MCQ GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

_MCQ_SYSTEM = """\
You are an expert exam paper setter generating multiple-choice questions.
You MUST respond with ONLY a valid JSON array — no prose, no markdown fences, nothing else.

Required JSON schema:
[
  {
    "question": "Full question text here?",
    "options": {
      "A": "Option text",
      "B": "Option text",
      "C": "Option text",
      "D": "Option text"
    },
    "answer": "A",
    "explanation": "Brief explanation of why the answer is correct."
  }
]

All 4 options must be plausible. Only one must be correct.
"""


def generate_mcq(
    topic: str,
    count: int = 5,
    difficulty: str = "mixed",
    subject: str = None,
    model_name: str = None,
    api_key: str = None,
) -> tuple[list[dict], list[dict]]:
    """
    Generate MCQ questions on a topic.
    difficulty: "easy" | "medium" | "hard" | "mixed"
    Returns: (questions_list, source_chunks)
    """
    sources = search(topic, k=8, subject=subject, api_key=api_key)
    if not sources:
        return [], []

    context   = _build_context(sources)
    diff_note = (
        "Mix easy (1), medium (2), and hard (2) questions."
        if difficulty == "mixed"
        else f"All questions should be {difficulty} difficulty."
    )

    user_msg = f"""Topic: {topic}
Difficulty: {diff_note}
Number of questions: {count}

Context from study materials:
{context}

Generate exactly {count} MCQ questions. Output ONLY the JSON array."""

    raw       = _call_gemini(_MCQ_SYSTEM, user_msg, model_name, api_key)
    questions = _safe_json(raw)
    if not isinstance(questions, list):
        questions = []
    return questions[:count], sources


# ══════════════════════════════════════════════════════════════════════════════
#  SHORT ANSWER GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

_SHORT_SYSTEM = """\
You are an expert exam paper setter generating short-answer questions.
Respond with ONLY a valid JSON array — no prose, no markdown fences, nothing else.

Required JSON schema:
[
  {
    "question": "Question text here?",
    "marks": 3,
    "model_answer": "Complete model answer in 2-4 sentences.",
    "key_points": ["Key point 1", "Key point 2", "Key point 3"]
  }
]

Vary marks between 2 and 5 per question.
key_points should match the marks allocation (one point per mark).
"""


def generate_short_answer(
    topic: str, count: int = 4, subject: str = None,
    model_name: str = None, api_key: str = None
) -> tuple[list[dict], list[dict]]:
    """
    Generate short-answer questions on a topic.
    Returns: (questions_list, source_chunks)
    """
    sources = search(topic, k=8, subject=subject, api_key=api_key)
    if not sources:
        return [], []

    context  = _build_context(sources)
    user_msg = f"""Topic: {topic}
Number of questions: {count}
Marks per question: vary between 2 and 5

Context:
{context}

Generate exactly {count} short-answer questions. Output ONLY the JSON array."""

    raw       = _call_gemini(_SHORT_SYSTEM, user_msg, model_name, api_key)
    questions = _safe_json(raw)
    if not isinstance(questions, list):
        questions = []
    return questions[:count], sources


# ══════════════════════════════════════════════════════════════════════════════
#  LONG ANSWER GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

_LONG_SYSTEM = """\
You are an expert exam paper setter generating long-answer / essay questions.
Respond with ONLY a valid JSON array — no prose, no markdown fences, nothing else.

Required JSON schema:
[
  {
    "question": "Main question text here?",
    "marks": 10,
    "parts": [
      "(a) Sub-question part a (3 marks)",
      "(b) Sub-question part b (4 marks)",
      "(c) Sub-question part c (3 marks)"
    ],
    "model_answer": "Comprehensive model answer covering all parts.",
    "marking_scheme": [
      "Part (a): Key point 1 (1 mark), Key point 2 (1 mark), Key point 3 (1 mark)",
      "Part (b): ...",
      "Part (c): ..."
    ]
  }
]

Questions should be 8–15 marks each with 2–4 sub-parts.
"""


def generate_long_answer(
    topic: str, count: int = 2, subject: str = None,
    model_name: str = None, api_key: str = None
) -> tuple[list[dict], list[dict]]:
    """
    Generate long-answer/essay questions on a topic.
    Returns: (questions_list, source_chunks)
    """
    sources = search(topic, k=10, subject=subject, api_key=api_key)
    if not sources:
        return [], []

    context  = _build_context(sources)
    user_msg = f"""Topic: {topic}
Number of questions: {count}
Marks: 10–15 marks each, with multi-part structure

Context:
{context}

Generate exactly {count} long-answer questions with sub-parts. Output ONLY the JSON array."""

    raw       = _call_gemini(_LONG_SYSTEM, user_msg, model_name, api_key)
    questions = _safe_json(raw)
    if not isinstance(questions, list):
        questions = []
    return questions[:count], sources


# ══════════════════════════════════════════════════════════════════════════════
#  FULL ASSESSMENT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_full_assessment(
    topic: str, subject: str = None,
    model_name: str = None, api_key: str = None
) -> tuple[dict, list[dict]]:
    """
    Generate a complete assessment with MCQs + Short + Long answers.
    Returns: (assessment_dict, all_unique_sources)
    """
    mcqs,  src1 = generate_mcq(topic,          count=5, subject=subject, model_name=model_name, api_key=api_key)
    short, src2 = generate_short_answer(topic,  count=3, subject=subject, model_name=model_name, api_key=api_key)
    long,  src3 = generate_long_answer(topic,   count=1, subject=subject, model_name=model_name, api_key=api_key)

    # Deduplicate sources by filename
    all_src = list({c["source"]: c for c in (src1 + src2 + src3)}.values())

    mcq_marks   = len(mcqs)                              # 1 mark each
    short_marks = sum(q.get("marks", 3) for q in short)
    long_marks  = sum(q.get("marks", 10) for q in long)

    return {
        "topic":        topic,
        "mcq":          mcqs,
        "short_answer": short,
        "long_answer":  long,
        "total_marks":  mcq_marks + short_marks + long_marks,
        "breakdown": {
            "MCQ (1 mark each)":         f"{len(mcqs)} × 1 = {mcq_marks}",
            "Short Answer":              f"{short_marks} marks",
            "Long Answer":               f"{long_marks} marks",
        },
    }, all_src