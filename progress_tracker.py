"""
progress_tracker.py  ─  Scholar AI  ─  Week 5 New
Tracks the student's study sessions, topics explored, Q-Bank quiz
scores, and builds a visual progress dashboard.

Data is stored in st.session_state under the key  "progress_data"
which is a dict with the following schema:

{
  "sessions": [
      {
        "timestamp": "2025-03-15T14:22:00",
        "topic":     "Binary Search Trees",
        "mode":      "explain",          # explain | exam | synthesize | exam_map | learning_path | qbank
        "level":     "intermediate",
        "subject":   "Computer Science | None",
      },
      ...
  ],
  "quiz_results": [
      {
        "timestamp": "…",
        "topic":     "Normalization",
        "type":      "MCQ | Short Answer | Long Answer | Full Assessment",
        "score":     7,
        "total":     10,
      },
      ...
  ],
  "streak_days": [],        # ISO date strings
}
"""

from __future__ import annotations
from datetime import datetime, date, timedelta
from collections import Counter
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
#  Initialise / load from session state
# ─────────────────────────────────────────────────────────────────────────────

def _init() -> dict:
    if "progress_data" not in st.session_state:
        st.session_state.progress_data = {
            "sessions":    [],
            "quiz_results": [],
            "streak_days": [],
        }
    return st.session_state.progress_data


# ─────────────────────────────────────────────────────────────────────────────
#  Public recording helpers  (called from app.py)
# ─────────────────────────────────────────────────────────────────────────────

def record_session(topic: str, mode: str, level: str = "intermediate", subject: str = None):
    """Call whenever the student asks a question or generates content."""
    data = _init()
    today = date.today().isoformat()

    data["sessions"].append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "topic":     topic,
        "mode":      mode,
        "level":     level,
        "subject":   subject or "General",
    })

    # Update streak
    if today not in data["streak_days"]:
        data["streak_days"].append(today)

    if "logged_in_user" in st.session_state and st.session_state.logged_in_user:
        import storage_manager as sm
        sm.save_progress(st.session_state.logged_in_user, data)


def record_quiz(topic: str, q_type: str, score: int, total: int):
    """Call after the student self-rates a Q-Bank result."""
    data = _init()
    today = date.today().isoformat()
    data["quiz_results"].append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "topic":     topic,
        "type":      q_type,
        "score":     score,
        "total":     total,
        "pct":       round(score / total * 100) if total else 0,
    })
    if today not in data["streak_days"]:
        data["streak_days"].append(today)

    if "logged_in_user" in st.session_state and st.session_state.logged_in_user:
        import storage_manager as sm
        sm.save_progress(st.session_state.logged_in_user, data)


# ─────────────────────────────────────────────────────────────────────────────
#  Streak calculation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_streak(streak_days: list[str]) -> int:
    if not streak_days:
        return 0
    sorted_days = sorted(set(streak_days), reverse=True)
    dates = [date.fromisoformat(d) for d in sorted_days]
    today = date.today()
    # Must have studied today or yesterday to have an active streak
    if dates[0] < today - timedelta(days=1):
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


