import os
import json
import hashlib
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import streamlit as st

# Check if Supabase credentials are provided
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    try:
        # Safely access st.secrets
        if hasattr(st, "secrets") and st.secrets:
            if "SUPABASE_URL" in st.secrets:
                SUPABASE_URL = st.secrets["SUPABASE_URL"]
            if "SUPABASE_KEY" in st.secrets:
                SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    except Exception:
        # Fallback if secrets.toml is missing or unconfigured
        pass

IS_SUPABASE_ACTIVE = bool(SUPABASE_URL and SUPABASE_KEY)


supabase_client = None
if IS_SUPABASE_ACTIVE:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        IS_SUPABASE_ACTIVE = False

# Local database file path
LOCAL_USERS_FILE = os.path.join("data", "users.json")

# ══════════════════════════════════════════════════════════════════════════════
#  CRYPTOGRAPHY HELPERS (For Local Mode)
# ══════════════════════════════════════════════════════════════════════════════
def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16).hex()
    pwd_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return pwd_hash, salt

def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest() == pwd_hash

def get_email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode('utf-8')).hexdigest()

def get_local_user_dir(email: str) -> str:
    email_hash = get_email_hash(email)
    user_dir = os.path.join("data", "user_data", email_hash)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL HELPERS (For Local Mode SMTP verification)
# ══════════════════════════════════════════════════════════════════════════════
def send_local_verification_email(email_to: str, code: str) -> bool:
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)
    
    if not all([smtp_server, smtp_port, smtp_user, smtp_password]):
        print(f"SMTP not configured. Verification code for {email_to}: {code}")
        # Store verification code in session for terminal fallback display
        st.session_state["local_otp_fallback"] = code
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_from
        msg['To'] = email_to
        msg['Subject'] = "Vidya AI - Email Verification Code"
        
        body = f"""Welcome to Vidya AI!
        
Your email verification code is: {code}
        
Please enter this code in the application to complete your registration.
"""
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, int(smtp_port))
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, email_to, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        st.session_state["local_otp_fallback"] = code
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  AUTHENTICATION APIS
# ══════════════════════════════════════════════════════════════════════════════
def sign_in(email: str, password: str) -> tuple[bool, str, str]:
    """
    Returns (success, user_id_or_email, error_message)
    """
    email = email.lower().strip()
    if IS_SUPABASE_ACTIVE:
        try:
            res = supabase_client.auth.sign_in_with_password({"email": email, "password": password})
            return True, res.user.id, ""
        except Exception as e:
            return False, "", str(e)
    else:
        # Local Mode
        if not os.path.exists(LOCAL_USERS_FILE):
            return False, "", "Invalid email or password."
        try:
            with open(LOCAL_USERS_FILE, "r") as f:
                users = json.load(f)
        except Exception:
            return False, "", "Database read error."
            
        if email not in users:
            return False, "", "Invalid email or password."
            
        user_record = users[email]
        if not user_record.get("is_verified", False):
            return False, "", "Email is not verified. Please register again."
            
        if verify_password(password, user_record["password_hash"], user_record["salt"]):
            return True, email, ""
        else:
            return False, "", "Invalid email or password."

def start_sign_up(email: str, password: str) -> tuple[bool, str]:
    """
    Step 1 of sign up. Triggers verification email.
    Returns (success, error_message_or_success_message)
    """
    email = email.lower().strip()
    if not email or "@" not in email:
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."

    if IS_SUPABASE_ACTIVE:
        try:
            # Supabase handles sign up and emails
            res = supabase_client.auth.sign_up({"email": email, "password": password})
            # If user is already created but not confirmed, it might succeed or error.
            return True, "Check your email for the verification link/code."
        except Exception as e:
            return False, str(e)
    else:
        # Local Mode
        os.makedirs("data", exist_ok=True)
        users = {}
        if os.path.exists(LOCAL_USERS_FILE):
            try:
                with open(LOCAL_USERS_FILE, "r") as f:
                    users = json.load(f)
            except Exception:
                pass
                
        if email in users and users[email].get("is_verified", False):
            return False, "User already exists with this email."
            
        # Generate 6-digit OTP code
        otp = f"{random.randint(100000, 999999)}"
        pwd_hash, salt = hash_password(password)
        
        users[email] = {
            "password_hash": pwd_hash,
            "salt": salt,
            "is_verified": False,
            "otp": otp
        }
        
        try:
            with open(LOCAL_USERS_FILE, "w") as f:
                json.dump(users, f, indent=2)
        except Exception as e:
            return False, f"Failed to write user data: {e}"
            
        sent = send_local_verification_email(email, otp)
        if sent:
            return True, "Verification email sent. Please enter the OTP to verify."
        else:
            return True, "Verification code generated (SMTP not configured. Read notice below)."

