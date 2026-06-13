"""
app.py  ─  Scholar AI  ─  Week 5 Enhanced
New views : Learning Path | Q-Bank | Knowledge Graph | Progress Tracker
New modes : Synthesize | Exam Map
New feature: Adaptive explanation levels (Beginner / Intermediate / Advanced)
New sidebar: Subject & chapter filters
Week 5 NEW: Progress Tracker — session history, quiz scores, streak calendar
"""

import streamlit as st
import streamlit.components.v1 as components
import tempfile, os, sys
from pathlib import Path
from dotenv import load_dotenv

# Force UTF-8 encoding for standard output to prevent cp1252 UnicodeEncodeErrors on Windows console
sys.stdout.reconfigure(encoding='utf-8')

# Initialize environment variables
load_dotenv()

# Streamlit Cloud deployment: Inject st.secrets into os.environ so all modules can find the keys
try:
    if hasattr(st, "secrets"):
        for k in st.secrets:
            os.environ[k] = str(st.secrets[k])
except Exception as e:
    print("Secrets injection error:", e)

import storage_manager as sm
from vector_store      import get_stats, add_documents
from document_processor import process_document
from rag_engine        import (
    answer_topic, solve_question,
    synthesize_topic, generate_learning_path,
    identify_prerequisites, map_topic_to_exam,
)
from question_bank     import generate_mcq, generate_short_answer, generate_long_answer, generate_full_assessment
from knowledge_graph   import build_knowledge_graph, get_topic_subgraph, render_graph_html
from progress_tracker  import render_progress_dashboard, record_session

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Scholar AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE & AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════
DEFAULTS = {
    "logged_in":      False,
    "logged_in_user": None,
    "use_supabase":   sm.IS_SUPABASE_CONFIGURED,  # Auto-detect: use Supabase if configured
    "auth_view":      "login",       # login | register | verify
    "reg_email":      "",
    "reg_password":   "",
    "api_settings":   None,
    "history":        [],
    "indexed":        False,
    "mode":           "explain",     # explain | exam | synthesize | exam_map
    "level":          "intermediate",# beginner | intermediate | advanced
    "view":           "chat",        # chat | upload | learning_path | qbank | knowledge_graph | progress
    "subject_filter": None,
    "chapter_filter": None,
    "kg_data":        None,          # cached knowledge graph
    "lp_result":      None,          # cached learning path result
    "qb_result":      None,          # cached Q-bank result
    "progress_data": {               # Week 5: progress tracking
        "sessions":    [],
        "quiz_results": [],
        "streak_days": [],
    },
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Initialize last_view for scroll reset when changing dashboard sections
if "last_view" not in st.session_state:
    st.session_state.last_view = st.session_state.view

if st.session_state.last_view != st.session_state.view:
    st.session_state.last_view = st.session_state.view
    try:
        st.html(
            """
            <script>
                window.parent.document.querySelectorAll('.main, [data-testid="stAppViewContainer"]').forEach(el => {
                    el.scrollTop = 0;
                });
            </script>
            """
        )
    except Exception:
        pass

def get_api_key_and_model(mode: str) -> tuple[str, str]:
    if st.session_state.api_settings and "modes" in st.session_state.api_settings:
        mode_cfg = st.session_state.api_settings["modes"].get(mode, {})
        model = mode_cfg.get("model", "gemini-1.5-flash")
        key = mode_cfg.get("api_key", "")
        if not key:
            key = st.session_state.api_settings.get("default_api_key", "")
        if not key:
            key = os.environ.get("GOOGLE_API_KEY", "")
            if not key and hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets:
                key = str(st.secrets["GOOGLE_API_KEY"])
        if "gemini-2.5" in model:
            model = model.replace("gemini-2.5", "gemini-1.5")
        return key, model
    
    default_models = {
        "explain": "gemini-1.5-flash",
        "exam": "gemini-1.5-pro",
        "synthesize": "gemini-1.5-pro",
        "exam_map": "gemini-1.5-flash",
        "learning_path": "gemini-1.5-flash",
        "qbank": "gemini-1.5-flash",
        "knowledge_graph": "gemini-1.5-flash"
    }
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key and hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets:
        key = str(st.secrets["GOOGLE_API_KEY"])
    return key, default_models.get(mode, "gemini-1.5-flash")

def load_user_session_data(user_id: str):
    import vector_store as vs
    
    st.session_state.api_settings = sm.load_api_settings(user_id)
    st.session_state.history = sm.load_chat_history(user_id)
    st.session_state.progress_data = sm.load_progress(user_id)
    
    # Force load into progress_data in session
    st.session_state["progress_data"] = st.session_state.progress_data
    
    chunks, metadata, faiss_filepath = sm.load_vector_store(user_id)
    if chunks and metadata and faiss_filepath:
        vs.load_user_vector_store(chunks, metadata, faiss_filepath)
        st.session_state.indexed = True
    else:
        vs.clear_vector_store()
        st.session_state.indexed = False

def logout_user():
    import vector_store as vs
    vs.clear_vector_store()
    
    st.session_state.logged_in = False
    st.session_state.logged_in_user = None
    st.session_state.history = []
    st.session_state.indexed = False
    st.session_state.kg_data = None
    st.session_state.lp_result = None
    st.session_state.qb_result = None
    st.session_state.progress_data = {
        "sessions":    [],
        "quiz_results": [],
        "streak_days": [],
    }
    st.session_state.api_settings = None
    st.session_state.view = "chat"

# Block access if not logged in
if not st.session_state.logged_in:
    st.markdown("""
    <style>
    html, body, .stApp { background: radial-gradient(ellipse at top left, #0f1a12, #0a0d0b 70%) !important; font-family: 'Sora', sans-serif; color: #e8f0e8; }
    .stTextInput > div > div > input {
        background: #141e17 !important; border: 1.5px solid #243d2b !important;
        border-radius: 12px !important; padding: 14px 16px !important; color: #e8f0e8 !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg,#34d399,#10b981) !important; color: #fff !important;
        border: none !important; border-radius: 9px !important; font-weight: 600 !important;
    }
    .stButton > button[kind="secondary"] {
        background: #141e17 !important; color: #8fb89e !important;
        border: 1px solid #243d2b !important; border-radius: 9px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(14, 22, 16, 0.8) !important;
        backdrop-filter: blur(14px) !important;
        border: 1.5px solid rgba(52, 211, 153, 0.15) !important;
        border-radius: 20px !important;
        box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5) !important;
        padding: 35px 30px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    col_l1, col_l2, col_l3 = st.columns([1, 1.3, 1])
    with col_l2:
        st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            if st.session_state.auth_view == "login":
                st.markdown('<h2 style="font-family:\'Lora\', serif; text-align:center; margin-bottom: 24px; color: #e8f0e8;">🎓 Scholar AI Login</h2>', unsafe_allow_html=True)

                login_email = st.text_input("Email", placeholder="you@example.com")
                login_password = st.text_input("Password", type="password", placeholder="••••••••")
                
                st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
                if st.button("Log In →", use_container_width=True, type="primary"):
                    if not login_email or not login_password:
                        st.error("Please fill in all fields.")
                    else:
                        success, uid, err = sm.sign_in(login_email, login_password)
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.logged_in_user = uid
                            load_user_session_data(uid)
                            st.rerun()
                        else:
                            st.error(f"Login failed: {err}")
                            
                st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 20px 0 !important;'>", unsafe_allow_html=True)
                st.markdown('<p style="font-size:12px; text-align:center; color: #8fb89e;">Manage Account</p>', unsafe_allow_html=True)
                c_fp1, c_fp2 = st.columns([1, 1], gap="small")
                with c_fp1:
                    if st.button("Create Account", use_container_width=True, type="secondary"):
                        st.session_state.auth_view = "register"
                        st.rerun()
                with c_fp2:
                    if st.button("Forgot Password?", use_container_width=True, type="secondary"):
                        st.session_state.auth_view = "forgot_password"
                        st.rerun()
                    
            elif st.session_state.auth_view == "register":
                st.markdown('<h2 style="font-family:\'Lora\', serif; text-align:center; margin-bottom: 24px; color: #e8f0e8;">🌱 Create Account</h2>', unsafe_allow_html=True)

                reg_email = st.text_input("Email", placeholder="you@example.com")
                reg_password = st.text_input("Password", type="password", placeholder="••••••••")
                
                st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
                if st.button("Send Verification Code →", use_container_width=True, type="primary"):
                    success, msg = sm.start_sign_up(reg_email, reg_password)
                    if success:
                        st.session_state.reg_email = reg_email
                        st.session_state.reg_password = reg_password
                        st.session_state.auth_view = "verify"
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                        
                st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 20px 0 !important;'>", unsafe_allow_html=True)
                if st.button("Back to Login", use_container_width=True, type="secondary"):
                    st.session_state.auth_view = "login"
                    st.rerun()
                    
            elif st.session_state.auth_view == "verify":
                st.markdown('<h2 style="font-family:\'Lora\', serif; text-align:center; margin-bottom: 24px; color: #e8f0e8;">🔑 Enter Verification Code</h2>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:13px; text-align:center; color: #8fb89e;">Enter the 6-digit code sent to <strong>{st.session_state.reg_email}</strong></p>', unsafe_allow_html=True)
                
                if "local_otp_fallback" in st.session_state and st.session_state.local_otp_fallback:
                    st.info(f"ℹ️ Code for testing: **{st.session_state.local_otp_fallback}**")
                    
                verification_code = st.text_input("6-digit Code", placeholder="123456")
                
                st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
                if st.button("Verify & Create Account", use_container_width=True, type="primary"):
                    success, uid, err = sm.verify_signup_otp(st.session_state.reg_email, verification_code)
                    if success:
                        st.success("Account created successfully!")
                        login_success, login_uid, login_err = sm.sign_in(st.session_state.reg_email, st.session_state.reg_password)
                        if login_success:
                            st.session_state.logged_in = True
                            st.session_state.logged_in_user = login_uid
                            st.session_state.local_otp_fallback = None
                            load_user_session_data(login_uid)
                            st.rerun()
                        else:
                            st.session_state.auth_view = "login"
                            st.rerun()
                    else:
                        st.error(f"Verification failed: {err}")
                        
                st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 20px 0 !important;'>", unsafe_allow_html=True)
                if st.button("Cancel & Register Again", use_container_width=True, type="secondary"):
                    st.session_state.auth_view = "register"
                    st.session_state.local_otp_fallback = None
                    st.rerun()
        
            elif st.session_state.auth_view == "forgot_password":
                st.markdown('<h2 style="font-family:\'Lora\', serif; text-align:center; margin-bottom: 24px; color: #e8f0e8;">🔑 Reset Password</h2>', unsafe_allow_html=True)

                st.markdown('<p style="font-size:13px; text-align:center; color: #8fb89e;">Enter your email to receive a password reset verification code.</p>', unsafe_allow_html=True)
                reset_email = st.text_input("Email", placeholder="you@example.com")
                
                st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
                if st.button("Send Reset Code →", use_container_width=True, type="primary"):
                    success, msg = sm.start_password_reset(reset_email)
                    if success:
                        st.session_state.reg_email = reset_email
                        st.session_state.auth_view = "verify_reset"
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                        
                st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 20px 0 !important;'>", unsafe_allow_html=True)
                if st.button("Back to Login", use_container_width=True, type="secondary"):
                    st.session_state.auth_view = "login"
                    st.rerun()
        
            elif st.session_state.auth_view == "verify_reset":
                st.markdown('<h2 style="font-family:\'Lora\', serif; text-align:center; margin-bottom: 24px; color: #e8f0e8;">🔒 Enter Reset Details</h2>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:13px; text-align:center; color: #8fb89e;">Enter the reset code sent to <strong>{st.session_state.reg_email}</strong> and choose a new password.</p>', unsafe_allow_html=True)
                
                if "local_otp_fallback" in st.session_state and st.session_state.local_otp_fallback:
                    st.info(f"ℹ️ SMTP not configured. OTP code for testing: **{st.session_state.local_otp_fallback}**")
                    
                reset_code = st.text_input("Reset Code", placeholder="123456")
                new_password = st.text_input("New Password", type="password", placeholder="••••••••")
                
                st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
                if st.button("Update Password & Log In →", use_container_width=True, type="primary"):
                    success, msg = sm.complete_password_reset(st.session_state.reg_email, reset_code, new_password)
                    if success:
                        st.success(msg)
                        login_success, login_uid, login_err = sm.sign_in(st.session_state.reg_email, new_password)
                        if login_success:
                            st.session_state.logged_in = True
                            st.session_state.logged_in_user = login_uid
                            st.session_state.local_otp_fallback = None
                            load_user_session_data(login_uid)
                            st.rerun()
                        else:
                            st.session_state.auth_view = "login"
                            st.rerun()
                    else:
                        st.error(msg)
                        
                st.markdown("<hr style='border-color: #2a3045; margin: 20px 0 !important;'>", unsafe_allow_html=True)
                if st.button("Cancel", use_container_width=True, type="secondary"):
                    st.session_state.auth_view = "login"
                    st.session_state.local_otp_fallback = None
                    st.rerun()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&family=Lora:ital,wght@0,400;0,600;1,400&family=Outfit:wght@300;400;500;600;700&display=swap');

:root {
  --bg:         #060b08;
  --surface:    #0c1410;
  --surface2:   #121e17;
  --surface3:   #1a2e22;
  --border:     #1e3a28;
  --border2:    #285038;
  --text:       #eef5f0;
  --text2:      #9ebfaa;
  --text3:      #5e8a6e;
  --text-inv:   #060b08;
  --accent:     #34d399;
  --accent2:    #10b981;
  --accent-lt:  rgba(52,211,153,.12);
  --accent-glow:rgba(52,211,153,.2);
  --gold:       #f5be4f;
  --gold-lt:    rgba(245,190,79,.1);
  --sage:       #50d890;
  --sage-lt:    rgba(80,216,144,.1);
  --rose:       #f37676;
  --rose-lt:    rgba(243,118,118,.1);
  --purple:     #af95fc;
  --purple-lt:  rgba(175,149,252,.1);
  --cyan:       #3ec8fc;
  --cyan-lt:    rgba(62,200,252,.1);
  --r:    12px;
  --r-lg: 20px;
  --sh:   0 4px 12px rgba(0,0,0,.5);
  --sh-lg:0 12px 40px rgba(0,0,0,.7);
}
*, *::before, *::after { box-sizing: border-box; }
html, body, .stApp { 
  background: radial-gradient(ellipse at top left, #0f1a12, #060b08 70%) !important; 
  font-family: 'Sora', 'Outfit', sans-serif; 
  color: var(--text); 
}
#MainMenu, footer { visibility:hidden; height:0; }
header, [data-testid="stHeader"] { background: transparent !important; }
[data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] { display: flex !important; visibility: visible !important; opacity: 1 !important; position: fixed !important; top: 15px !important; left: 15px !important; z-index: 999999 !important; color: var(--accent) !important; background: var(--surface2) !important; border: 1px solid var(--accent) !important; border-radius: 8px !important; padding: 5px !important; }
.block-container { padding: 20px 40px 100px !important; max-width:100% !important; }

/* ── Premium Custom Scrollbar ── */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: rgba(0,0,0,0.2) !important;
}
::-webkit-scrollbar-thumb {
  background: var(--border) !important;
  border-radius: 6px !important;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--accent) !important;
}

/* ── Profile Card Styling ── */
.profile-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 14px;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
  margin: 12px 14px 4px;
  box-shadow: var(--sh);
}
.profile-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  box-shadow: 0 4px 10px var(--accent-glow);
  flex-shrink: 0;
}
.profile-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.profile-email {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
}
.profile-status {
  font-size: 10px;
  color: var(--sage);
  font-weight: 500;
  margin-top: 1px;
}

/* ── Sidebar Navigation Customizing (Google Drive Flow Layout) ── */
section[data-testid="stSidebar"] div.stButton > button {
  width: 100% !important;
  text-align: left !important;
  justify-content: flex-start !important;
  display: flex !important;
  align-items: center !important;
  padding: 10px 20px !important;
  border-radius: 99px !important; /* Fully rounded pill inset like Drive */
  font-family: 'Outfit', 'Sora', sans-serif !important;
  font-size: 13.5px !important;
  font-weight: 500 !important;
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  color: var(--text2) !important;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
  margin-bottom: 4px !important;
}

/* Force inner text and icons to be left-aligned */
section[data-testid="stSidebar"] div.stButton > button > div,
section[data-testid="stSidebar"] div.stButton > button > span,
section[data-testid="stSidebar"] div.stButton > button p,
section[data-testid="stSidebar"] div.stButton > button [data-testid="stMarkdownContainer"] {
  display: flex !important;
  justify-content: flex-start !important;
  align-items: center !important;
  text-align: left !important;
  width: 100% !important;
  margin: 0 !important;
}

/* Active navigation item (Drive-style pill with left accent bar) */
section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
  background: var(--accent-lt) !important;
  color: var(--accent) !important;
  font-weight: 600 !important;
  position: relative !important;
}
section[data-testid="stSidebar"] div.stButton > button[kind="primary"]::before {
  content: '' !important;
  position: absolute !important;
  left: 6px !important;
  top: 20% !important;
  height: 60% !important;
  width: 3px !important;
  background: var(--accent) !important;
  border-radius: 99px !important;
  box-shadow: 0 0 8px var(--accent-glow) !important;
}

/* Hover state (Subtle background highlight) */
section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover,
section[data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover {
  background: rgba(255, 255, 255, 0.05) !important;
  color: var(--text) !important;
}

section[data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover {
  background: rgba(52, 211, 153, 0.18) !important;
  color: var(--accent) !important;
}

/* Logout button - sleek, subtle */
section[data-testid="stSidebar"] div.stButton:has(button[key="logout_btn"]) > button {
  color: var(--text3) !important;
  font-size: 12.5px !important;
  padding: 8px 20px !important;
  margin-bottom: 16px !important;
  transition: all 0.2s ease !important;
}
section[data-testid="stSidebar"] div.stButton:has(button[key="logout_btn"]) > button:hover {
  color: var(--rose) !important;
  background: var(--rose-lt) !important;
}

/* ── Sidebar General Structure ── */
section[data-testid="stSidebar"] {
  min-width: 280px !important;
  max-width: 320px !important;
  width: 300px !important;
}
section[data-testid="stSidebar"] > div:first-child { 
  background: var(--surface) !important; 
  border-right: 1px solid var(--border) !important; 
  padding: 0 !important; 
  width: 100% !important;
}


section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] div { 
  color: var(--text2) !important; 
}
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { 
  color: var(--text) !important; 
}

/* ── Collapsible Expanders for Filters & Files ── */
[data-testid="stSidebar"] [data-testid="stExpander"] {
  background: rgba(255,255,255,0.01) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  margin: 4px 14px 8px !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  padding: 8px 12px !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  color: var(--text3) !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Glassmorphism for bordered containers ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(12, 20, 16, 0.7) !important;
  backdrop-filter: blur(16px) !important;
  border: 1px solid rgba(52, 211, 153, 0.12) !important;
  border-radius: 16px !important;
  box-shadow: var(--sh-lg) !important;
  padding: 30px 25px !important;
  transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
  border-color: rgba(52, 211, 153, 0.25) !important;
  box-shadow: 0 16px 48px rgba(52, 211, 153, 0.08) !important;
}

/* ── Force all Streamlit text visible ── */
.stApp p, .stApp span, .stApp label, .stApp div, .stApp li, .stApp small,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li, [class*="stText"] { color: var(--text) !important; }
.stApp .stCaption, [data-testid="stCaptionContainer"] p, .stApp small { color: var(--text2) !important; }

/* ── File uploader ── */
[data-testid="stFileUploader"] section, [data-testid="stFileUploader"] section *,
[data-testid="stFileUploader"] button, [data-testid="stFileUploader"] button span,
[data-testid="stFileUploaderFileName"], [data-testid="stFileUploaderFileData"] * { color: var(--text2) !important; }
[data-testid="stFileUploader"] button { background: var(--surface3) !important; border: 1px solid var(--border2) !important; border-radius: 8px !important; }
[data-testid="stFileUploader"] > div,
[data-testid="stFileUploader"] [data-testid="stFileUploadDropzone"],
[data-testid="stFileUploader"] section {
  background: var(--surface2) !important;
  border: 2px dashed var(--border2) !important;
  border-radius: 14px !important;
  padding: 36px 28px !important;
  transition: border-color .2s, background .2s !important;
}
[data-testid="stFileUploader"] > div:hover,
[data-testid="stFileUploader"] [data-testid="stFileUploadDropzone"]:hover,
[data-testid="stFileUploader"] section:hover {
  border-color: var(--accent) !important;
  background: var(--accent-lt) !important;
}

/* ── Text input / textarea ── */
.stTextInput > div > div > input, .stTextArea > div > div > textarea {
  background: var(--surface2) !important; border: 1.5px solid var(--border2) !important;
  border-radius: 12px !important; padding: 14px 16px !important; font-size: 14px !important;
  font-family: 'Sora', sans-serif !important; color: var(--text) !important;
  caret-color: var(--accent) !important; resize: none !important; transition: border-color .2s, box-shadow .2s !important;
}
.stTextInput > div > div > input::placeholder, .stTextArea > div > div > textarea::placeholder { color: var(--text3) !important; }
.stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 3px var(--accent-glow) !important; outline: none !important; }
.stTextInput > div > div, .stTextInput > div, .stTextArea > div > div, .stTextArea > div,
[data-baseweb="input"], [data-baseweb="textarea"] { background: transparent !important; border: none !important; box-shadow: none !important; }
.stTextInput label, .stTextArea label { color: var(--text2) !important; font-size: 13px !important; }

/* ── Selectbox ── */
[data-baseweb="select"] > div { background: var(--surface2) !important; border: 1.5px solid var(--border2) !important; border-radius: 10px !important; }
[data-baseweb="select"] span, [data-baseweb="select"] div,
[data-baseweb="popover"] li, [data-baseweb="popover"] span { color: var(--text) !important; background: var(--surface2) !important; }
[data-baseweb="popover"] [aria-selected="true"] { background: var(--accent-lt) !important; }

/* ── Radio ── */
[data-testid="stRadio"] label, [data-testid="stRadio"] span { color: var(--text2) !important; }
[data-testid="stRadio"] label:has(input:checked) span { color: var(--text) !important; }

/* ── Progress ── */
.stProgress > div { background: var(--surface3) !important; border-radius:99px !important; height:5px !important; }
.stProgress > div > div { background: var(--accent) !important; border-radius:99px !important; }

/* ── Alerts ── */
.stAlert { border-radius: 10px !important; font-family:'Sora',sans-serif !important; font-size:13px !important; }

/* ── Expander ── */
[data-testid="stExpander"] summary p { color: var(--text2) !important; }
[data-testid="stExpander"] { background: var(--surface2) !important; border: 1px solid var(--border) !important; border-radius: 10px !important; }

/* ── Spinner ── */
.stSpinner > div { border-top-color: var(--accent) !important; }
hr { border-color: var(--border) !important; margin: 20px 0 !important; }

/* ── Metric ── */
[data-testid="stMetricLabel"] p { color: var(--text3) !important; font-size:11px !important; text-transform:uppercase; letter-spacing:.07em; }
[data-testid="stMetricValue"]   { color: var(--text) !important; font-size:28px !important; font-weight:700 !important; }

.status-pill { display:inline-flex; align-items:center; gap:6px; padding:5px 12px; border-radius:99px; font-size:11px; font-weight:600; margin:14px 20px 0; }
.status-on  { background:var(--sage-lt);  color:var(--sage)  !important; border:1px solid rgba(78,203,141,.3); }
.status-off { background:var(--gold-lt);  color:var(--gold)  !important; border:1px solid rgba(240,184,74,.3); }
.status-dot { width:6px; height:6px; border-radius:50%; background:currentColor; }

.sb-sec { font-size:10px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:var(--text3) !important; padding:18px 20px 8px; display:block; }
.sb-nav-label { font-size:10px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:var(--text3) !important; padding:16px 14px 8px; display:block; }
.sb-divider { height:1px; background:var(--border); margin:8px 14px 12px; }
.sb-files { padding:0 12px; }
.sb-file-row { display:flex; align-items:center; gap:9px; padding:8px 8px; border-radius:8px; font-size:12px; color:var(--text2) !important; transition:background .12s; margin-bottom:2px; }
.sb-file-row:hover { background:var(--surface2); }
.sb-file-icon { width:28px; height:28px; border-radius:7px; display:flex; align-items:center; justify-content:center; font-size:14px; flex-shrink:0; }
.fi-pdf { background:rgba(240,112,112,.15); } .fi-docx { background:var(--accent-lt); } .fi-pptx { background:var(--gold-lt); } .fi-txt { background:var(--sage-lt); } .fi-gen { background:var(--surface3); }
.sb-file-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; color:var(--text2) !important; }

/* ── Nav/mode buttons ── */
.stButton > button[kind="primary"] { background: linear-gradient(135deg,var(--accent),var(--accent2)) !important; color: #fff !important; border: none !important; border-radius: 9px !important; font-family: 'Sora', sans-serif !important; font-size: 12px !important; font-weight: 600 !important; padding: 8px 12px !important; box-shadow: 0 2px 8px var(--accent-glow) !important; transition: opacity .15s, transform .1s !important; }
.stButton > button[kind="primary"]:hover { opacity:.88 !important; transform:translateY(-1px) !important; }
.stButton > button[kind="secondary"] { background: var(--surface2) !important; color: var(--text2) !important; border: 1px solid var(--border2) !important; border-radius: 9px !important; font-family: 'Sora', sans-serif !important; font-size: 12px !important; font-weight: 500 !important; padding: 8px 12px !important; transition: all .15s !important; }
.stButton > button[kind="secondary"]:hover { background: var(--surface3) !important; color: var(--text) !important; }

/* ── Level pill buttons ── */
.level-beginner  { color: var(--sage)   !important; background: var(--sage-lt)   !important; }
.level-intermediate { color: var(--accent) !important; background: var(--accent-lt) !important; }
.level-advanced  { color: var(--purple) !important; background: var(--purple-lt) !important; }

/* ── Welcome ── */
/* ── Persistent Chat Console ── */
.chat-console {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  margin: 0 10px;
  padding: 0;
  box-shadow: 0 -4px 24px rgba(0,0,0,0.4);
  overflow: hidden;
}
.chat-console-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
}
.chat-console-icon { font-size: 15px; }
.chat-console-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  flex: 1;
  letter-spacing: 0.02em;
}
.chat-console-mode {
  font-size: 10px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-lt);
  border-radius: 6px;
  padding: 3px 8px;
  white-space: nowrap;
}
.chat-console-body {
  padding: 10px 14px 14px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.chat-console-body .stTextInput {
  flex: 1;
}
.chat-console-body .stButton {
  flex: 0 0 auto;
  margin-bottom: 1px;
}
.chat-console-body .stTextInput > div > div > input {
  background: var(--surface2) !important;
  border: 1.5px solid var(--border2) !important;
  border-radius: 10px !important;
  padding: 10px 14px !important;
  font-size: 13px !important;
}
.chat-console-body .stButton > button[kind="primary"] {
  padding: 10px 18px !important;
  font-size: 13px !important;
  border-radius: 10px !important;
  white-space: nowrap !important;
}

.welcome-card { max-width:560px; margin:0 auto; text-align:center; padding:64px 24px 48px; }
.welcome-glyph { width:76px; height:76px; border-radius:22px; background:var(--accent-lt); border:1px solid rgba(52,211,153,.25); display:flex; align-items:center; justify-content:center; font-size:36px; margin:0 auto 26px; box-shadow:0 4px 16px var(--accent-glow); }
.welcome-h { font-family:'Lora',Georgia,serif; font-size:30px; font-weight:600; color:var(--text); margin:0 0 12px; line-height:1.25; }
.welcome-h em { font-style:italic; color:var(--accent); }
.welcome-p { font-size:15px; color:var(--text2); line-height:1.7; margin:0 0 28px; }
.welcome-chips { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
.welcome-chip { background:var(--surface2); border:1px solid var(--border2); border-radius:8px; padding:8px 14px; font-size:12px; color:var(--text2); }

/* ── Chat bubbles ── */
.msg-row { display:flex; margin-bottom:24px; align-items:flex-start; }
.msg-row-user { justify-content:flex-end; }
.msg-row-ai   { justify-content:flex-start; }
.bubble { max-width:70%; padding:14px 18px; font-size:14px; line-height:1.75; border-radius:var(--r-lg); }
.bubble-user { background: linear-gradient(135deg,var(--accent),var(--accent2)); color: #fff !important; border-radius: var(--r-lg) var(--r-lg) 5px var(--r-lg); box-shadow: 0 4px 16px var(--accent-glow); font-weight: 500; }
.bubble-ai { background: var(--surface2); border: 1px solid var(--border2); color: var(--text) !important; border-radius: 5px var(--r-lg) var(--r-lg) var(--r-lg); box-shadow: var(--sh); }
.avatar { width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:16px; flex-shrink:0; margin-top:4px; }
.avatar-user { background:var(--accent-lt); margin-left:10px; order:2; }
.avatar-ai   { background:linear-gradient(135deg,var(--accent),var(--accent2)); box-shadow:0 2px 8px var(--accent-glow); margin-right:10px; }
.ai-label { font-size:10px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--accent) !important; margin-bottom:6px; }
.src-bar  { display:flex; flex-wrap:wrap; gap:5px; margin-top:12px; padding-top:10px; border-top:1px solid var(--border); }
.src-chip { background:var(--accent-lt); border:1px solid rgba(52,211,153,.25); border-radius:6px; padding:2px 9px; font-size:11px; color:var(--accent) !important; font-weight:500; }

/* ── Q-Bank cards ── */
.qcard { background:var(--surface2); border:1px solid var(--border2); border-radius:12px; padding:18px 20px; margin-bottom:12px; }
.qcard-num { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.1em; color:var(--text3) !important; margin-bottom:6px; }
.qcard-q { font-size:14px; font-weight:600; color:var(--text) !important; margin-bottom:10px; line-height:1.5; }
.qcard-opt { font-size:13px; color:var(--text2) !important; padding:4px 0; }
.qcard-opt-correct { color:var(--sage) !important; font-weight:600; }
.qmark { background:var(--gold-lt); color:var(--gold) !important; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:700; }
.answer-box { background:var(--surface3); border-left:3px solid var(--sage); border-radius:0 8px 8px 0; padding:10px 14px; margin-top:10px; font-size:13px; color:var(--text) !important; line-height:1.6; }
.kpoint { display:flex; align-items:flex-start; gap:8px; font-size:12px; color:var(--text2) !important; margin-top:4px; }

/* ── Upload ── */
.ucard-title { font-family:'Lora',Georgia,serif; font-size:22px; font-weight:600; color:var(--text); margin:0 0 6px; }
.ucard-sub { font-size:13px; color:var(--text2); margin-bottom:20px; line-height:1.6; }
.fpill { display:flex; align-items:center; gap:10px; background:var(--surface2); border:1px solid var(--border); border-radius:10px; padding:10px 14px; margin-bottom:6px; font-size:13px; box-shadow:var(--sh); }
.fpill-ok  { border-color:rgba(78,203,141,.3);  background:var(--sage-lt); }
.fpill-err { border-color:rgba(240,112,112,.3); background:var(--rose-lt); }
.fpill-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text) !important; }
.fpill-ext { background:var(--accent-lt); color:var(--accent) !important; border-radius:5px; padding:2px 8px; font-size:10px; font-weight:700; }
.fpill-chunks { background:var(--sage-lt); color:var(--sage) !important; border-radius:5px; padding:2px 8px; font-size:11px; font-weight:600; }

/* ── How-it-works ── */
.how-card { background: var(--surface2); border: 1px solid var(--border2); border-radius:14px; padding:22px 24px; box-shadow:var(--sh); }
.how-card-title { font-size:11px; font-weight:700; color:var(--text3) !important; letter-spacing:.12em; text-transform:uppercase; margin-bottom:16px; }
.how-step { display:flex; align-items:flex-start; gap:12px; margin-bottom:14px; }
.how-num { width:26px; height:26px; border-radius:50%; background:var(--accent-lt); color:var(--accent) !important; font-size:12px; font-weight:700; display:flex; align-items:center; justify-content:center; flex-shrink:0; border:1px solid rgba(52,211,153,.25); }
.how-text { font-size:13px; color:var(--text2) !important; line-height:1.6; }
.how-text strong { color:var(--text) !important; font-weight:600; }
.fmt-badge { border-radius:6px; padding:3px 10px; font-size:12px; font-weight:700; }
.fmt-pdf { background:var(--rose-lt); color:var(--rose) !important; } .fmt-docx { background:var(--accent-lt); color:var(--accent) !important; } .fmt-pptx { background:var(--gold-lt); color:var(--gold) !important; } .fmt-txt { background:var(--sage-lt); color:var(--sage) !important; }

/* ── KG Legend ── */
.kg-legend { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0 16px; }
.kg-dot { width:10px; height:10px; border-radius:50%; display:inline-block; margin-right:5px; }
.kg-item { display:flex; align-items:center; font-size:12px; color:var(--text2) !important; background:var(--surface2); border:1px solid var(--border); border-radius:8px; padding:4px 10px; }

/* ── Section header ── */
.sec-header { font-family:'Lora',Georgia,serif; font-size:20px; font-weight:600; color:var(--text); margin-bottom:6px; }
.sec-sub { font-size:13px; color:var(--text2); margin-bottom:20px; }

/* ── Assessment header ── */
.assess-header { background:var(--surface2); border:1px solid var(--border2); border-radius:14px; padding:20px 24px; margin-bottom:20px; }
.assess-title { font-family:'Lora',serif; font-size:18px; font-weight:600; color:var(--text) !important; margin-bottom:8px; }
.assess-marks { font-size:13px; color:var(--text2) !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def file_icon(name: str) -> tuple:
    ext = Path(name).suffix.lower()
    return {
        ".pdf":  ("📄", "fi-pdf"),
        ".docx": ("📝", "fi-docx"),
        ".pptx": ("📊", "fi-pptx"),
        ".txt":  ("📃", "fi-txt"),
    }.get(ext, ("📁", "fi-gen"))


MODE_META = {
    "explain":    {"icon": "📖", "label": "Explain",    "color": "var(--accent)"},
    "exam":       {"icon": "📝", "label": "Exam Q",     "color": "var(--gold)"},
    "synthesize": {"icon": "🔀", "label": "Synthesize", "color": "var(--sage)"},
    "exam_map":   {"icon": "🗺️", "label": "Exam Map",   "color": "var(--purple)"},
}

LEVEL_META = {
    "beginner":     {"icon": "🌱", "label": "Beginner",     "cls": "level-beginner"},
    "intermediate": {"icon": "📚", "label": "Intermediate", "cls": "level-intermediate"},
    "advanced":     {"icon": "🔬", "label": "Advanced",     "cls": "level-advanced"},
}


# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR (Google Drive Layout Flow)
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Header logo
    st.markdown("""
    <div class="sb-logo" style="padding: 16px 14px 10px; border-bottom: none;">
      <span class="sb-logo-icon">🎓</span>
      <span class="sb-logo-text" style="font-family:'Outfit',sans-serif;font-size:18px;font-weight:700;color:var(--text);">Scholar AI</span>
      <span class="sb-logo-beta" style="font-size:9px;font-weight:700;color:var(--accent);background:var(--accent-lt);border-radius:4px;padding:2px 6px;margin-left:6px;">PRO</span>
    </div>
    """, unsafe_allow_html=True)

    stats = get_stats()

    # User profile at left top
    storage_type = "Cloud (Supabase)" if sm.IS_SUPABASE_ACTIVE else "Local Disk"
    st.markdown(f"""
    <div class="profile-card">
      <div class="profile-avatar">🧑</div>
      <div class="profile-info">
        <div class="profile-email" title="{st.session_state.logged_in_user}">{st.session_state.logged_in_user}</div>
        <div class="profile-status">Online • {storage_type}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Active DB Stats
    st.markdown(f"""
    <div class="sb-stats" style="display:flex; gap:8px; margin: 8px 14px 14px;">
      <div class="sb-stat" style="flex:1;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:8px;padding:8px;text-align:center;"><div class="sb-stat-n" style="font-size:18px;font-weight:700;color:var(--text);">{stats["documents"]}</div><div class="sb-stat-l" style="font-size:9px;text-transform:uppercase;color:var(--text3);margin-top:2px;">Docs</div></div>
      <div class="sb-stat" style="flex:1;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:8px;padding:8px;text-align:center;"><div class="sb-stat-n" style="font-size:18px;font-weight:700;color:var(--text);">{stats["chunks"]}</div><div class="sb-stat-l" style="font-size:9px;text-transform:uppercase;color:var(--text3);margin-top:2px;">Chunks</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-nav-label">Workspace Navigation</div>', unsafe_allow_html=True)

    # Sidebar Navigation items list
    nav_items = [
        ("chat",             "💬 Chat"),
        ("upload",           "📤 Upload"),
        ("learning_path",    "🗺️ Learning Path"),
        ("qbank",            "📋 Q-Bank"),
        ("knowledge_graph",  "🕸️ Knowledge Graph"),
        ("progress",         "📊 Progress"),
        ("settings",         "⚙️ Settings"),
    ]
    for view_key, view_label in nav_items:
        is_active = st.session_state.view == view_key
        if st.button(view_label, key=f"nav_btn_{view_key}", use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state.view = view_key
            st.rerun()

    # ── Mode & Level selectors ──────────────────────────────────
    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-nav-label">Assistant Mode</div>', unsafe_allow_html=True)

    mode_items = [
        ("explain",   "📖 Explain"),
        ("exam",      "📝 Exam Q"),
        ("synthesize","🔀 Synthesize"),
        ("exam_map",  "🗺️ Exam Map"),
    ]
    for mk, ml in mode_items:
        is_active_mode = st.session_state.mode == mk
        if st.button(ml, key=f"sb_mode_{mk}", use_container_width=True,
                     type="primary" if is_active_mode else "secondary"):
            st.session_state.mode = mk
            st.rerun()

    # Level selector (only for explain / synthesize)
    if st.session_state.mode in ("explain", "synthesize"):
        st.markdown('<div class="sb-nav-label">Difficulty Level</div>', unsafe_allow_html=True)
        lv_items = [("beginner","🌱 Beginner"), ("intermediate","📚 Intermediate"), ("advanced","🔬 Advanced")]
        for lk, ll in lv_items:
            is_active_lv = st.session_state.level == lk
            if st.button(ll, key=f"sb_level_{lk}", use_container_width=True,
                         type="primary" if is_active_lv else "secondary"):
                st.session_state.level = lk
                st.rerun()

    # ── Content filters & docs ──────────────────────────────────
    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    if stats["subjects"]:
        with st.expander("🔍 Filter Content", expanded=False):
            subject_opts = ["All Subjects"] + stats["subjects"]
            sel_subj = st.selectbox("Subject", subject_opts, key="sb_subject_select")
            st.session_state.subject_filter = None if sel_subj == "All Subjects" else sel_subj

            if st.session_state.subject_filter:
                chapters = stats["chapters_by_subject"].get(st.session_state.subject_filter, [])
                if chapters:
                    chap_opts = ["All Chapters"] + chapters
                    sel_chap = st.selectbox("Chapter", chap_opts, key="sb_chapter_select")
                    st.session_state.chapter_filter = None if sel_chap == "All Chapters" else sel_chap

    with st.expander("📁 Indexed Documents", expanded=False):
        if stats["sources"]:
            for s in stats["sources"]:
                ico, cls = file_icon(s)
                display = s if len(s) <= 24 else s[:21] + "…"
                st.markdown(f"""
                <div class="sb-file-row" style="display:flex;align-items:center;gap:8px;padding:6px;border-radius:6px;margin-bottom:2px;font-size:11px;">
                  <span class="sb-file-icon {cls}" style="flex-shrink:0;">{ico}</span>
                  <span class="sb-file-name" title="{s}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;">{display}</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-size:11px;font-style:italic;color:var(--text3)!important;padding:4px 8px;">No files yet</p>', unsafe_allow_html=True)

        st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
        if st.button("🗑 Clear Database", key="clear_kb_btn", use_container_width=True):
            import vector_store as vs
            vs.clear_vector_store()
            if st.session_state.logged_in_user:
                sm.clear_vector_store_files(st.session_state.logged_in_user)
            st.session_state.history = []; st.session_state.indexed = False
            st.session_state.kg_data = None; st.session_state.lp_result = None
            st.session_state.qb_result = None
            st.rerun()

    # ── Sleek Logout at bottom ──────────────────────────────────
    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)
    if st.button("🚪   Log Out", key="logout_btn", use_container_width=True):
        logout_user()
        st.rerun()

    st.markdown("""
    <div style="font-size:9px;text-align:center;color:var(--text3)!important;margin-top:10px;line-height:1.4;padding:0 8px;">
      Supports PDF · DOCX · PPTX · TXT<br>
      Powered by Gemini 2.5 + FAISS
    </div>
    """, unsafe_allow_html=True)

if st.session_state.view == "upload":
    st.markdown('<div style="padding:32px 44px;">', unsafe_allow_html=True)
    col_up, col_how = st.columns([3, 2], gap="large")

    with col_up:
        st.markdown('<div class="ucard-title">📤 Upload Study Materials</div>', unsafe_allow_html=True)
        st.markdown('<div class="ucard-sub">Drag & drop or browse your files. Supports PDF, DOCX, PPTX, and TXT.</div>', unsafe_allow_html=True)
        files = st.file_uploader("Drop files here", type=["pdf","docx","pptx","txt"],
                                 accept_multiple_files=True, label_visibility="collapsed")
        if files:
            for f in files:
                ext = Path(f.name).suffix.upper().lstrip(".")
                st.markdown(f'<div class="fpill">📄 <span class="fpill-name">{f.name}</span><span class="fpill-ext">{ext}</span></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        process_btn = st.button("⚡  Process & Index Documents", use_container_width=True, type="primary")

        if process_btn and files:
            new_docs = []
            prog = st.progress(0, text="Reading files…")
            for i, file in enumerate(files):
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.name).suffix) as tmp:
                    tmp.write(file.read()); path = tmp.name
                try:
                    doc = process_document(path); doc["filename"] = file.name
                    new_docs.append(doc)
                    st.markdown(f'<div class="fpill fpill-ok">✅ <span class="fpill-name">{file.name}</span><span class="fpill-chunks">{doc["num_chunks"]} chunks</span></div>', unsafe_allow_html=True)
                except Exception as e:
                    st.markdown(f'<div class="fpill fpill-err">❌ <span class="fpill-name">{file.name}: {e}</span></div>', unsafe_allow_html=True)
                finally:
                    os.unlink(path)
                prog.progress((i+1)/len(files), text=f"Processing {i+1}/{len(files)}…")

            if new_docs:
                mode_key, _ = get_api_key_and_model("explain")
                with st.spinner("Embedding & building vector index…"):
                    add_documents(new_docs, api_key=mode_key)
                    if st.session_state.logged_in_user:
                        import vector_store as vs
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".faiss") as tmp_f:
                            tmp_path = tmp_f.name
                        try:
                            if vs.faiss_index is not None:
                                import faiss
                                faiss.write_index(vs.faiss_index, tmp_path)
                            sm.save_vector_store(
                                st.session_state.logged_in_user,
                                vs.chunks_store,
                                vs.metadata_store,
                                tmp_path
                            )
                        finally:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                st.session_state.indexed = True
                st.session_state.kg_data = None  # Invalidate cached KG
                prog.empty()
                st.success(f"🎉 {len(new_docs)} document(s) indexed! Switch to Chat to ask questions.")
        elif process_btn and not files:
            st.warning("Upload at least one file first.")

    with col_how:
        st.markdown("""
        <div style="margin-top:42px;">
          <div class="how-card">
            <div class="how-card-title">How it works</div>
            <div class="how-step"><div class="how-num">1</div><div class="how-text"><strong>Upload</strong> your PDFs, notes, slides, or textbooks.</div></div>
            <div class="how-step"><div class="how-num">2</div><div class="how-text"><strong>Process</strong> — Scholar AI chunks, embeds, and indexes your content.</div></div>
            <div class="how-step"><div class="how-num">3</div><div class="how-text"><strong>Ask</strong> anything in Chat, generate a Learning Path, or build a Q-Bank.</div></div>
          </div>
          <div class="how-card" style="margin-top:14px;">
            <div class="how-card-title">Supported formats</div>
            <div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:4px;">
              <span class="fmt-badge fmt-pdf">PDF</span>
              <span class="fmt-badge fmt-docx">DOCX</span>
              <span class="fmt-badge fmt-pptx">PPTX</span>
              <span class="fmt-badge fmt-txt">TXT</span>
            </div>
          </div>
          <div class="how-card" style="margin-top:14px;">
            <div class="how-card-title">Week 3-5 Features</div>
            <div class="how-step"><div class="how-num">🔀</div><div class="how-text"><strong>Synthesize</strong> topics across multiple uploaded documents.</div></div>
            <div class="how-step"><div class="how-num">🗺️</div><div class="how-text"><strong>Learning Path</strong> — theory → examples → self-assessment.</div></div>
            <div class="how-step"><div class="how-num">📋</div><div class="how-text"><strong>Q-Bank</strong> — auto-generate MCQ, short & long answer questions.</div></div>
            <div class="how-step"><div class="how-num">🕸️</div><div class="how-text"><strong>Knowledge Graph</strong> — visual map of topic relationships.</div></div>
            <div class="how-step"><div class="how-num">📊</div><div class="how-text"><strong>Progress Tracker</strong> — sessions, quiz scores & study streak. <span style="color:var(--sage);font-weight:700;">NEW</span></div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: CHAT
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "chat":
    # ── Active mode status header (mode/level selectors are in sidebar) ──
    mm = MODE_META.get(st.session_state.mode, MODE_META["explain"])
    lm = LEVEL_META.get(st.session_state.level, LEVEL_META["intermediate"])
    level_html = ""
    if st.session_state.mode in ("explain", "synthesize"):
        level_html = f' · <span style="color:var(--sage);">{lm["icon"]} {lm["label"]}</span>'
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;padding:12px 20px;background:var(--surface2);border:1px solid var(--border);border-radius:12px;margin-bottom:12px;">
      <span style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.1em;">Active Mode:</span>
      <span style="font-size:13px;font-weight:600;color:var(--accent);">{mm['icon']} {mm['label']}</span>
      {level_html}
    </div>
    """, unsafe_allow_html=True)
    chat_area = st.container()


    with chat_area:
        if not st.session_state.history:
            mode_info = {
                "explain":    "Ask me to <strong>explain</strong> any topic from your materials.",
                "exam":       "Paste an <strong>exam question</strong> — I'll write a model answer.",
                "synthesize": "I'll <strong>synthesise</strong> a topic across all your uploaded docs.",
                "exam_map":   "I'll map a topic to <strong>likely exam patterns</strong> and high-yield content.",
            }
            st.markdown(f"""
            <div class="welcome-card">
              <div class="welcome-glyph">🎓</div>
              <h2 class="welcome-h">Ask <em>Scholar AI</em> anything</h2>
              <p class="welcome-p">{mode_info[st.session_state.mode]}<br>Upload your materials first, then ask away.</p>
              <div class="welcome-chips">
                <span class="welcome-chip">📖 Topic explanations</span>
                <span class="welcome-chip">📝 Exam solving</span>
                <span class="welcome-chip">🔀 Multi-source synthesis</span>
                <span class="welcome-chip">🗺️ Exam pattern mapping</span>
              </div>
            </div>""", unsafe_allow_html=True)

        for item in st.session_state.history:
            mm   = MODE_META.get(item["mode"], MODE_META["explain"])
            lm   = LEVEL_META.get(item.get("level", "intermediate"), LEVEL_META["intermediate"])
            lbl  = f"{mm['icon']} {mm['label']}"
            if item["mode"] in ("explain", "synthesize"):
                lbl += f" · {lm['icon']} {lm['label']}"

            st.markdown(f'<div class="msg-row msg-row-user"><div class="bubble bubble-user">{item["q"]}</div><div class="avatar avatar-user">🧑</div></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="ai-label" style="margin-left:44px;">Scholar AI · {lbl}</div>', unsafe_allow_html=True)

            with st.container():
                col_av, col_ans = st.columns([0.05, 0.95])
                with col_av:
                    st.markdown('<div class="avatar avatar-ai" style="margin-top:2px;">🤖</div>', unsafe_allow_html=True)
                with col_ans:
                    st.markdown('<div style="background:var(--surface2);border:1px solid var(--border2);color:var(--text);padding:16px 20px;border-radius:5px 14px 14px 14px;font-size:14px;line-height:1.75;box-shadow:var(--sh);">', unsafe_allow_html=True)
                    st.markdown(item["a"])
                    if item.get("sources"):
                        seen  = {s["source"]: s for s in item["sources"]}
                        chips = "".join(f'<span class="src-chip">📄 {s["source"]}</span>' for s in seen.values())
                        st.markdown(f'<div class="src-bar">{chips}</div>', unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: LEARNING PATH
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "learning_path":
    st.markdown('<div style="padding:32px 44px 20px;">', unsafe_allow_html=True)
    st.markdown('<div class="sec-header">🗺️ Learning Path Generator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-sub">Enter any topic to get a structured learning journey: Theory → Worked Examples → Self-Assessment.</div>', unsafe_allow_html=True)

    lp_col1, lp_col2, lp_col3 = st.columns([3, 1, 1], gap="small")
    with lp_col1:
        lp_topic = st.text_input("Topic", placeholder="e.g. Binary Search Trees, Normalization, Newton's Laws…", label_visibility="collapsed")
    with lp_col2:
        lp_level = st.selectbox("Level", ["Beginner", "Intermediate", "Advanced"], index=1, label_visibility="collapsed")
    with lp_col3:
        lp_btn = st.button("Generate Path →", use_container_width=True, type="primary")

    st.markdown('</div>', unsafe_allow_html=True)

    if lp_btn and lp_topic:
        if not st.session_state.indexed:
            st.warning("⚠️ Please upload and index documents first.")
        else:
            mode_key, mode_model = get_api_key_and_model("learning_path")
            with st.spinner(f"Building learning path for '{lp_topic}'…"):
                result, sources = generate_learning_path(
                    lp_topic, subject=st.session_state.subject_filter,
                    model_name=mode_model, api_key=mode_key
                )
            st.session_state.lp_result = {"topic": lp_topic, "level": lp_level,
                                           "result": result, "sources": sources}
            # Week 5: track this study session
            record_session(topic=lp_topic, mode="learning_path",
                           level=lp_level.lower(),
                           subject=st.session_state.subject_filter)

    if lp_btn and not lp_topic:
        st.warning("Please enter a topic first.")

    # ── Also show Prerequisites ──────────────────────────────────────────
    if st.session_state.lp_result:
        data = st.session_state.lp_result
        st.markdown(f'<div style="padding:0 44px;">', unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["📖 Learning Path", "🔑 Prerequisites"])

        with tab1:
            st.markdown(
                f'<div style="background:var(--surface2);border:1px solid var(--border2);'
                f'border-radius:14px;padding:24px 28px;font-size:14px;line-height:1.8;">',
                unsafe_allow_html=True
            )
            st.markdown(data["result"])
            if data["sources"]:
                seen  = {s["source"]: s for s in data["sources"]}
                chips = "".join(f'<span class="src-chip">📄 {s}</span>' for s in seen)
                st.markdown(f'<div class="src-bar">{chips}</div>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with tab2:
            mode_key, mode_model = get_api_key_and_model("learning_path")
            with st.spinner("Identifying prerequisites…"):
                prereq_result, prereq_src = identify_prerequisites(
                    data["topic"], subject=st.session_state.subject_filter,
                    model_name=mode_model, api_key=mode_key
                )
            st.markdown(
                '<div style="background:var(--surface2);border:1px solid var(--border2);'
                'border-radius:14px;padding:24px 28px;font-size:14px;line-height:1.8;">',
                unsafe_allow_html=True
            )
            st.markdown(prereq_result)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: Q-BANK
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "qbank":
    st.markdown('<div style="padding:32px 44px 20px;">', unsafe_allow_html=True)
    st.markdown('<div class="sec-header">📋 Question Bank Generator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-sub">Auto-generate MCQ, short-answer, long-answer, or a full assessment from your study materials.</div>', unsafe_allow_html=True)

    qb_c1, qb_c2, qb_c3, qb_c4 = st.columns([3, 1.5, 1, 1], gap="small")
    with qb_c1:
        qb_topic = st.text_input("Topic", placeholder="e.g. Database Normalization, Recursion…", label_visibility="collapsed")
    with qb_c2:
        qb_type = st.selectbox("Question Type",
                               ["MCQ", "Short Answer", "Long Answer", "Full Assessment"],
                               label_visibility="collapsed")
    with qb_c3:
        qb_count = st.selectbox("Count", [3, 5, 8, 10], index=1, label_visibility="collapsed") \
            if qb_type != "Full Assessment" else st.empty()
    with qb_c4:
        qb_btn = st.button("Generate →", use_container_width=True, type="primary")

    st.markdown('</div>', unsafe_allow_html=True)

    if qb_btn and qb_topic:
        if not st.session_state.indexed:
            st.warning("⚠️ Please upload and index documents first.")
        else:
            subj = st.session_state.subject_filter
            mode_key, mode_model = get_api_key_and_model("qbank")
            with st.spinner(f"Generating {qb_type} questions on '{qb_topic}'…"):
                if qb_type == "MCQ":
                    qs, src = generate_mcq(qb_topic, count=qb_count, subject=subj, model_name=mode_model, api_key=mode_key)
                    st.session_state.qb_result = {"type": "mcq", "topic": qb_topic, "questions": qs, "sources": src}
                elif qb_type == "Short Answer":
                    qs, src = generate_short_answer(qb_topic, count=qb_count, subject=subj, model_name=mode_model, api_key=mode_key)
                    st.session_state.qb_result = {"type": "short", "topic": qb_topic, "questions": qs, "sources": src}
                elif qb_type == "Long Answer":
                    qs, src = generate_long_answer(qb_topic, count=qb_count, subject=subj, model_name=mode_model, api_key=mode_key)
                    st.session_state.qb_result = {"type": "long", "topic": qb_topic, "questions": qs, "sources": src}
                else:
                    assessment, src = generate_full_assessment(qb_topic, subject=subj, model_name=mode_model, api_key=mode_key)
                    st.session_state.qb_result = {"type": "full", "topic": qb_topic, "assessment": assessment, "sources": src}

            # Week 5: track Q-Bank generation as a study session
            record_session(topic=qb_topic, mode="qbank", subject=subj)

    if qb_btn and not qb_topic:
        st.warning("Please enter a topic first.")

    # ── Render Q-Bank results ─────────────────────────────────────────────
    if st.session_state.qb_result:
        data = st.session_state.qb_result
        st.markdown('<div style="padding:0 44px;">', unsafe_allow_html=True)

        def render_mcq(questions):
            if not questions:
                st.warning("No MCQ questions could be generated. Try a different topic."); return
            for i, q in enumerate(questions, 1):
                with st.expander(f"Q{i}: {q.get('question','')[:90]}…", expanded=(i==1)):
                    st.markdown(f'<div class="qcard-q">{q.get("question","")}</div>', unsafe_allow_html=True)
                    opts = q.get("options", {})
                    correct = q.get("answer", "")
                    for key, val in opts.items():
                        cls = "qcard-opt-correct" if key == correct else "qcard-opt"
                        prefix = "✅ " if key == correct else f"{key}. "
                        st.markdown(f'<div class="{cls}">{prefix}{val}</div>', unsafe_allow_html=True)
                    if q.get("explanation"):
                        st.markdown(f'<div class="answer-box">💡 {q["explanation"]}</div>', unsafe_allow_html=True)

        def render_short(questions):
            if not questions:
                st.warning("No short-answer questions generated."); return
            for i, q in enumerate(questions, 1):
                with st.expander(f"Q{i} ({q.get('marks','?')} marks): {q.get('question','')[:80]}…", expanded=(i==1)):
                    st.markdown(f'<span class="qmark">{q.get("marks","?")} marks</span>', unsafe_allow_html=True)
                    st.markdown(f'<div class="qcard-q" style="margin-top:8px;">{q.get("question","")}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="answer-box"><strong>Model Answer:</strong><br>{q.get("model_answer","")}</div>', unsafe_allow_html=True)
                    if q.get("key_points"):
                        st.markdown('<div style="margin-top:8px;font-size:12px;color:var(--text3)!important;font-weight:700;text-transform:uppercase;letter-spacing:.08em;">Key Points</div>', unsafe_allow_html=True)
                        for pt in q["key_points"]:
                            st.markdown(f'<div class="kpoint">• {pt}</div>', unsafe_allow_html=True)

        def render_long(questions):
            if not questions:
                st.warning("No long-answer questions generated."); return
            for i, q in enumerate(questions, 1):
                with st.expander(f"Q{i} ({q.get('marks','?')} marks)", expanded=(i==1)):
                    st.markdown(f'<span class="qmark">{q.get("marks","?")} marks</span>', unsafe_allow_html=True)
                    st.markdown(f'<div class="qcard-q" style="margin-top:8px;">{q.get("question","")}</div>', unsafe_allow_html=True)
                    if q.get("parts"):
                        st.markdown('<div style="margin-top:6px;">', unsafe_allow_html=True)
                        for part in q["parts"]:
                            st.markdown(f'<div style="font-size:13px;color:var(--text2)!important;padding:2px 0;">{part}</div>', unsafe_allow_html=True)
                        st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="answer-box" style="margin-top:10px;"><strong>Model Answer:</strong><br>{q.get("model_answer","")}</div>', unsafe_allow_html=True)
                    if q.get("marking_scheme"):
                        st.markdown('<div style="margin-top:10px;font-size:12px;color:var(--text3)!important;font-weight:700;text-transform:uppercase;letter-spacing:.08em;">Marking Scheme</div>', unsafe_allow_html=True)
                        for ms in q["marking_scheme"]:
                            st.markdown(f'<div class="kpoint">• {ms}</div>', unsafe_allow_html=True)

        if data["type"] == "mcq":
            st.markdown(f'<div class="sec-header" style="font-size:16px;">📝 MCQ — {data["topic"]}</div>', unsafe_allow_html=True)
            render_mcq(data["questions"])

        elif data["type"] == "short":
            st.markdown(f'<div class="sec-header" style="font-size:16px;">✏️ Short Answer — {data["topic"]}</div>', unsafe_allow_html=True)
            render_short(data["questions"])

        elif data["type"] == "long":
            st.markdown(f'<div class="sec-header" style="font-size:16px;">📜 Long Answer — {data["topic"]}</div>', unsafe_allow_html=True)
            render_long(data["questions"])

        elif data["type"] == "full":
            assessment = data["assessment"]
            breakdown  = " · ".join(f"{k}: {v}" for k, v in assessment.get("breakdown", {}).items())
            st.markdown(f"""
            <div class="assess-header">
              <div class="assess-title">📋 Full Assessment — {assessment["topic"]}</div>
              <div class="assess-marks">Total: <strong>{assessment["total_marks"]} marks</strong> &nbsp;|&nbsp; {breakdown}</div>
            </div>""", unsafe_allow_html=True)

            tab_mcq, tab_sa, tab_la = st.tabs(["📝 Section A: MCQ", "✏️ Section B: Short Answer", "📜 Section C: Long Answer"])
            with tab_mcq:   render_mcq(assessment.get("mcq", []))
            with tab_sa:    render_short(assessment.get("short_answer", []))
            with tab_la:    render_long(assessment.get("long_answer", []))

        # Sources
        if data.get("sources"):
            seen  = {s["source"]: s for s in data["sources"]}
            chips = "".join(f'<span class="src-chip">📄 {s}</span>' for s in seen)
            st.markdown(f'<div class="src-bar" style="margin-top:20px;">{chips}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: KNOWLEDGE GRAPH
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "knowledge_graph":
    st.markdown('<div style="padding:32px 44px 20px;">', unsafe_allow_html=True)
    st.markdown('<div class="sec-header">🕸️ Knowledge Graph</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-sub">Visualise the relationships between topics in your study materials.</div>', unsafe_allow_html=True)

    kg_c1, kg_c2, kg_c3 = st.columns([2, 2, 1], gap="small")
    with kg_c1:
        kg_topic_filter = st.text_input("Filter by topic (optional)", placeholder="e.g. 'sorting' to focus the graph…", label_visibility="collapsed")
    with kg_c2:
        kg_subject_filter = st.text_input("Subject focus (optional)", placeholder="e.g. Computer Science, Mathematics…", label_visibility="collapsed")
    with kg_c3:
        kg_btn = st.button("Build Graph →", use_container_width=True, type="primary")

    st.markdown('</div>', unsafe_allow_html=True)

    if kg_btn:
        if not st.session_state.indexed:
            st.warning("⚠️ Please upload and index documents first.")
        else:
            mode_key, mode_model = get_api_key_and_model("knowledge_graph")
            with st.spinner("Extracting topics and building knowledge graph…"):
                graph = build_knowledge_graph(subject=kg_subject_filter or None, model_name=mode_model, api_key=mode_key)
            st.session_state.kg_data = {"graph": graph, "topic_filter": kg_topic_filter}

    if st.session_state.kg_data:
        kd    = st.session_state.kg_data
        graph = kd["graph"]

        if graph.get("error"):
            st.error(graph["error"])
        elif not graph.get("nodes"):
            st.info("No topics extracted yet. Try uploading more study materials.")
        else:
            # Apply topic filter if provided
            topic_filter = kd.get("topic_filter", "").strip()
            display_graph = get_topic_subgraph(topic_filter, graph) if topic_filter else graph

            node_count = len(display_graph["nodes"])
            edge_count = len(display_graph["edges"])

            st.markdown(f'<div style="padding:0 44px;">', unsafe_allow_html=True)

            # Stats row
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Nodes", node_count)
            m2.metric("Connections", edge_count)
            m3.metric("Total Topics", len(graph["nodes"]))
            m4.metric("Showing", f"{'All' if not topic_filter else topic_filter.title()}")

            # Legend
            st.markdown("""
            <div class="kg-legend">
              <div class="kg-item"><span class="kg-dot" style="background:#34d399;"></span> Concept</div>
              <div class="kg-item"><span class="kg-dot" style="background:#4ecb8d;"></span> Definition</div>
              <div class="kg-item"><span class="kg-dot" style="background:#f0b84a;"></span> Algorithm</div>
              <div class="kg-item"><span class="kg-dot" style="background:#f07070;"></span> Formula</div>
              <div class="kg-item"><span class="kg-dot" style="background:#a78bfa;"></span> Application</div>
              <div class="kg-item"><span class="kg-dot" style="background:#38bdf8;"></span> Theory</div>
            </div>
            """, unsafe_allow_html=True)

            # Graph visualisation
            html_str = render_graph_html(display_graph, height=520)
            components.html(html_str, height=540, scrolling=False)

            # Node table
            with st.expander("📋 Node Details"):
                for node in display_graph["nodes"]:
                    st.markdown(
                        f'<div class="fpill" style="margin-bottom:6px;">'
                        f'<span class="kg-dot" style="background:{node.get("color","#34d399")};width:12px;height:12px;border-radius:50%;flex-shrink:0;"></span>'
                        f'<span class="fpill-name"><strong>{node["label"]}</strong> — {node.get("description","")}</span>'
                        f'<span class="fpill-ext">{node.get("type","concept")}</span></div>',
                        unsafe_allow_html=True
                    )

            st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: PROGRESS TRACKER  (Week 5 New)
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "progress":
    st.markdown('<div style="padding:32px 44px 20px;">', unsafe_allow_html=True)
    st.markdown('<div class="sec-header">📊 Progress Tracker</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sec-sub">'
        'Track your study sessions, quiz scores, daily streak, and most-studied topics.'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div style="padding:0 44px 40px;">', unsafe_allow_html=True)
    render_progress_dashboard()
    st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "settings":
    st.markdown('<div style="padding:32px 44px 20px;">', unsafe_allow_html=True)
    st.markdown('<div class="sec-header">⚙️ Application Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-sub">Manage your model configurations, custom API keys, and account profile.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div style="padding:0 44px 40px;">', unsafe_allow_html=True)
    
    storage_type = "Cloud Storage (Supabase)" if sm.IS_SUPABASE_ACTIVE else "Local Disk Storage (Offline)"
    
    st.markdown(f"""
    <div style="background:var(--surface2); border:1px solid var(--border2); border-radius:14px; padding:20px 22px; margin-bottom:24px;">
      <div style="font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:var(--text3)!important; margin-bottom:14px;">🧑 Profile Info</div>
      <div style="font-size:14px; line-height:1.6; color:var(--text2)!important;">
        Email Address: <strong style="color:var(--text)!important;">{st.session_state.logged_in_user}</strong><br>
        Database Provider: <strong style="color:var(--text)!important;">{storage_type}</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("settings_form"):
        st.markdown('<h4 style="color:var(--text); margin-bottom:8px;">Google Gemini API Keys & Models</h4>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:12px; color:var(--text3)!important; margin-bottom:18px;">Specify a default API key, and optionally choose different models or override API keys for specific modes to leverage model specialties (e.g. Gemini 2.5 Pro for complex exams).</p>', unsafe_allow_html=True)
        
        default_key = st.text_input(
            "Default Google API Key", 
            value=st.session_state.api_settings.get("default_api_key", ""), 
            type="password", 
            placeholder="Defaults to GOOGLE_API_KEY from environment if blank..."
        )
        
        st.markdown("<hr style='border-color: var(--border2); margin:20px 0 !important;'>", unsafe_allow_html=True)
        st.markdown('<h4 style="color:var(--text); margin-bottom:8px;">Alternative Failover API Keys (Free Tier Providers)</h4>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:12px; color:var(--text3)!important; margin-bottom:18px;">Specify backup keys to automatically fallback to free alternative models (such as LLaMA on Groq or OpenRouter) when Gemini keys hit quota or token limits. Supports comma-separated lists of keys for rotation.</p>', unsafe_allow_html=True)
        
        groq_key = st.text_input(
            "Groq API Key(s)",
            value=st.session_state.api_settings.get("groq_api_key", ""),
            type="password",
            placeholder="e.g. gsk_key1, gsk_key2 (Uses GROQ_API_KEY from environment if blank...)"
        )
        
        openrouter_key = st.text_input(
            "OpenRouter API Key(s)",
            value=st.session_state.api_settings.get("openrouter_api_key", ""),
            type="password",
            placeholder="e.g. sk-or-v1-key1, sk-or-v1-key2 (Uses OPENROUTER_API_KEY from environment if blank...)"
        )
        
        st.markdown("<hr style='border-color: var(--border2); margin:20px 0 !important;'>", unsafe_allow_html=True)
        
        model_options = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.0-pro-exp"]
        
        modes_to_configure = [
            ("explain", "📖 Explain Mode"),
            ("exam", "📝 Exam Q Mode"),
            ("synthesize", "🔀 Synthesize Mode"),
            ("exam_map", "🗺️ Exam Map Mode"),
        ]
        
        updated_modes = {}
        for m_key, m_label in modes_to_configure:
            st.markdown(f'<h5 style="color:var(--text); margin-top:10px; margin-bottom:4px;">{m_label}</h5>', unsafe_allow_html=True)
            mode_data = st.session_state.api_settings.get("modes", {}).get(m_key, {})
            
            c1, c2 = st.columns([1, 2], gap="small")
            with c1:
                cur_model = mode_data.get("model", "gemini-2.5-flash")
                idx = model_options.index(cur_model) if cur_model in model_options else 0
                sel_model = st.selectbox("Model", model_options, index=idx, key=f"set_model_{m_key}")
            with c2:
                cur_key = mode_data.get("api_key", "")
                sel_key = st.text_input("Override API Key", value=cur_key, type="password", placeholder="Uses default API key if blank...", key=f"set_key_{m_key}")
            
            updated_modes[m_key] = {"model": sel_model, "api_key": sel_key}
            
        submitted = st.form_submit_button("⚡ Save Settings", use_container_width=True)
        if submitted:
            st.session_state.api_settings["default_api_key"] = default_key
            st.session_state.api_settings["groq_api_key"] = groq_key
            st.session_state.api_settings["openrouter_api_key"] = openrouter_key
            st.session_state.api_settings["modes"] = updated_modes
            sm.save_api_settings(st.session_state.logged_in_user, st.session_state.api_settings)
            st.success("Settings saved successfully!")
            st.rerun()
            
    st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PERSISTENT CHAT CONSOLE — "Ask Vidya AI…" (visible on all pages)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div style="height: 32px;"></div>', unsafe_allow_html=True)

placeholders = {
    "explain":    "Ask about a topic (e.g. 'Explain binary search trees')…",
    "exam":       "Paste your exam question (e.g. 'Solve: Describe normalization steps')…",
    "synthesize": "Enter a topic to synthesise across all your documents…",
    "exam_map":   "Enter a topic to map to exam patterns and high-yield content…",
}
active_mode = st.session_state.mode
placeholder_txt = placeholders.get(active_mode, "Ask Vidya AI something…")

mode_desc_map = {
    "explain":    f"Explain Topic — {st.session_state.level.title()} Level",
    "exam":       "Solve Exam Question",
    "synthesize": f"Cross-Document Synthesis — {st.session_state.level.title()} Level",
    "exam_map":   "Exam Pattern Mapping",
}

st.markdown("""
<div class="chat-console">
  <div class="chat-console-header">
    <span class="chat-console-icon">💬</span>
    <span class="chat-console-title">Ask Vidya AI...</span>
    <span class="chat-console-mode">""" + mode_desc_map.get(active_mode, "Explain") + """</span>
  </div>
  <div class="chat-console-body">
""", unsafe_allow_html=True)

if "chat_input_key" not in st.session_state:
    st.session_state.chat_input_key = 0

col_input, col_btn = st.columns([6, 1], gap="small")
with col_input:
    global_query = st.text_input(
        "global_chat_bar",
        placeholder=placeholder_txt,
        label_visibility="collapsed",
        key=f"global_chat_input_{st.session_state.chat_input_key}",
    )
with col_btn:
    global_ask_btn = st.button("Ask", use_container_width=True, type="primary", key="global_send_btn")

st.markdown('</div></div>', unsafe_allow_html=True)

if (global_ask_btn or (global_query and global_query != "")) and global_query:
    if not st.session_state.indexed:
        st.warning("⚠️ Please upload and index your documents first in the Upload view.")
    else:
        subj  = st.session_state.subject_filter
        level = st.session_state.level
        with st.spinner("Scholar AI is thinking…"):
            mode_key, mode_model = get_api_key_and_model(st.session_state.mode)
            try:
                if st.session_state.mode == "explain":
                    answer, sources = answer_topic(global_query, level=level, subject=subj, model_name=mode_model, api_key=mode_key)
                elif st.session_state.mode == "exam":
                    answer, sources = solve_question(global_query, subject=subj, model_name=mode_model, api_key=mode_key)
                elif st.session_state.mode == "synthesize":
                    answer, sources = synthesize_topic(global_query, level=level, subject=subj, model_name=mode_model, api_key=mode_key)
                else:  # exam_map
                    answer, sources = map_topic_to_exam(global_query, subject=subj, model_name=mode_model, api_key=mode_key)
            except Exception as e:
                st.error(f"Failed to generate response: {str(e)}")
                st.stop()

        st.session_state.history.append({
            "q": global_query, "a": answer, "sources": sources,
            "mode": st.session_state.mode, "level": level,
        })
        if st.session_state.logged_in_user:
            sm.save_chat_history(st.session_state.logged_in_user, st.session_state.history)
        
        record_session(
            topic=global_query[:80],
            mode=st.session_state.mode,
            level=level,
            subject=subj,
        )
        
        # Reset input and view
        st.session_state.view = "chat"
        st.session_state.chat_input_key += 1
        st.rerun()