# ─────────────────────────────────────────────────────────────────────────────
#  Aggregated stats helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_summary_stats() -> dict:
    data = _init()
    sessions      = data["sessions"]
    quiz_results  = data["quiz_results"]
    streak        = _compute_streak(data["streak_days"])

    topic_counts  = Counter(s["topic"] for s in sessions)
    subject_counts = Counter(s["subject"] for s in sessions)
    mode_counts   = Counter(s["mode"]  for s in sessions)

    avg_score = (
        round(sum(q["pct"] for q in quiz_results) / len(quiz_results))
        if quiz_results else 0
    )

    return {
        "total_sessions":  len(sessions),
        "unique_topics":   len(topic_counts),
        "streak":          streak,
        "total_days":      len(data["streak_days"]),
        "avg_score":       avg_score,
        "quiz_count":      len(quiz_results),
        "top_topics":      topic_counts.most_common(5),
        "subject_counts":  dict(subject_counts),
        "mode_counts":     dict(mode_counts),
        "recent_sessions": sessions[-10:][::-1],  # last 10, newest first
        "quiz_results":    quiz_results[-10:][::-1],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Simple bar-chart helper (pure HTML — no external lib needed)
# ─────────────────────────────────────────────────────────────────────────────

def _html_bar(label: str, value: int, max_val: int, color: str = "var(--accent)") -> str:
    pct = min(100, round(value / max_val * 100)) if max_val else 0
    return f"""
    <div style="margin-bottom:8px;">
      <div style="display:flex;justify-content:space-between;font-size:12px;
                  color:var(--text2)!important;margin-bottom:3px;">
        <span style="max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{label}</span>
        <span style="font-weight:700;color:var(--text)!important;">{value}</span>
      </div>
      <div style="background:var(--surface3);border-radius:99px;height:7px;">
        <div style="background:{color};width:{pct}%;border-radius:99px;height:7px;transition:width .4s;"></div>
      </div>
    </div>"""


def _score_color(pct: int) -> str:
    if pct >= 80:
        return "var(--sage)"
    if pct >= 50:
        return "var(--gold)"
    return "var(--rose)"


# ─────────────────────────────────────────────────────────────────────────────
#  Main render function  (called from app.py inside the progress view)
# ─────────────────────────────────────────────────────────────────────────────

def render_progress_dashboard():
    stats = get_summary_stats()
    data  = _init()

    # ── Top KPI strip ────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5, gap="small")
    kpis = [
        (k1, "📚", stats["total_sessions"],  "Sessions"),
        (k2, "🗂️", stats["unique_topics"],   "Topics"),
        (k3, "🔥", stats["streak"],          "Day Streak"),
        (k4, "📅", stats["total_days"],      "Days Active"),
        (k5, "🏆", f"{stats['avg_score']}%", "Avg Quiz Score"),
    ]
    for col, icon, val, lbl in kpis:
        with col:
            st.markdown(f"""
            <div style="background:var(--surface2);border:1px solid var(--border2);
                        border-radius:12px;padding:16px 14px;text-align:center;">
              <div style="font-size:22px;margin-bottom:4px;">{icon}</div>
              <div style="font-size:26px;font-weight:700;color:var(--text)!important;line-height:1;">{val}</div>
              <div style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
                          color:var(--text3)!important;margin-top:5px;">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Main two-column layout ────────────────────────────────────────────────
    left, right = st.columns([1, 1], gap="large")

    # ── LEFT: Top topics + Subject breakdown + Mode breakdown ─────────────────
    with left:
        # Top Topics
        st.markdown("""
        <div style="background:var(--surface2);border:1px solid var(--border2);
                    border-radius:14px;padding:20px 22px;margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                      color:var(--text3)!important;margin-bottom:14px;">🔖 Most Studied Topics</div>
        """, unsafe_allow_html=True)

        if stats["top_topics"]:
            max_v = stats["top_topics"][0][1]
            bars  = "".join(_html_bar(t, v, max_v, "var(--accent)") for t, v in stats["top_topics"])
            st.markdown(bars + "</div>", unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-size:13px;color:var(--text3)!important;font-style:italic;">No study sessions yet.</p></div>', unsafe_allow_html=True)

        # Subject breakdown
        st.markdown("""
        <div style="background:var(--surface2);border:1px solid var(--border2);
                    border-radius:14px;padding:20px 22px;margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                      color:var(--text3)!important;margin-bottom:14px;">📂 Sessions by Subject</div>
        """, unsafe_allow_html=True)

        if stats["subject_counts"]:
            max_v = max(stats["subject_counts"].values())
            colors = ["var(--sage)", "var(--gold)", "var(--purple)", "var(--cyan)", "var(--rose)"]
            bars = "".join(
                _html_bar(subj, cnt, max_v, colors[i % len(colors)])
                for i, (subj, cnt) in enumerate(sorted(stats["subject_counts"].items(), key=lambda x: -x[1]))
            )
            st.markdown(bars + "</div>", unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-size:13px;color:var(--text3)!important;font-style:italic;">No data yet.</p></div>', unsafe_allow_html=True)

        # Mode breakdown
        MODE_LABELS = {
            "explain":       "📖 Explain",
            "exam":          "📝 Exam Q",
            "synthesize":    "🔀 Synthesize",
            "exam_map":      "🗺️ Exam Map",
            "learning_path": "🛤️ Learning Path",
            "qbank":         "📋 Q-Bank",
        }
        st.markdown("""
        <div style="background:var(--surface2);border:1px solid var(--border2);
                    border-radius:14px;padding:20px 22px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                      color:var(--text3)!important;margin-bottom:14px;">⚙️ Usage by Mode</div>
        """, unsafe_allow_html=True)

        if stats["mode_counts"]:
            max_v = max(stats["mode_counts"].values())
            bars = "".join(
                _html_bar(MODE_LABELS.get(m, m), cnt, max_v, "var(--accent-lt)")
                for m, cnt in sorted(stats["mode_counts"].items(), key=lambda x: -x[1])
            )
            st.markdown(bars + "</div>", unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-size:13px;color:var(--text3)!important;font-style:italic;">No data yet.</p></div>', unsafe_allow_html=True)

    # ── RIGHT: Recent sessions + Quiz results + Self-score widget ────────────
    with right:
        # Recent sessions
        st.markdown("""
        <div style="background:var(--surface2);border:1px solid var(--border2);
                    border-radius:14px;padding:20px 22px;margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                      color:var(--text3)!important;margin-bottom:14px;">🕒 Recent Study Sessions</div>
        """, unsafe_allow_html=True)

        if stats["recent_sessions"]:
            MODE_ICONS = {
                "explain": "📖", "exam": "📝", "synthesize": "🔀",
                "exam_map": "🗺️", "learning_path": "🛤️", "qbank": "📋",
            }
            rows = ""
            for s in stats["recent_sessions"]:
                ts    = s["timestamp"][:16].replace("T", " ")
                icon  = MODE_ICONS.get(s["mode"], "💬")
                topic = s["topic"][:35] + "…" if len(s["topic"]) > 35 else s["topic"]
                level = s.get("level", "")
                level_badge = f'<span style="background:var(--accent-lt);color:var(--accent)!important;border-radius:5px;padding:1px 7px;font-size:10px;font-weight:700;">{level}</span>' if level else ""
                rows += f"""
                <div style="display:flex;align-items:center;gap:10px;padding:7px 0;
                            border-bottom:1px solid var(--border);font-size:12px;">
                  <span style="font-size:16px;width:22px;text-align:center;">{icon}</span>
                  <span style="flex:1;color:var(--text)!important;font-weight:500;">{topic}</span>
                  {level_badge}
                  <span style="color:var(--text3)!important;white-space:nowrap;">{ts}</span>
                </div>"""
            st.markdown(rows + "</div>", unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-size:13px;color:var(--text3)!important;font-style:italic;">No sessions yet — start studying!</p></div>', unsafe_allow_html=True)

        # Quiz results
        st.markdown("""
        <div style="background:var(--surface2);border:1px solid var(--border2);
                    border-radius:14px;padding:20px 22px;margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                      color:var(--text3)!important;margin-bottom:14px;">📊 Quiz Performance</div>
        """, unsafe_allow_html=True)

        if stats["quiz_results"]:
            rows = ""
            for q in stats["quiz_results"]:
                pct   = q["pct"]
                color = _score_color(pct)
                topic = q["topic"][:28] + "…" if len(q["topic"]) > 28 else q["topic"]
                rows += f"""
                <div style="display:flex;align-items:center;gap:10px;padding:7px 0;
                            border-bottom:1px solid var(--border);font-size:12px;">
                  <span style="flex:1;color:var(--text)!important;font-weight:500;">{topic}</span>
                  <span style="font-size:10px;color:var(--text3)!important;">{q['type']}</span>
                  <span style="font-weight:700;color:{color}!important;min-width:45px;text-align:right;">
                    {q['score']}/{q['total']} <span style="font-size:10px;">({pct}%)</span>
                  </span>
                </div>"""
            st.markdown(rows + "</div>", unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-size:13px;color:var(--text3)!important;font-style:italic;">No quiz scores yet.</p></div>', unsafe_allow_html=True)

        # ── Self-score widget ─────────────────────────────────────────────────
        st.markdown("""
        <div style="background:var(--surface2);border:1px solid var(--border2);
                    border-radius:14px;padding:20px 22px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                      color:var(--text3)!important;margin-bottom:4px;">✏️ Log a Quiz Score</div>
          <p style="font-size:12px;color:var(--text3)!important;margin-bottom:12px;line-height:1.5;">
            After attempting a Q-Bank set, record how you did here.
          </p>
        """, unsafe_allow_html=True)

        sc_c1, sc_c2 = st.columns([2, 1], gap="small")
        with sc_c1:
            sc_topic = st.text_input("Topic name", placeholder="e.g. Database Normalization",
                                     label_visibility="collapsed", key="sc_topic")
        with sc_c2:
            sc_type = st.selectbox("Type", ["MCQ", "Short Answer", "Long Answer", "Full Assessment"],
                                   label_visibility="collapsed", key="sc_type")

        sc_c3, sc_c4, sc_c5 = st.columns([1, 1, 1], gap="small")
        with sc_c3:
            sc_score = st.number_input("Score", min_value=0, max_value=100, value=0,
                                       label_visibility="collapsed", key="sc_score")
        with sc_c4:
            sc_total = st.number_input("Out of", min_value=1, max_value=100, value=10,
                                       label_visibility="collapsed", key="sc_total")
        with sc_c5:
            sc_btn = st.button("Log Score →", use_container_width=True, type="primary", key="sc_btn")

        st.markdown("</div>", unsafe_allow_html=True)

        if sc_btn:
            if sc_topic.strip():
                if sc_score > sc_total:
                    st.error("Score cannot exceed total.")
                else:
                    record_quiz(sc_topic.strip(), sc_type, int(sc_score), int(sc_total))
                    pct = round(sc_score / sc_total * 100) if sc_total else 0
                    color = _score_color(pct)
                    st.success(f"Logged! {sc_topic} — {sc_score}/{sc_total} ({pct}%)")
                    st.rerun()
            else:
                st.warning("Please enter the topic name.")

    # ── Streak Calendar ───────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div style="background:var(--surface2);border:1px solid var(--border2);
                border-radius:14px;padding:20px 22px;">
      <div style="font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                  color:var(--text3)!important;margin-bottom:14px;">🗓️ Study Activity — Last 30 Days</div>
    """, unsafe_allow_html=True)

    today      = date.today()
    start      = today - timedelta(days=29)
    active_set = set(data.get("streak_days", []))
    cells      = ""
    for i in range(30):
        d     = start + timedelta(days=i)
        iso   = d.isoformat()
        active = iso in active_set
        bg     = "var(--sage)" if active else "var(--surface3)"
        title  = iso
        day_n  = d.day
        border = "2px solid var(--accent)" if d == today else "2px solid transparent"
        cells += f"""
        <div title="{title}" style="width:30px;height:30px;border-radius:7px;background:{bg};
                                    border:{border};display:flex;align-items:center;justify-content:center;
                                    font-size:10px;color:{'var(--text)' if active else 'var(--text3)'}!important;
                                    font-weight:{'700' if active else '400'};">{day_n}</div>"""

    st.markdown(f"""
    <div style="display:flex;flex-wrap:wrap;gap:6px;">{cells}</div>
    <div style="display:flex;align-items:center;gap:8px;margin-top:12px;font-size:11px;color:var(--text3)!important;">
      <span style="width:12px;height:12px;border-radius:3px;background:var(--sage);display:inline-block;"></span> Studied
      <span style="width:12px;height:12px;border-radius:3px;background:var(--surface3);display:inline-block;margin-left:8px;"></span> No session
    </div>
    </div>""", unsafe_allow_html=True)

    # ── Clear progress ────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("⚙️ Manage Progress Data"):
        st.markdown('<p style="font-size:12px;color:var(--text3)!important;">This clears only your progress tracking data — uploaded documents are NOT affected.</p>', unsafe_allow_html=True)
        if st.button("🗑 Clear Progress History", type="secondary"):
            st.session_state.progress_data = {
                "sessions": [], "quiz_results": [], "streak_days": []
            }
            if "logged_in_user" in st.session_state and st.session_state.logged_in_user:
                import storage_manager as sm
                sm.save_progress(st.session_state.logged_in_user, st.session_state.progress_data)
            st.success("Progress history cleared.")
            st.rerun()