def verify_signup_otp(email: str, token: str) -> tuple[bool, str, str]:
    """
    Verifies OTP token.
    Returns (success, user_id_or_email, error_message)
    """
    email = email.lower().strip()
    token = token.strip()
    
    if IS_SUPABASE_ACTIVE:
        try:
            # Supabase verify OTP for signup
            res = supabase_client.auth.verify_otp({"email": email, "token": token, "type": "signup"})
            return True, res.user.id, ""
        except Exception as e:
            return False, "", str(e)
    else:
        # Local Mode
        if not os.path.exists(LOCAL_USERS_FILE):
            return False, "", "Registration not started."
        try:
            with open(LOCAL_USERS_FILE, "r") as f:
                users = json.load(f)
        except Exception:
            return False, "", "Database read error."
            
        if email not in users:
            return False, "", "Registration not started."
            
        user = users[email]
        if user.get("is_verified", False):
            return True, email, ""
            
        if user.get("otp") == token:
            user["is_verified"] = True
            user.pop("otp", None) # remove otp from record
            
            try:
                with open(LOCAL_USERS_FILE, "w") as f:
                    json.dump(users, f, indent=2)
                return True, email, ""
            except Exception as e:
                return False, "", f"Failed to save user verification: {e}"
        else:
            return False, "", "Invalid verification code. Please try again."

def start_password_reset(email: str) -> tuple[bool, str]:
    """
    Step 1 of password reset. Generates and sends OTP reset code.
    Returns (success, message_or_error)
    """
    email = email.lower().strip()
    if not email:
        return False, "Please enter your email address."

    if IS_SUPABASE_ACTIVE:
        try:
            # Send Supabase password reset email.
            supabase_client.auth.reset_password_for_email(email)
            return True, "Password reset email sent (via Supabase)."
        except Exception as e:
            return False, str(e)
    else:
        # Local Mode
        if not os.path.exists(LOCAL_USERS_FILE):
            return False, "User does not exist."
        try:
            with open(LOCAL_USERS_FILE, "r") as f:
                users = json.load(f)
        except Exception:
            return False, "Database read error."
            
        if email not in users:
            return False, "User with this email does not exist."
            
        # Generate 6-digit OTP code for reset
        otp = f"{random.randint(100000, 999999)}"
        users[email]["reset_otp"] = otp
        
        try:
            with open(LOCAL_USERS_FILE, "w") as f:
                json.dump(users, f, indent=2)
        except Exception as e:
            return False, f"Failed to save reset request: {e}"
            
        sent = send_local_verification_email(email, otp)
        if sent:
            return True, "Verification code sent to your email."
        else:
            return True, "Verification code generated (SMTP not configured. Read notice below)."

def complete_password_reset(email: str, token: str, new_password: str) -> tuple[bool, str]:
    """
    Step 2 of password reset. Verifies OTP code and updates password.
    Returns (success, message_or_error)
    """
    email = email.lower().strip()
    token = token.strip()
    if len(new_password) < 6:
        return False, "New password must be at least 6 characters long."
        
    if IS_SUPABASE_ACTIVE:
        try:
            # For Supabase, verify the recovery OTP token first
            res = supabase_client.auth.verify_otp({"email": email, "token": token, "type": "recovery"})
            # If successful, we have a session. Update the user password.
            supabase_client.auth.update_user({"password": new_password})
            return True, "Password reset successfully! You can now log in."
        except Exception as e:
            return False, str(e)
    else:
        # Local Mode
        if not os.path.exists(LOCAL_USERS_FILE):
            return False, "Database does not exist."
        try:
            with open(LOCAL_USERS_FILE, "r") as f:
                users = json.load(f)
        except Exception:
            return False, "Database read error."
            
        if email not in users:
            return False, "User does not exist."
            
        user = users[email]
        if "reset_otp" not in user or user["reset_otp"] != token:
            return False, "Invalid reset code. Please check and try again."
            
        # Update password
        pwd_hash, salt = hash_password(new_password)
        user["password_hash"] = pwd_hash
        user["salt"] = salt
        user.pop("reset_otp", None) # remove reset otp
        
        try:
            with open(LOCAL_USERS_FILE, "w") as f:
                json.dump(users, f, indent=2)
            return True, "Password reset successfully! You can now log in."
        except Exception as e:
            return False, f"Failed to save new password: {e}"

# ══════════════════════════════════════════════════════════════════════════════
#  USER DATA PERSISTENCE
# ══════════════════════════════════════════════════════════════════════════════
def save_chat_history(user_id: str, history: list):
    if IS_SUPABASE_ACTIVE:
        try:
            supabase_client.table("chat_history").upsert({
                "user_id": user_id,
                "history_json": history
            }).execute()
        except Exception as e:
            print(f"Error saving chat history to Supabase: {e}")
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        history_path = os.path.join(user_dir, "chat_history.json")
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving local chat history: {e}")

def load_chat_history(user_id: str) -> list:
    if IS_SUPABASE_ACTIVE:
        try:
            res = supabase_client.table("chat_history").select("history_json").eq("user_id", user_id).execute()
            if res.data:
                return res.data[0].get("history_json", [])
        except Exception as e:
            print(f"Error loading chat history from Supabase: {e}")
        return []
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        history_path = os.path.join(user_dir, "chat_history.json")
        if os.path.exists(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading local chat history: {e}")
        return []

def save_progress(user_id: str, progress_data: dict):
    if IS_SUPABASE_ACTIVE:
        try:
            supabase_client.table("progress").upsert({
                "user_id": user_id,
                "progress_json": progress_data
            }).execute()
        except Exception as e:
            print(f"Error saving progress to Supabase: {e}")
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        progress_path = os.path.join(user_dir, "progress.json")
        try:
            with open(progress_path, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving local progress: {e}")

def load_progress(user_id: str) -> dict:
    default_progress = {
        "sessions":    [],
        "quiz_results": [],
        "streak_days": [],
    }
    if IS_SUPABASE_ACTIVE:
        try:
            res = supabase_client.table("progress").select("progress_json").eq("user_id", user_id).execute()
            if res.data:
                return res.data[0].get("progress_json", default_progress)
        except Exception as e:
            print(f"Error loading progress from Supabase: {e}")
        return default_progress
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        progress_path = os.path.join(user_dir, "progress.json")
        if os.path.exists(progress_path):
            try:
                with open(progress_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading local progress: {e}")
        return default_progress

def save_api_settings(user_id: str, settings: dict):
    if IS_SUPABASE_ACTIVE:
        try:
            supabase_client.table("api_settings").upsert({
                "user_id": user_id,
                "settings_json": settings
            }).execute()
        except Exception as e:
            print(f"Error saving API settings to Supabase: {e}")
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        settings_path = os.path.join(user_dir, "api_settings.json")
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving local API settings: {e}")

def load_api_settings(user_id: str) -> dict:
    default_settings = {
        "default_api_key": "",
        "groq_api_key": "",
        "openrouter_api_key": "",
        "modes": {
            "explain": {"model": "gemini-2.5-flash", "api_key": ""},
            "exam": {"model": "gemini-2.5-pro", "api_key": ""},
            "synthesize": {"model": "gemini-2.5-pro", "api_key": ""},
            "exam_map": {"model": "gemini-2.5-flash", "api_key": ""},
            "learning_path": {"model": "gemini-2.5-flash", "api_key": ""},
            "qbank": {"model": "gemini-2.5-flash", "api_key": ""},
            "knowledge_graph": {"model": "gemini-2.5-flash", "api_key": ""},
        }
    }
    if IS_SUPABASE_ACTIVE:
        try:
            res = supabase_client.table("api_settings").select("settings_json").eq("user_id", user_id).execute()
            if res.data:
                # Merge loaded keys to default to keep structure intact
                loaded = res.data[0].get("settings_json", {})
                for k, v in loaded.items():
                    if k == "modes" and isinstance(v, dict):
                        for mk, mv in v.items():
                            if mk in default_settings["modes"]:
                                default_settings["modes"][mk].update(mv)
                    else:
                        default_settings[k] = v
        except Exception as e:
            print(f"Error loading API settings from Supabase: {e}")
        return default_settings
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        settings_path = os.path.join(user_dir, "api_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    for k, v in loaded.items():
                        if k == "modes" and isinstance(v, dict):
                            for mk, mv in v.items():
                                if mk in default_settings["modes"]:
                                    default_settings["modes"][mk].update(mv)
                        else:
                            default_settings[k] = v
            except Exception as e:
                print(f"Error loading local API settings: {e}")
        return default_settings

# ══════════════════════════════════════════════════════════════════════════════
#  VECTOR STORE STORAGE APIS (For FAISS Index files)
# ══════════════════════════════════════════════════════════════════════════════
def save_vector_store(user_id: str, chunks: list, metadata: list, faiss_index_filepath: str):
    """
    Saves vector chunks, metadata, and FAISS index file.
    faiss_index_filepath is the path to the temp .faiss file on disk that was just written.
    """
    if IS_SUPABASE_ACTIVE:
        try:
            # Upload chunks.json
            chunks_json = json.dumps(chunks, ensure_ascii=False, indent=2).encode('utf-8')
            supabase_client.storage.from_("vector_stores").upload(
                f"{user_id}/chunks.json",
                chunks_json,
                {"content-type": "application/json", "x-upsert": "true"}
            )
            # Upload metadata.json
            meta_json = json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf-8')
            supabase_client.storage.from_("vector_stores").upload(
                f"{user_id}/metadata.json",
                meta_json,
                {"content-type": "application/json", "x-upsert": "true"}
            )
            # Upload vector_store.faiss binary
            if os.path.exists(faiss_index_filepath):
                with open(faiss_index_filepath, "rb") as f:
                    file_data = f.read()
                supabase_client.storage.from_("vector_stores").upload(
                    f"{user_id}/vector_store.faiss",
                    file_data,
                    {"content-type": "application/octet-stream", "x-upsert": "true"}
                )
            print("Successfully uploaded vector store to Supabase storage.")
        except Exception as e:
            print(f"Error uploading vector store to Supabase: {e}")
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        local_chunks_path = os.path.join(user_dir, "vector_store_chunks.json")
        local_meta_path = os.path.join(user_dir, "vector_store_meta.json")
        local_faiss_path = os.path.join(user_dir, "vector_store.faiss")
        
        try:
            with open(local_chunks_path, "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)
            with open(local_meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            if os.path.exists(faiss_index_filepath):
                import shutil
                shutil.copyfile(faiss_index_filepath, local_faiss_path)
            print("Successfully saved vector store locally.")
        except Exception as e:
            print(f"Error saving local vector store: {e}")

def load_vector_store(user_id: str) -> tuple[list, list, str | None]:
    """
    Downloads/retrieves chunks, metadata, and returns a filepath to the .faiss index file.
    Returns (chunks, metadata, faiss_index_filepath)
    """
    if IS_SUPABASE_ACTIVE:
        user_dir = os.path.join("data", "temp_downloads", user_id)
        os.makedirs(user_dir, exist_ok=True)
        
        chunks = []
        metadata = []
        faiss_path = os.path.join(user_dir, "vector_store.faiss")
        
        try:
            # Download chunks.json
            try:
                chunks_data = supabase_client.storage.from_("vector_stores").download(f"{user_id}/chunks.json")
                chunks = json.loads(chunks_data.decode('utf-8'))
            except Exception:
                # Vector store doesn't exist yet
                return [], [], None
                
            # Download metadata.json
            try:
                meta_data = supabase_client.storage.from_("vector_stores").download(f"{user_id}/metadata.json")
                metadata = json.loads(meta_data.decode('utf-8'))
            except Exception:
                return [], [], None
                
            # Download vector_store.faiss
            try:
                faiss_data = supabase_client.storage.from_("vector_stores").download(f"{user_id}/vector_store.faiss")
                with open(faiss_path, "wb") as f:
                    f.write(faiss_data)
            except Exception:
                return [], [], None
                
            return chunks, metadata, faiss_path
        except Exception as e:
            print(f"Error downloading vector store from Supabase: {e}")
            return [], [], None
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        local_chunks_path = os.path.join(user_dir, "vector_store_chunks.json")
        local_meta_path = os.path.join(user_dir, "vector_store_meta.json")
        local_faiss_path = os.path.join(user_dir, "vector_store.faiss")
        
        if os.path.exists(local_chunks_path) and os.path.exists(local_meta_path) and os.path.exists(local_faiss_path):
            try:
                with open(local_chunks_path, "r", encoding="utf-8") as f:
                    chunks = json.load(f)
                with open(local_meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                return chunks, metadata, local_faiss_path
            except Exception as e:
                print(f"Error loading local vector store files: {e}")
        return [], [], None

def clear_vector_store_files(user_id: str):
    if IS_SUPABASE_ACTIVE:
        try:
            supabase_client.storage.from_("vector_stores").remove([
                f"{user_id}/chunks.json",
                f"{user_id}/metadata.json",
                f"{user_id}/vector_store.faiss"
            ])
            # Also clear the rows in tables
            supabase_client.table("chat_history").delete().eq("user_id", user_id).execute()
        except Exception as e:
            print(f"Error deleting cloud vector store: {e}")
    else:
        # Local Mode
        user_dir = get_local_user_dir(user_id)
        for name in ["vector_store_chunks.json", "vector_store_meta.json", "vector_store.faiss", "chat_history.json"]:
            path = os.path.join(user_dir, name)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"Error removing {path}: {e}")
