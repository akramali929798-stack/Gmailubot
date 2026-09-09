import imaplib
import email as email_lib
import requests
import time
import random
import string
import json
import os
import re
import threading
import sys
import io
import ssl
from datetime import datetime
import html
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
# ANSI color codes for colorful terminal output
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
MAGENTA= "\033[95m"
BLUE   = "\033[94m"
WHITE  = "\033[97m"
DIM    = "\033[2m"

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# Thread pool for concurrent OTP processing (capped to conserve Railway RAM)
executor = ThreadPoolExecutor(max_workers=20)
_start_time = time.time()  # process start — used for uptime / health check

# ==========================
# CONFIG
# ==========================
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "bot_token": "8698118717:AAEu-wE79_MKaAi5iH0QLlsE1ZlIf7I7cS8",
    "admin_ids": [5550493320, 576819773],
    "gmail_list": [],
    "imap_passwords": {},    "force_join": {"enabled": False, "channels": []},
    "auto_delete": {"user_seconds": 0, "group_seconds": 0},
    "otp_group": {"enabled": True, "link": "https://t.me/Gmail_otp_botx"},
    "group_bot": {
        "enabled": True,
        "token": "8698118717:AAEu-wE79_MKaAi5iH0QLlsE1ZlIf7I7cS8",
        "group_id": "-1003939455952",
        "send_all_mail": True
    },
    "blocked_users": [],
    "sheet_title": "Alias Bot Data",
    "ad_button": {
        "enabled": True,
        "text": "TG Sell Bot",
        "url": "https://t.me/Virtual_Nuumberr_bot?startapp=Kldt1HRF"
    }
}

_config = None

def _load_env_config():
    """Railway Environment Variables থেকে config তৈরি করে"""
    import copy
    cfg = copy.deepcopy(DEFAULT_CONFIG)

    # BOT_TOKEN env var
    env_token = os.environ.get("BOT_TOKEN", "").strip()
    if env_token:
        cfg["bot_token"] = env_token

    # ADMIN_IDS env var (comma separated: 576819773,123456)
    env_admins = os.environ.get("ADMIN_IDS", "").strip()
    if env_admins:
        try:
            cfg["admin_ids"] = [int(x.strip()) for x in env_admins.split(",") if x.strip()]
        except: pass

    # GMAIL_LIST env var (comma separated emails)
    env_gmails = os.environ.get("GMAIL_LIST", "").strip()
    if env_gmails:
        cfg["gmail_list"] = [x.strip() for x in env_gmails.split(",") if x.strip()]

    # IMAP_PASSWORDS env var (JSON string: {"email":"pass","email2":"pass2"})
    env_imap = os.environ.get("IMAP_PASSWORDS", "").strip()
    if env_imap:
        try:
            cfg["imap_passwords"] = json.loads(env_imap)
        except: pass

    # GROUP_ID env var
    env_group_id = os.environ.get("GROUP_ID", "").strip()
    if env_group_id:
        cfg["group_bot"]["group_id"] = env_group_id

    # GROUP_TOKEN env var (if different from main bot token)
    env_group_token = os.environ.get("GROUP_TOKEN", "").strip()
    if env_group_token:
        cfg["group_bot"]["token"] = env_group_token
    elif env_token:
        cfg["group_bot"]["token"] = env_token

    return cfg

def load_config():
    global _config
    if _config is not None:
        return _config

    # Railway / Cloud: Environment variable থেকে config নাও
    env_token = os.environ.get("BOT_TOKEN", "").strip()

    if not os.path.exists(CONFIG_FILE):
        if env_token:
            # Railway mode: env vars থেকে config তৈরি
            _config = _load_env_config()
            print(f"[Config] ✅ Environment variables থেকে config লোড হয়েছে")
            return _config
        else:
            _config = DEFAULT_CONFIG.copy()
            save_config(_config)
            return _config
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        # Env vars দিয়ে override করো (Railway এ সুবিধার জন্য)
        if env_token:
            cfg["bot_token"] = env_token
        env_admins = os.environ.get("ADMIN_IDS", "").strip()
        if env_admins:
            try:
                cfg["admin_ids"] = [int(x.strip()) for x in env_admins.split(",") if x.strip()]
            except: pass
        env_imap = os.environ.get("IMAP_PASSWORDS", "").strip()
        if env_imap:
            try:
                cfg["imap_passwords"] = json.loads(env_imap)
            except: pass
        env_group_id = os.environ.get("GROUP_ID", "").strip()
        if env_group_id and "group_bot" in cfg:
            cfg["group_bot"]["group_id"] = env_group_id
        for key, val in DEFAULT_CONFIG.items():
            if key not in cfg:
                cfg[key] = val
        if "group_bot" in cfg:
            for k, v in DEFAULT_CONFIG["group_bot"].items():
                if k not in cfg["group_bot"]:
                    cfg["group_bot"][k] = v
        if "ad_button" in cfg:
            for k, v in DEFAULT_CONFIG["ad_button"].items():
                if k not in cfg["ad_button"]:
                    cfg["ad_button"][k] = v
        _config = cfg
        return _config
    except:
        if env_token:
            _config = _load_env_config()
            return _config
        return DEFAULT_CONFIG

def save_config(cfg):
    global _config
    _config = cfg
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ==========================
# LOCAL DATA STORAGE
# ==========================

# In-memory cache — alias/tag data local এ থাকে
_cache     = {}  # chat_id(str) -> {tag, email, tag_history, username, full_name, ...}
_tag_index = {}  # tag.lower() -> chat_id(str)

# Local JSON files
ALIAS_FILE = "alias_data.json"   # chat_id -> {tag, email, tag_history, username, full_name, joined_at}

def _load_alias_file():
    if not os.path.exists(ALIAS_FILE): return {}
    with open(ALIAS_FILE) as f: return json.load(f)

def _save_alias_file(data):
    with open(ALIAS_FILE, "w") as f: json.dump(data, f, indent=2)

def load_cache():
    """Local alias file থেকে memory তে load করে"""
    global _cache, _tag_index
    _cache = {}
    _tag_index = {}
    try:
        alias_data = _load_alias_file()
        for cid, adata in alias_data.items():
            _cache[cid] = {
                "chat_id":     cid,
                "username":    adata.get("username", ""),
                "full_name":   adata.get("full_name", ""),
                "joined_at":   adata.get("joined_at", ""),
                "tag":         adata.get("tag", ""),
                "email":       adata.get("email", ""),
                "tag_history": adata.get("tag_history", []),
                "row":         None
            }
            for t in adata.get("tag_history", []):
                _tag_index[t.lower()] = cid
            if adata.get("tag"):
                _tag_index[adata["tag"].lower()] = cid
        print(f"{GREEN}{BOLD}✅ Cache loaded:{RESET} {WHITE}{len(_cache)} users{RESET}")
    except Exception as e:
        print(f"{RED}[Cache load] {e}{RESET}")

def save_alias_local(cid):
    """Alias + user data local file এ save করে"""
    data = _cache.get(str(cid), {})
    alias_data = _load_alias_file()
    alias_data[str(cid)] = {
        "tag":         data.get("tag", ""),
        "email":       data.get("email", ""),
        "tag_history": data.get("tag_history", []),
        "username":    data.get("username", ""),
        "full_name":   data.get("full_name", ""),
        "joined_at":   data.get("joined_at", "")
    }
    _save_alias_file(alias_data)

def register_user(chat_id, username, full_name):
    """User প্রথমবার /start দিলে local file এ save করে। Returns True if new user."""
    cid = str(chat_id)
    if cid in _cache:
        return False  # already registered
    joined_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "chat_id":     cid,
        "username":    username,
        "full_name":   full_name,
        "joined_at":   joined_at,
        "tag":         "",
        "email":       "",
        "tag_history": [],
        "row":         None
    }
    _cache[cid] = data
    # Background: local file এ save করো
    threading.Thread(target=lambda: save_alias_local(cid), daemon=True).start()
    return True  # new user

def get_user_data(chat_id):
    return _cache.get(str(chat_id))

def update_user_alias(chat_id, tag, email):
    """User এর alias update করে cache + local file এ (sheet এ না)"""
    cid  = str(chat_id)
    data = _cache.get(cid, {})
    history = data.get("tag_history", [])
    if tag.lower() not in [t.lower() for t in history]:
        history.append(tag)
    history = history[-10:]
    data["tag"]         = tag
    data["email"]       = email
    data["tag_history"] = history
    _cache[cid] = data
    _tag_index[tag.lower()] = cid
    # Local file এ save (background)
    threading.Thread(target=lambda: save_alias_local(cid), daemon=True).start()

def find_user_by_tag(tag):
    """tag থেকে chat_id বের করো — O(1) memory lookup"""
    cid = _tag_index.get(tag.lower())
    if cid:
        try: return int(cid)
        except: pass
    return None

def get_all_users():
    return list(_cache.values())

# ==========================
# TELEGRAM
# ==========================
def get_bot_token():
    return load_config().get("bot_token", "")

last_update_id = 0
_processed_updates = set()
_user_locks = {}

def get_user_lock(chat_id):
    if chat_id not in _user_locks:
        _user_locks[chat_id] = threading.Lock()
    return _user_locks[chat_id]

_session = requests.Session()
# Retry adapter: retry on connection errors and 5xx, with backoff
_retry_adapter = HTTPAdapter(
    max_retries=Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
)
_session.mount("https://", _retry_adapter)
_session.mount("http://",  _retry_adapter)

def api(method, payload=None, params=None):
    token = get_bot_token()
    if not token: return {}
    url = f"https://api.telegram.org/bot{token}/{method}"
    for attempt in range(4):
        try:
            if payload:
                r = _session.post(url, json=payload, timeout=25)
            else:
                # timeout parameter in params is for server-side long polling.
                # we set requests timeout slightly higher (40s) than the 30s long poll.
                r = _session.get(url, params=params, timeout=40)
            return r.json()
        except Exception as e:
            wait = 2 ** attempt  # 1, 2, 4, 8 seconds
            print(f"{RED}[API] {e} — retry in {wait}s{RESET}")
            time.sleep(wait)
    return {}

def send_msg(chat_id, text, markup=None, parse_mode="HTML"):
    p = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if markup: p["reply_markup"] = markup
    return api("sendMessage", p)

def send_photo(chat_id, photo, caption=None, markup=None, parse_mode="HTML"):
    p = {"chat_id": chat_id, "photo": photo, "parse_mode": parse_mode}
    if caption: p["caption"] = caption
    if markup: p["reply_markup"] = markup
    return api("sendPhoto", p)

def edit_msg(chat_id, msg_id, text, markup=None, parse_mode="HTML"):
    p = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": parse_mode}
    if markup: p["reply_markup"] = markup
    return api("editMessageText", p)

def answer_cb(cb_id, text="", alert=False):
    api("answerCallbackQuery", {"callback_query_id": cb_id, "text": text, "show_alert": alert})

def delete_msg(chat_id, msg_id):
    api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})

def update_telegram_menu_button():
    menu_btn = {"type": "default"}
    r = api("setChatMenuButton", {"menu_button": menu_btn})
    return r

# ==========================
# ALIAS SYSTEM
# ==========================
def generate_tag():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def get_user_base_email(chat_id):
    cfg  = load_config()
    data = get_user_data(chat_id)
    if data and data.get("email") and data["email"] in cfg["gmail_list"]:
        return data["email"]
    if not cfg["gmail_list"]: return None
    chosen = random.choice(cfg["gmail_list"])
    return chosen

def randomize_local(local):
    """gmail local part এর case random করে — প্রতিবার আলাদা দেখাবে"""
    return ''.join(c.upper() if random.choice([True, False]) else c.lower() for c in local)

def get_or_create_alias(chat_id):
    data = get_user_data(chat_id)
    if data and data.get("tag") and data.get("email"):
        local, domain = data["email"].split("@")
        return f"{randomize_local(local)}+{data['tag']}@{domain}"
    # নতুন alias তৈরি করো
    base_email = get_user_base_email(chat_id)
    if not base_email: return None
    tag = generate_tag()
    update_user_alias(chat_id, tag, base_email)
    local, domain = base_email.split("@")
    return f"{randomize_local(local)}+{tag}@{domain}"

def regenerate_alias(chat_id, new_base_email=None):
    cfg  = load_config()
    if not new_base_email:
        gmails = cfg.get("gmail_list", [])
        new_base_email = random.choice(gmails) if gmails else get_user_base_email(chat_id)
    if not new_base_email or "@" not in str(new_base_email):
        return None
    tag = generate_tag()
    update_user_alias(chat_id, tag, new_base_email)
    local, domain = new_base_email.split("@")
    return f"{randomize_local(local)}+{tag}@{domain}"

# user alias message_id — local dict (in-memory only, no need to persist)
_alias_msg_ids = {}  # chat_id -> message_id

def alias_keyboard(alias):
    cfg = load_config()
    kb  = [
        [{"text": alias, "copy_text": {"text": alias}}],
        [{"text": "🔄 Refresh", "callback_data": "refresh_alias"},
         {"text": "🔀 Change",  "callback_data": "next_alias"}]
    ]
    
    ad = cfg.get("ad_button", {})
    if ad.get("enabled") and ad.get("url"):
        kb.append([{"text": ad.get("text", "TG Sell Bot"), "url": ad.get("url")}])

    if cfg["otp_group"]["enabled"]:
        kb.append([{"text": "📨 OTP GROUP", "url": cfg["otp_group"]["link"]}])
    return {"inline_keyboard": kb}

def send_alias(chat_id):
    alias = get_or_create_alias(chat_id)
    if not alias:
        send_msg(chat_id, "⚠️ কোনো Gmail পাওয়া যায়নি।"); return
    old_id = _alias_msg_ids.get(chat_id)
    if old_id:
        res = edit_msg(chat_id, old_id,
                       "নিচের বাটনে ক্লিক করলেই copy হয়ে যাবে 👇",
                       markup=alias_keyboard(alias))
        if res.get("ok"): return
        _alias_msg_ids.pop(chat_id, None)
    res = send_msg(chat_id,
                   "নিচের বাটনে ক্লিক করলেই copy হয়ে যাবে 👇",
                   markup=alias_keyboard(alias))
    if res.get("ok"):
        _alias_msg_ids[chat_id] = res["result"]["message_id"]

def send_alias_new(chat_id):
    """প্রতিবার /start এ সম্পূর্ণ নতুন message পাঠায়, নতুন alias সহ"""
    cfg    = load_config()
    gmails = cfg.get("gmail_list", [])
    new_base = random.choice(gmails) if gmails else None
    alias = regenerate_alias(chat_id, new_base_email=new_base)
    if not alias:
        send_msg(chat_id, "⚠️ কোনো Gmail পাওয়া যায়নি।"); return
    res = send_msg(chat_id,
                   "নিচের বাটনে ক্লিক করলেই copy হয়ে যাবে 👇",
                   markup=alias_keyboard(alias))
    if res.get("ok"):
        _alias_msg_ids[chat_id] = res["result"]["message_id"]

def change_alias(chat_id, msg_id):
    cfg    = load_config()
    gmails = cfg.get("gmail_list", [])
    new_base = random.choice(gmails) if gmails else None
    alias  = regenerate_alias(chat_id, new_base_email=new_base)
    _alias_msg_ids[chat_id] = msg_id
    edit_msg(chat_id, msg_id,
             "নিচের বাটনে ক্লিক করলেই copy হয়ে যাবে 👇",
             markup=alias_keyboard(alias))

# ==========================
# OTP
# ==========================
def extract_otp(text):
    m = re.search(r"\b\d{4,8}\b", text)
    return m.group() if m else None

def extract_tag(to_field):
    m = re.search(r'\+([^@\s]+)@', to_field)
    return m.group(1) if m else None

_sent_otps = {}  # chat_id -> {otp: timestamp}

def is_duplicate_otp(chat_id, otp):
    key = str(chat_id)
    now = time.time()
    if key not in _sent_otps: _sent_otps[key] = {}
    _sent_otps[key] = {k: v for k, v in _sent_otps[key].items() if now - v < 60}
    if otp in _sent_otps[key]: return True
    _sent_otps[key][otp] = now
    return False

def parse_time_input(text):
    """M1 -> 60, S35 -> 35, 0 -> disabled"""
    text = text.strip().upper()
    if text.startswith("M"):
        try: return int(text[1:]) * 60
        except: return 0
    elif text.startswith("S"):
        try: return int(text[1:])
        except: return 0
    return 0

def auto_delete_msg(token, chat_id, msg_id, after_seconds):
    """নির্দিষ্ট সময় পরে message delete করে"""
    def _delete():
        time.sleep(after_seconds)
        try:
            if token:
                # Group bot এর message
                _session.post(
                    f"https://api.telegram.org/bot{token}/deleteMessage",
                    json={"chat_id": chat_id, "message_id": msg_id},
                    timeout=15
                )
            else:
                # Main bot এর message
                api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        except: pass
    threading.Thread(target=_delete, daemon=True).start()

def send_otp_to_user(chat_id, otp, tag=None, service="OTP"):
    if is_duplicate_otp(chat_id, otp): return
    tag_esc = html.escape(tag) if tag else ""
    tag_line = f" {tag_esc}" if tag else ""
    res = send_msg(
        chat_id,
        f"📨 <b>New {service}</b>{tag_line}\n\n🔐 <b>Code:</b> <code>{html.escape(otp)}</code>",
        markup={"inline_keyboard": [[
            {"text": f"🔑 {otp}", "copy_text": {"text": otp}}
        ]]}
    )
    # Auto delete
    cfg = load_config()
    secs = cfg.get("auto_delete", {}).get("user_seconds", 0)
    if secs and res.get("ok"):
        auto_delete_msg(None, chat_id, res["result"]["message_id"], secs)

# ==========================
# GROUP BOT
# Telegram Quote format = HTML <blockquote>
# ==========================
def send_mail_to_group(subject, from_, to_, body, otp=None, tag=None):
    cfg = load_config()
    gb  = cfg.get("group_bot", {})
    if not gb.get("enabled") or not gb.get("token") or not gb.get("group_id"):
        return
    if not otp and not gb.get("send_all_mail", True):
        return

    try: group_id = int(gb["group_id"])
    except: group_id = gb["group_id"]
    token = gb["token"]

    if otp:
        tag_esc = html.escape(tag) if tag else ""
        tag_line = f" {tag_esc}" if tag else ""
        text = f"📨 <b>New OTP</b>{tag_line}\n\n🔐 <b>Code:</b> <code>{html.escape(otp)}</code>"
        markup = {"inline_keyboard": [[
            {"text": f"🔑 {otp}", "copy_text": {"text": otp}}
        ]]}
    else:
        # from_ থেকে শুধু নাম বের করো
        from_name = re.sub(r'<[^>]+>', '', from_).strip().strip('"').strip("'") or from_

        # Body পরিষ্কার করো
        body_clean = body.strip().replace("\r\n", "\n").replace("\r", "\n")
        # খালি lines কমাও
        body_clean = re.sub(r'\n{3,}', '\n\n', body_clean)

        # HTML escaping
        subject_esc = html.escape(subject)
        from_name_esc = html.escape(from_name)
        body_esc = html.escape(body_clean[:2000])
        tag_esc = html.escape(tag) if tag else ""
        
        tag_line = f"\nTag: {tag_esc}" if tag else ""

        # Quote block — Telegram HTML blockquote
        quote_content = (
            f"Subject: {subject_esc}"
            f"{tag_line}"
            f"\nFrom: {from_name_esc}"
        )

        # Message = header + blockquote + full body
        text = (
            f"📧 <b>New Mail</b>\n\n"
            f"<blockquote>{quote_content}</blockquote>"
        )
        if body_clean:
            text += f"\n\n{body_esc}"

        markup = None

    for attempt in range(4):
        try:
            payload = {
                "chat_id": group_id,
                "text": text,
                "parse_mode": "HTML",
            }
            if markup:
                payload["reply_markup"] = markup
            r = _session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=25
            ).json()
            if not r.get("ok"):
                desc = r.get('description', '')
                if "chat not found" in desc or "bot was kicked" in desc:
                    # Group ID wrong or bot not in group — log once, skip silently
                    print(f"{YELLOW}[{_ts()}][Group] Not in group or wrong ID: {desc}{RESET}")
                else:
                    print(f"{RED}[{_ts()}][Group-ERR] {desc}{RESET}")
                return
            # Auto delete group message
            cfg2  = load_config()
            gsecs = cfg2.get("auto_delete", {}).get("group_seconds", 0)
            if gsecs and r.get("result"):
                auto_delete_msg(token, group_id, r["result"]["message_id"], gsecs)
            return  # success — exit retry loop
        except Exception as e:
            wait = 2 ** attempt  # 1, 2, 4, 8 seconds
            print(f"{RED}[Group bot Exception] {e} — retry in {wait}s{RESET}")
            time.sleep(wait)

def _ts():
    """Current time prefix for log lines."""
    return datetime.now().strftime("%H:%M:%S")

def _decode_subject(subject):
    """RFC 2047 encoded subject (e.g. =?UTF-8?B?...?=) কে plain text এ convert করে."""
    try:
        from email.header import decode_header
        parts = decode_header(subject)
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(enc or "utf-8", errors="ignore"))
            else:
                decoded.append(str(part))
        return "".join(decoded)
    except Exception:
        return subject

def process_and_send_email(raw_email, base_email):
    try:
        msg     = email_lib.message_from_bytes(raw_email)
        from_   = msg.get("from", "").lower()
        to_     = msg.get("to", "")
        subject = _decode_subject(msg.get("subject", ""))   # RFC 2047 decode
        body    = ""

        # Extract body — prefer text/plain, fall back to any decodable part
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break
            if not body:  # fallback: first decodable part
                for part in msg.walk():
                    try:
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        if body: break
                    except Exception:
                        continue
        else:
            try:
                body = msg.get_payload(decode=True).decode(errors="ignore")
            except Exception:
                body = str(msg.get_payload())

        otp = extract_otp(subject + "\n" + body)
        tag = extract_tag(to_)

        subject_short = subject[:60]
        print(f"{CYAN}[{_ts()}][MAIL] {base_email} | from={from_[:40]} | tag={tag} | otp={otp} | subj={subject_short}{RESET}")

        # ── Route OTP to user ──────────────────────────────────────────
        if otp and tag:
            user = find_user_by_tag(tag)
            if user:
                # Detect service name from sender / subject
                if "telegram.org" in from_:
                    service = "Telegram OTP"
                elif "otp-noreply" in from_ or "imo" in from_ or "imo" in subject.lower():
                    service = "IMO OTP"
                elif "whatsapp" in from_ or "whatsapp" in subject.lower():
                    service = "WhatsApp OTP"
                elif "google" in from_:
                    service = "Google OTP"
                elif "facebook" in from_ or "instagram" in from_:
                    service = "Meta OTP"
                elif "amazon" in from_ or "aws" in from_:
                    service = "Amazon OTP"
                else:
                    service = "OTP"
                send_otp_to_user(user, otp, tag=tag, service=service)
                print(f"{GREEN}[{_ts()}][OTP-SENT] {service} otp={otp} tag={tag} uid={user}{RESET}")
            else:
                print(f"{YELLOW}[{_ts()}][OTP-NO-USER] tag={tag} otp={otp} — no user found{RESET}")

        # ── Send full mail to group (always) ───────────────────────────
        send_mail_to_group(subject, from_, to_, body, otp=otp, tag=tag)

    except Exception as e:
        print(f"{RED}[{_ts()}][MAIL-ERR] {base_email}: {e}{RESET}")

# ==========================
# PROCESS UNSEEN EMAILS  (UID-based — never misses a message)
# ==========================
def process_unseen(mail_conn, base_email):
    """
    Fetch all new messages with UID > _last_uid[base_email].
    Using UID commands avoids sequence-number renumbering bugs that
    cause OTP misses after expunge / reconnect.
    """
    try:
        mail_conn.select("inbox")
        last_uid = _last_uid.get(base_email, 0)

        # UID SEARCH: only messages strictly newer than our watermark
        status, data = mail_conn.uid("search", None, f"UID {last_uid + 1}:*")
        if status != "OK" or not data or not data[0]:
            return

        uid_list = [u for u in data[0].split() if u]
        if not uid_list:
            return

        # Filter sentinel: Gmail returns the last UID even when there's nothing new
        new_uids = []
        for u in uid_list:
            try:
                uid_int = int(u)
                if uid_int > last_uid:
                    new_uids.append(u)
            except ValueError:
                continue

        if not new_uids:
            return

        print(f"{CYAN}[{_ts()}][IMAP] {base_email} — {len(new_uids)} new message(s){RESET}")

        for uid in new_uids:
            try:
                st2, raw_data = mail_conn.uid("fetch", uid, "(RFC822)")
                if st2 != "OK" or not raw_data or raw_data[0] is None:
                    print(f"{YELLOW}[{_ts()}][IMAP-FETCH] uid={uid} failed: {st2}{RESET}")
                    continue

                raw_email = raw_data[0][1]
                executor.submit(process_and_send_email, raw_email, base_email)

                # Advance watermark only after successful submit
                uid_int = int(uid)
                if uid_int > _last_uid.get(base_email, 0):
                    _last_uid[base_email] = uid_int
                mail_conn.uid("store", uid, "+FLAGS", "\\Seen")

            except Exception as fetch_e:
                # Log but keep going — don't advance watermark so we retry next cycle
                print(f"{RED}[{_ts()}][IMAP-FETCH-ERR] uid={uid} {base_email}: {fetch_e}{RESET}")

    except imaplib.IMAP4.abort:
        raise   # propagate connection errors to trigger reconnect
    except Exception as e:
        print(f"{YELLOW}[{_ts()}][IMAP-SEARCH-ERR] {base_email}: {e}{RESET}")

# ==========================
# IMAP THREAD
# ==========================
# Per-email highest processed UID.
# Persists across reconnects — no mail is re-sent, no mail is missed.
_last_uid    = {}   # base_email → int  (last UID submitted to executor)
_imap_status = {}   # base_email → str  ("idle" | "poll" | "connecting" | "error")

def imap_thread(base_email, app_password):
    """Fully resilient IMAP thread: IDLE push with poll fallback.
    - Never exits due to exceptions.
    - Reconnects with exponential backoff (max 60 s).
    - UID-based tracking ensures no OTP missed across reconnects.
    """
    IDLE_TIMEOUT  = 20   # seconds per IDLE wait before re-issuing
    POLL_INTERVAL = 5    # seconds between polls in fallback mode
    NOOP_EVERY    = 60   # poll iterations between NOOP keep-alives
    reconnect_delay = 5

    import socket as _socket

    # Permissive SSL — avoids _ssl.c EOF errors on Railway
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode    = ssl.CERT_NONE

    while True:   # ── outer reconnect loop ──────────────────────────────
        mail = None
        _imap_status[base_email] = "connecting"
        try:
            print(f"{CYAN}[{_ts()}][IMAP] Connecting {base_email}...{RESET}")
            mail = imaplib.IMAP4_SSL("imap.gmail.com", ssl_context=_ssl_ctx)
            mail.login(base_email, app_password)
            mail.select("inbox")
            reconnect_delay = 5   # reset backoff on successful connect

            # ── Watermark: record current highest UID on first connect ──
            # On reconnect _last_uid already has the last processed UID,
            # so we resume exactly where we left off: no duplicates, no gaps.
            if base_email not in _last_uid:
                try:
                    st, msgs = mail.uid("search", None, "ALL")
                    if st == "OK" and msgs[0].strip():
                        _last_uid[base_email] = int(msgs[0].split()[-1])
                    else:
                        _last_uid[base_email] = 0
                    print(f"{GREEN}[{_ts()}][IMAP] {base_email} watermark uid={_last_uid[base_email]}{RESET}")
                except Exception as wm_e:
                    _last_uid[base_email] = 0
                    print(f"{YELLOW}[{_ts()}][IMAP] watermark failed {base_email}: {wm_e}{RESET}")

            # ── Choose mode ────────────────────────────────────────────
            caps     = mail.capabilities
            use_idle = caps and b"IDLE" in caps

            if use_idle:
                _imap_status[base_email] = "idle"
                print(f"{GREEN}[{_ts()}][IMAP-IDLE] {base_email}{RESET}")

                while True:   # ── inner IDLE loop ──────────────────────
                    try:
                        tag_b = mail._new_tag()
                        mail.send(tag_b + b" IDLE\r\n")
                        mail.readline()   # "+ idling" continuation

                        # Wait for server push (EXISTS / EXPUNGE / BYE)
                        mail.socket().settimeout(IDLE_TIMEOUT)
                        try:
                            _line = mail.readline()
                        except (_socket.timeout, TimeoutError, OSError):
                            _line = b""
                        finally:
                            mail.socket().settimeout(None)

                        # Terminate IDLE
                        try:
                            mail.send(b"DONE\r\n")
                            mail.readline()   # drain tagged OK
                        except Exception:
                            pass

                        mail.select("inbox")
                        process_unseen(mail, base_email)

                    except (OSError, EOFError, imaplib.IMAP4.abort) as e:
                        print(f"{YELLOW}[{_ts()}][IDLE-ERR] {base_email}: {e} — reconnecting{RESET}")
                        break
                    except Exception as e:
                        print(f"{YELLOW}[{_ts()}][IDLE-ERR] {base_email}: {e} — reconnecting{RESET}")
                        break

            else:
                _imap_status[base_email] = "poll"
                print(f"{YELLOW}[{_ts()}][IMAP-POLL] {base_email} (no IDLE support){RESET}")
                noop_counter = 0

                while True:   # ── inner POLL loop ──────────────────────
                    time.sleep(POLL_INTERVAL)
                    noop_counter += 1
                    try:
                        mail.select("inbox")
                        process_unseen(mail, base_email)
                    except (OSError, EOFError, imaplib.IMAP4.abort) as e:
                        print(f"{YELLOW}[{_ts()}][POLL-ERR] {base_email}: {e} — reconnecting{RESET}")
                        break
                    except Exception as e:
                        # Non-fatal: log and keep polling
                        print(f"{YELLOW}[{_ts()}][POLL-WARN] {base_email}: {e}{RESET}")

                    if noop_counter >= NOOP_EVERY:
                        try:
                            mail.noop()
                            noop_counter = 0
                        except Exception as e:
                            print(f"{YELLOW}[{_ts()}][NOOP-FAIL] {base_email}: {e} — reconnecting{RESET}")
                            break

        except imaplib.IMAP4.error as e:
            _imap_status[base_email] = "error"
            print(f"{RED}[{_ts()}][IMAP-LOGIN-ERR] {base_email}: {e}{RESET}")
        except (OSError, EOFError) as e:
            _imap_status[base_email] = "error"
            print(f"{RED}[{_ts()}][IMAP-NET-ERR] {base_email}: {e}{RESET}")
        except Exception as e:
            _imap_status[base_email] = "error"
            print(f"{RED}[{_ts()}][IMAP-ERR] {base_email}: {e}{RESET}")
        finally:
            if mail:
                try: mail.logout()
                except: pass
            mail = None

        print(f"{YELLOW}[{_ts()}][IMAP] {base_email} — reconnect in {reconnect_delay}s...{RESET}")
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 60)   # cap at 60 s



# ==========================
# FORCE JOIN
# ==========================
def check_joined(chat_id):
    cfg = load_config()
    if not cfg["force_join"]["enabled"]: return True, []
    missing = []
    for ch in cfg["force_join"]["channels"]:
        try:
            part = ch["link"].strip().rstrip("/").split("t.me/")[-1]
            if part.startswith("+"): continue
            r = api("getChatMember", {"chat_id": "@"+part, "user_id": chat_id})
            if r.get("result",{}).get("status","left") in ["left","kicked"]:
                missing.append(ch)
        except: missing.append(ch)
    return len(missing)==0, missing

def send_force_join(chat_id, channels):
    btns = [[{"text": f"👉 {ch.get('name','Join')}", "url": ch["link"]}] for ch in channels]
    btns.append([{"text": "✅ Join করেছি, চেক করুন", "callback_data": "check_join"}])
    send_msg(chat_id, "🔒 Bot ব্যবহার করতে নিচের Channel/Group এ Join করুন:",
             markup={"inline_keyboard": btns})

# ==========================
# PENDING STATE  (in-memory + async file backup)
# ==========================
PENDING_FILE  = "pending.json"
_pending      = {}                # in-memory store — zero disk hit per request
_pending_lock = threading.Lock()

def _load_pending_from_file():
    """Startup: restore pending state from disk."""
    global _pending
    if not os.path.exists(PENDING_FILE):
        return
    try:
        with open(PENDING_FILE) as f:
            _pending = json.load(f)
    except Exception:
        _pending = {}

def _flush_pending():
    """Background: persist current pending state to disk."""
    try:
        with _pending_lock:
            snapshot = dict(_pending)
        with open(PENDING_FILE, "w") as f:
            json.dump(snapshot, f)
    except Exception:
        pass

def set_pending(chat_id, action, mid=None, extra=None):
    with _pending_lock:
        _pending[str(chat_id)] = {"action": action, "panel_msg_id": mid, "extra": extra}
    threading.Thread(target=_flush_pending, daemon=True).start()

def get_pending(chat_id):
    with _pending_lock:
        val = _pending.get(str(chat_id))
    if not val: return None, None, None
    if isinstance(val, dict):
        return val.get("action"), val.get("panel_msg_id"), val.get("extra")
    return val, None, None

def clear_pending(chat_id):
    with _pending_lock:
        _pending.pop(str(chat_id), None)
    threading.Thread(target=_flush_pending, daemon=True).start()

# ==========================
# ADMIN PANEL
# ==========================
def is_admin(chat_id):
    return chat_id in load_config()["admin_ids"]

def admin_panel(chat_id, msg_id=None):
    cfg = load_config()
    fj  = "✅" if cfg["force_join"]["enabled"]                       else "❌"
    og  = "✅" if cfg["otp_group"]["enabled"]                        else "❌"
    gb  = "✅" if cfg.get("group_bot",{}).get("enabled")             else "❌"
    gm  = "✅" if cfg.get("group_bot",{}).get("send_all_mail", True) else "❌"
    total = len(_cache)
    ad    = cfg.get("auto_delete", {})
    ud    = ad.get("user_seconds", 0)
    gd    = ad.get("group_seconds", 0)
    ud_txt = f"{ud}s" if ud else "Off"
    gd_txt = f"{gd}s" if gd else "Off"
    ad_btn = cfg.get("ad_button", {"enabled": False, "text": "🚀 Open App", "url": ""})
    ad_status = "✅" if ad_btn.get("enabled") else "❌"
    ad_text = ad_btn.get("text", "🚀 Open App")
    ad_url = ad_btn.get("url", "")

    txt = (
        f"⚙️ <b>Admin Panel</b>\n\n"
        f"📧 Gmail: <code>{len(cfg['gmail_list'])}</code>\n"
        f"👥 Users: <code>{total}</code>\n"
        f"🔒 Force Join: {fj}\n"
        f"💬 OTP Group Button: {og}\n"
        f"🤖 Group Bot: {gb}\n"
        f"📧 Group All Mail: {gm}\n"
        f"⏱ User OTP Delete: <code>{ud_txt}</code>\n"
        f"⏱ Group OTP Delete: <code>{gd_txt}</code>\n"
        f"🚫 Blocked: <code>{len(cfg['blocked_users'])}</code>\n\n"
        f"📢 Ad Button: {ad_status}\n"
        f"✍️ Ad Text: <code>{html.escape(ad_text)}</code>\n"
        f"🔗 Ad Link: <code>{html.escape(ad_url)}</code>"
    )
    kb = {"inline_keyboard": [
        [{"text": "➕ Gmail যোগ",        "callback_data": "adm_add_gmail"},
         {"text": "🗑 Gmail মুছুন",      "callback_data": "adm_del_gmail"}],
        [{"text": f"🔒 Force Join {fj}", "callback_data": "adm_toggle_fj"},
         {"text": "➕ Channel যোগ",      "callback_data": "adm_add_ch"}],
        [{"text": "🗑 Channel মুছুন",    "callback_data": "adm_del_ch"},
         {"text": f"💬 OTP Button {og}", "callback_data": "adm_toggle_otp"}],
        [{"text": "🔗 OTP Link",         "callback_data": "adm_otp_link"}],
        [{"text": f"🤖 Group Bot {gb}",  "callback_data": "adm_group_bot"},
         {"text": f"📧 All Mail {gm}",   "callback_data": "adm_toggle_group_mail"}],
        [{"text": "📢 Broadcast",        "callback_data": "adm_broadcast"},
         {"text": "📊 Statistics",       "callback_data": "adm_stats"}],
        [{"text": "⏱ User OTP Delete",  "callback_data": "adm_del_user"},
         {"text": "⏱ Group OTP Delete", "callback_data": "adm_del_group"}],
        [{"text": "🚫 Block",            "callback_data": "adm_block"},
         {"text": "✅ Unblock",          "callback_data": "adm_unblock"}],
        [{"text": "👥 User List",        "callback_data": "adm_users"},
         {"text": "🔑 Sheet Title",      "callback_data": "adm_sheet_title"}],
        [{"text": f"📢 Ad Button {ad_status}", "callback_data": "adm_toggle_ad"},
         {"text": "✍️ Ad Text",         "callback_data": "adm_ad_text"}],
        [{"text": "🔗 Ad Link",         "callback_data": "adm_ad_link"}]
    ]}
    if msg_id:
        edit_msg(chat_id, msg_id, txt, markup=kb)
    else:
        send_msg(chat_id, txt, markup=kb)

# ==========================
# PENDING HANDLER
# ==========================
def process_pending(chat_id, text, msg=None):
    action, pmid, extra = get_pending(chat_id)
    if not action: return False
    cfg = load_config()
    clear_pending(chat_id)

    if action == "add_gmail":
        ei = text.strip()
        if "@" not in ei:
            send_msg(chat_id, "❌ সঠিক Gmail দিন।")
        elif ei in cfg["gmail_list"]:
            send_msg(chat_id, f"⚠️ <code>{ei}</code> আগে থেকেই আছে।")
        else:
            set_pending(chat_id, f"add_gmail_pass:{ei}", pmid)
            send_msg(chat_id, f"📧 Gmail: <code>{ei}</code>\n\n🔑 App Password পাঠান:")
            return True
        admin_panel(chat_id)

    elif action.startswith("add_gmail_pass:"):
        new_email = action.split("add_gmail_pass:", 1)[1]
        app_pass  = text.strip().replace(" ", "")
        try:
            t = imaplib.IMAP4_SSL("imap.gmail.com")
            t.login(new_email, app_pass)
            t.logout()
            cfg["gmail_list"].append(new_email)
            cfg.setdefault("imap_passwords", {})[new_email] = app_pass
            save_config(cfg)
            threading.Thread(target=imap_thread, args=(new_email, app_pass), daemon=True).start()
            send_msg(chat_id, f"✅ <code>{new_email}</code> যোগ হয়েছে। IMAP চালু।")
        except Exception as e:
            send_msg(chat_id, f"❌ Login ব্যর্থ!\n<code>{e}</code>")
        admin_panel(chat_id)

    elif action == "del_gmail":
        em = text.strip()
        if em in cfg["gmail_list"]:
            cfg["gmail_list"].remove(em)
            cfg.get("imap_passwords", {}).pop(em, None)
            save_config(cfg)
            send_msg(chat_id, f"✅ <code>{em}</code> মুছে ফেলা হয়েছে।")
        else:
            send_msg(chat_id, "❌ নেই।")
        admin_panel(chat_id)

    elif action == "add_channel":
        if "-" in text and "https://" in text:
            idx = text.index("-")
            cfg["force_join"]["channels"].append({
                "name": text[:idx].strip(), "link": text[idx+1:].strip()
            })
            save_config(cfg)
            send_msg(chat_id, "✅ Channel যোগ হয়েছে।")
        else:
            send_msg(chat_id, "❌ Format: <code>নাম-https://t.me/link</code>")
        admin_panel(chat_id)

    elif action == "del_channel":
        cfg["force_join"]["channels"] = [
            c for c in cfg["force_join"]["channels"] if c["name"] != text.strip()
        ]
        save_config(cfg)
        send_msg(chat_id, "✅ মুছে ফেলা হয়েছে।")
        admin_panel(chat_id)

    elif action == "otp_link":
        cfg["otp_group"]["link"] = text.strip()
        save_config(cfg)
        send_msg(chat_id, "✅ Link পরিবর্তন হয়েছে।")
        admin_panel(chat_id)

    elif action == "broadcast_msg":
        photo = None
        if msg and "photo" in msg and msg["photo"]:
            photo = msg["photo"][-1]["file_id"]
            content_text = (msg.get("caption") or "").strip()
        else:
            content_text = text.strip()

        if not photo and not content_text:
            send_msg(chat_id, "❌ Broadcast করার জন্য text অথবা image পাঠান।")
            admin_panel(chat_id)
            return True

        extra_data = {"photo": photo, "text": content_text}
        set_pending(chat_id, "broadcast_confirm", pmid, extra=extra_data)

        confirm_markup = {"inline_keyboard": [[
            {"text": "✅ Send",   "callback_data": "bc_confirm"},
            {"text": "❌ Cancel", "callback_data": "bc_cancel"}
        ]]}

        if photo:
            preview_caption = f"আপনি কি এই photo broadcast করতে চান?\n\n<b>Caption:</b>\n{content_text}" if content_text else "আপনি কি এই photo broadcast করতে চান?"
            send_photo(chat_id, photo, caption=preview_caption, markup=confirm_markup)
        else:
            send_msg(
                chat_id,
                f"আপনি কি এই message broadcast করতে চান?\n\n<blockquote>{content_text}</blockquote>",
                markup=confirm_markup
            )
        return True

    elif action == "block":
        try:
            uid = int(text.strip())
            if uid not in cfg["blocked_users"]:
                cfg["blocked_users"].append(uid); save_config(cfg)
                send_msg(chat_id, f"🚫 <code>{uid}</code> blocked।")
            else: send_msg(chat_id, "⚠️ Already blocked।")
        except: send_msg(chat_id, "❌ Chat ID দিন।")
        admin_panel(chat_id)

    elif action == "unblock":
        try:
            uid = int(text.strip())
            if uid in cfg["blocked_users"]:
                cfg["blocked_users"].remove(uid); save_config(cfg)
                send_msg(chat_id, f"✅ <code>{uid}</code> unblocked।")
            else: send_msg(chat_id, "⚠️ Blocked না।")
        except: send_msg(chat_id, "❌ Chat ID দিন।")
        admin_panel(chat_id)

    elif action == "sheet_title":
        cfg["sheet_title"] = text.strip(); save_config(cfg)
        send_msg(chat_id, f"✅ Sheet: <code>{text.strip()}</code>")
        admin_panel(chat_id)

    elif action == "set_ad_text":
        cfg.setdefault("ad_button", {})["text"] = text.strip()
        save_config(cfg)
        update_telegram_menu_button()
        send_msg(chat_id, f"✅ Ad Button Text পরিবর্তন হয়েছে: <code>{html.escape(text.strip())}</code>")
        admin_panel(chat_id)

    elif action == "set_ad_link":
        cfg.setdefault("ad_button", {})["url"] = text.strip()
        save_config(cfg)
        update_telegram_menu_button()
        send_msg(chat_id, f"✅ Ad Button Link পরিবর্তন হয়েছে: <code>{html.escape(text.strip())}</code>")
        admin_panel(chat_id)

    elif action == "group_bot_token":
        token = text.strip()
        try:
            r = _session.get(
                f"https://api.telegram.org/bot{token}/getMe", timeout=15
            ).json()
            if not r.get("ok"): raise Exception("Invalid token")
            bot_name = r["result"].get("username", "")
            cfg.setdefault("group_bot", {})["token"] = token
            save_config(cfg)
            set_pending(chat_id, "group_bot_groupid", pmid)
            send_msg(chat_id, f"✅ @{bot_name}\n\n📢 Group ID পাঠান:\n<code>-1001234567890</code>")
            return True
        except Exception as e:
            send_msg(chat_id, f"❌ Token invalid!\n<code>{e}</code>")
            admin_panel(chat_id)

    elif action == "group_bot_groupid":
        cfg.setdefault("group_bot", {})["group_id"]      = text.strip()
        cfg["group_bot"]["enabled"]       = True
        cfg["group_bot"]["send_all_mail"] = True
        save_config(cfg)
        send_msg(chat_id, f"✅ Group Bot চালু!\nID: <code>{text.strip()}</code>\n\nBot কে group এর admin করুন।")
        admin_panel(chat_id)

    elif action == "set_del_user":
        secs = parse_time_input(text)
        cfg.setdefault("auto_delete", {})["user_seconds"] = secs
        save_config(cfg)
        msg = f"✅ User OTP <code>{secs}s</code> পরে delete হবে।" if secs else "✅ User OTP auto delete বন্ধ।"
        send_msg(chat_id, msg)
        admin_panel(chat_id)

    elif action == "set_del_group":
        secs = parse_time_input(text)
        cfg.setdefault("auto_delete", {})["group_seconds"] = secs
        save_config(cfg)
        msg = f"✅ Group OTP <code>{secs}s</code> পরে delete হবে।" if secs else "✅ Group OTP auto delete বন্ধ।"
        send_msg(chat_id, msg)
        admin_panel(chat_id)

    return True

def do_broadcast(admin_id, message_data):
    """সব user কে broadcast করে result দেখায়"""
    users = get_all_users()
    ok = fail = 0

    photo = None
    text = ""
    if isinstance(message_data, dict):
        photo = message_data.get("photo")
        text = message_data.get("text", "")
    else:
        text = str(message_data)

    for u in users:
        try:
            cid = int(u["chat_id"])
            if photo:
                caption = f"📢 <b>Admin Notice:</b>\n\n{text}" if text else "📢 <b>Admin Notice</b>"
                send_photo(cid, photo, caption=caption)
            else:
                send_msg(cid, f"📢 <b>Admin Notice:</b>\n\n{text}")
            ok += 1
            time.sleep(0.05)
        except: fail += 1
    send_msg(admin_id, f"📢 Broadcast শেষ!\n\n✅ {ok}\n❌ {fail}")

# ==========================
# BACKGROUND SERVICES
# ==========================
def _background_cleanup():
    """Periodic in-memory cleanup — every 5 min to prevent RAM leaks."""
    while True:
        time.sleep(300)
        try:
            now = time.time()
            # Clean expired OTP dedup entries (they expire in 60s naturally)
            for key in list(_sent_otps.keys()):
                _sent_otps[key] = {k: v for k, v in _sent_otps.get(key, {}).items() if now - v < 60}
                if not _sent_otps[key]:
                    _sent_otps.pop(key, None)
            # Trim _user_locks dict — prevents unbounded growth
            if len(_user_locks) > 500:
                to_remove = list(_user_locks.keys())[: len(_user_locks) - 200]
                for k in to_remove:
                    _user_locks.pop(k, None)
        except Exception:
            pass

def _start_health_server():
    """Minimal HTTP health-check server for Railway on $PORT."""
    import http.server
    port = int(os.environ.get("PORT", 8080))

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            uptime = int(time.time() - _start_time)
            self.wfile.write(f"OK uptime={uptime}s".encode())
        def log_message(self, *a):
            pass  # suppress HTTP access log noise

    try:
        srv = http.server.HTTPServer(("0.0.0.0", port), _Handler)
        print(f"{CYAN}[Health] HTTP server on port {port}{RESET}")
        srv.serve_forever()
    except Exception as e:
        print(f"{YELLOW}[Health] Could not start HTTP server: {e}{RESET}")

# ==========================
# BOT LOOP
# ==========================
def run_bot():
    global last_update_id
    print(f"{CYAN}{BOLD}🤖 Polling started...{RESET}")
    _fail_streak = 0
    while True:
        try:
            res = api("getUpdates", params={"offset": last_update_id+1, "timeout": 30})
            updates = res.get("result", [])
            _fail_streak = 0  # reset streak on every successful API call
            for update in updates:
                uid = update["update_id"]
                if uid in _processed_updates: continue
                _processed_updates.add(uid)
                if len(_processed_updates) > 1000:
                    for x in sorted(_processed_updates)[:500]:
                        _processed_updates.discard(x)
                last_update_id = uid
                cfg = load_config()

                # ── MESSAGE ──
                if "message" in update:
                    msg     = update["message"]
                    chat_id = msg["chat"]["id"]
                    text    = msg.get("text", "").strip()
                    user    = msg.get("from", {})
                    uname   = user.get("username", "")
                    fname   = f"{user.get('first_name','')} {user.get('last_name','')}".strip()

                    if chat_id in cfg["blocked_users"]:
                        send_msg(chat_id, "🚫 আপনি এই bot ব্যবহার করতে পারবেন না।")
                        continue

                    if is_admin(chat_id):
                        if text == "/admin": admin_panel(chat_id); continue
                        if text in ["/start", "/cancel"]:
                            clear_pending(chat_id)
                        elif process_pending(chat_id, text, msg=msg): continue

                    if not text:
                        continue

                    if text == "/start":
                        lock = get_user_lock(chat_id)
                        if not lock.acquire(blocking=False): continue
                        try:
                            is_new = register_user(chat_id, uname, fname)

                            # Welcome message — শুধুমাত্র প্রথমবার
                            if is_new:
                                welcome_msg = (
                                    "👋 <b>Welcome to Temp Gmail Official Bot!</b>\n\n"
                                    "📬 Get OTPs instantly in your temporary Gmail inbox.\n\n"
                                    "✅ Fast OTP delivery\n"
                                    "🔒 Secure & reliable\n"
                                    "⚡ Easy verification\n"
                                    "🌐 Supports multiple services\n\n"
                                    "Thank you for choosing <b>Temp Gmail Official Bot!</b>"
                                )
                                send_msg(chat_id, welcome_msg)

                            joined, missing = check_joined(chat_id)
                            if not joined:
                                send_force_join(chat_id, missing)
                                continue
                            send_alias_new(chat_id)
                        finally:
                            lock.release()
                        continue

                    if text == "/gen":
                        joined, missing = check_joined(chat_id)
                        if not joined: send_force_join(chat_id, missing); continue
                        send_alias(chat_id)
                        continue

                # ── CALLBACK ──
                if "callback_query" in update:
                    cb      = update["callback_query"]
                    chat_id = cb["message"]["chat"]["id"]
                    msg_id  = cb["message"]["message_id"]
                    data    = cb["data"]

                    if chat_id in cfg["blocked_users"]:
                        answer_cb(cb["id"], "🚫 Blocked", alert=True); continue

                    # Broadcast confirm/cancel
                    if data == "bc_confirm":
                        action, _, extra = get_pending(chat_id)
                        if action == "broadcast_confirm" and extra:
                            clear_pending(chat_id)
                            answer_cb(cb["id"], "📢 Sending...")
                            delete_msg(chat_id, msg_id)
                            threading.Thread(
                                target=do_broadcast, args=(chat_id, extra), daemon=True
                            ).start()
                        continue

                    if data == "bc_cancel":
                        clear_pending(chat_id)
                        answer_cb(cb["id"], "❌ Cancelled")
                        delete_msg(chat_id, msg_id)
                        continue

                    if data == "refresh_alias":
                        joined, missing = check_joined(chat_id)
                        if not joined:
                            answer_cb(cb["id"], "❌ Channel ছেড়ে দিয়েছেন!", alert=True)
                            send_force_join(chat_id, missing)
                        else:
                            d   = get_user_data(chat_id)
                            tag = d.get("tag","") if d else ""
                            answer_cb(cb["id"], f"⏳ {tag} — OTP আসার অপেক্ষায়...")

                    elif data == "next_alias":
                        joined, missing = check_joined(chat_id)
                        if not joined:
                            answer_cb(cb["id"], "❌ Channel ছেড়ে দিয়েছেন!", alert=True)
                            send_force_join(chat_id, missing)
                        else:
                            change_alias(chat_id, msg_id)
                            answer_cb(cb["id"])

                    elif data == "check_join":
                        joined, missing = check_joined(chat_id)
                        if joined:
                            answer_cb(cb["id"], "✅ Verified!")
                            delete_msg(chat_id, msg_id)
                            send_alias(chat_id)
                        else:
                            answer_cb(cb["id"], "❌ এখনো Join করেননি!", alert=True)

                    elif is_admin(chat_id):
                        answer_cb(cb["id"])

                        if data == "adm_add_gmail":
                            set_pending(chat_id, "add_gmail", msg_id)
                            delete_msg(chat_id, msg_id)
                            send_msg(chat_id, "📧 Gmail পাঠান:\n<code>example@gmail.com</code>")

                        elif data == "adm_del_gmail":
                            lst = "\n".join([f"• <code>{g}</code>" for g in cfg["gmail_list"]]) or "❌ নেই।"
                            set_pending(chat_id, "del_gmail", msg_id)
                            send_msg(chat_id, f"<b>Gmail List:</b>\n{lst}\n\nমুছতে Gmail পাঠান:")

                        elif data == "adm_toggle_fj":
                            cfg["force_join"]["enabled"] = not cfg["force_join"]["enabled"]
                            save_config(cfg); admin_panel(chat_id, msg_id)

                        elif data == "adm_add_ch":
                            set_pending(chat_id, "add_channel", msg_id)
                            delete_msg(chat_id, msg_id)
                            send_msg(chat_id, "➕ Format:\n<code>নাম-https://t.me/link</code>")

                        elif data == "adm_del_ch":
                            lst = "\n".join([f"• <code>{c['name']}</code>" for c in cfg["force_join"]["channels"]]) or "❌ নেই।"
                            set_pending(chat_id, "del_channel", msg_id)
                            send_msg(chat_id, f"<b>Channels:</b>\n{lst}\n\nমুছতে নাম পাঠান:")

                        elif data == "adm_toggle_otp":
                            cfg["otp_group"]["enabled"] = not cfg["otp_group"]["enabled"]
                            save_config(cfg); admin_panel(chat_id, msg_id)

                        elif data == "adm_otp_link":
                            set_pending(chat_id, "otp_link", msg_id)
                            send_msg(chat_id, f"🔗 বর্তমান: <code>{cfg['otp_group']['link']}</code>\nনতুন link পাঠান:")

                        elif data == "adm_group_bot":
                            gb = cfg.get("group_bot", {})
                            if gb.get("enabled"):
                                cfg["group_bot"]["enabled"] = False
                                save_config(cfg)
                                send_msg(chat_id, "❌ Group Bot বন্ধ।")
                                admin_panel(chat_id, msg_id)
                            else:
                                if gb.get("token") and gb.get("group_id"):
                                    cfg["group_bot"]["enabled"] = True
                                    save_config(cfg)
                                    send_msg(chat_id, "✅ Group Bot চালু।")
                                    admin_panel(chat_id, msg_id)
                                else:
                                    set_pending(chat_id, "group_bot_token", msg_id)
                                    delete_msg(chat_id, msg_id)
                                    send_msg(chat_id, "🤖 Group Bot Token পাঠান:")

                        elif data == "adm_toggle_group_mail":
                            current = cfg.get("group_bot", {}).get("send_all_mail", True)
                            cfg.setdefault("group_bot", {})["send_all_mail"] = not current
                            save_config(cfg)
                            status = "✅ চালু" if not current else "❌ বন্ধ"
                            send_msg(chat_id, f"📧 All Mail {status}।")
                            admin_panel(chat_id, msg_id)

                        elif data == "adm_broadcast":
                            set_pending(chat_id, "broadcast_msg", msg_id)
                            delete_msg(chat_id, msg_id)
                            send_msg(chat_id, "📢 Message অথবা Image (caption সহ বা ছাড়া) পাঠান:")

                        elif data == "adm_stats":
                            send_msg(chat_id,
                                f"📊 <b>Statistics</b>\n\n"
                                f"👥 Users: <code>{len(_cache)}</code>\n"
                                f"📧 Gmails: <code>{len(cfg['gmail_list'])}</code>\n"
                                f"🚫 Blocked: <code>{len(cfg['blocked_users'])}</code>")

                        elif data == "adm_del_user":
                            ud = cfg.get("auto_delete", {}).get("user_seconds", 0)
                            ud_txt = f"{ud}s" if ud else "Off"
                            set_pending(chat_id, "set_del_user", msg_id)
                            send_msg(chat_id,
                                f"⏱ <b>User OTP Auto Delete</b>\n"
                                f"বর্তমান: <code>{ud_txt}</code>\n\n"
                                f"Format: <code>M1</code> = 1 মিনিট, <code>S35</code> = 35 সেকেন্ড\n"
                                f"বন্ধ করতে: <code>S0</code>")

                        elif data == "adm_del_group":
                            gd = cfg.get("auto_delete", {}).get("group_seconds", 0)
                            gd_txt = f"{gd}s" if gd else "Off"
                            set_pending(chat_id, "set_del_group", msg_id)
                            send_msg(chat_id,
                                f"⏱ <b>Group OTP Auto Delete</b>\n"
                                f"বর্তমান: <code>{gd_txt}</code>\n\n"
                                f"Format: <code>M1</code> = 1 মিনিট, <code>S35</code> = 35 সেকেন্ড\n"
                                f"বন্ধ করতে: <code>S0</code>")

                        elif data == "adm_block":
                            set_pending(chat_id, "block", msg_id)
                            delete_msg(chat_id, msg_id)
                            send_msg(chat_id, "🚫 Block করতে Chat ID পাঠান:")

                        elif data == "adm_unblock":
                            if not cfg["blocked_users"]:
                                send_msg(chat_id, "✅ কোনো blocked user নেই।")
                            else:
                                lst = "\n".join([f"• <code>{u}</code>" for u in cfg["blocked_users"]])
                                set_pending(chat_id, "unblock", msg_id)
                                send_msg(chat_id, f"<b>Blocked:</b>\n{lst}\n\nUnblock Chat ID:")

                        elif data == "adm_users":
                            users = get_all_users()
                            if not users:
                                send_msg(chat_id, "❌ কোনো user নেই।")
                            else:
                                lines = [
                                    f"<code>{u['chat_id']}</code> @{u.get('username','N/A')} {u.get('full_name','')}"
                                    for u in users[:50]
                                ]
                                send_msg(chat_id, "👥 <b>Users:</b>\n\n" + "\n".join(lines))

                        elif data == "adm_sheet_title":
                            set_pending(chat_id, "sheet_title", msg_id)
                            send_msg(chat_id, f"📋 বর্তমান: <code>{cfg['sheet_title']}</code>\nনতুন title পাঠান:")

                        elif data == "adm_toggle_ad":
                            cfg.setdefault("ad_button", {})["enabled"] = not cfg.get("ad_button", {}).get("enabled", False)
                            save_config(cfg)
                            update_telegram_menu_button()
                            admin_panel(chat_id, msg_id)

                        elif data == "adm_ad_text":
                            current_text = cfg.get("ad_button", {}).get("text", "🚀 Open App")
                            set_pending(chat_id, "set_ad_text", msg_id)
                            send_msg(chat_id, f"✍️ বর্তমান বাটন টেক্সট: <code>{html.escape(current_text)}</code>\nনতুন টেক্সট পাঠান:")

                        elif data == "adm_ad_link":
                            current_url = cfg.get("ad_button", {}).get("url", "")
                            set_pending(chat_id, "set_ad_link", msg_id)
                            send_msg(chat_id, f"🔗 বর্তমান বাটন লিংক: <code>{html.escape(current_url)}</code>\nনতুন লিংক পাঠান:")

        except Exception as e:
            _fail_streak += 1
            wait = min(60, 3 * _fail_streak)
            print(f"{RED}[Bot] {e} — retry in {wait}s (streak={_fail_streak}){RESET}")
            time.sleep(wait)

# ==========================
# START
# ==========================
if __name__ == "__main__":
    print(f"{MAGENTA}{BOLD}{'='*45}{RESET}")
    print(f"{MAGENTA}{BOLD}   📬  Gmail OTP Bot  —  Starting Up   {RESET}")
    print(f"{MAGENTA}{BOLD}{'='*45}{RESET}")

    cfg = load_config()
    print(f"{CYAN}⚙️  Config loaded{RESET}")

    # Local data load
    load_cache()
    _load_pending_from_file()   # restore pending admin states from disk

    # IMAP threads
    print(f"{CYAN}{'─'*45}{RESET}")
    for gmail in cfg["gmail_list"]:
        pw = cfg.get("imap_passwords", {}).get(gmail, "")
        if pw and "YOUR_APP_PASSWORD" not in pw:
            threading.Thread(target=imap_thread, args=(gmail, pw), daemon=True).start()
            print(f"{GREEN}✅ IMAP:{RESET} {WHITE}{gmail}{RESET}")
        else:
            print(f"{YELLOW}⚠️  Password নেই:{RESET} {DIM}{gmail}{RESET}")

    print(f"{CYAN}{'─'*45}{RESET}")
    print(f"{GREEN}{BOLD}🤖 Bot চালু...{RESET}")
    try:
        update_telegram_menu_button()
    except Exception as e:
        print(f"{RED}[Menu Button Init Error] {e}{RESET}")

    # Start background services
    threading.Thread(target=_start_health_server, daemon=True).start()
    threading.Thread(target=_background_cleanup,  daemon=True).start()

    # Outer restart loop — auto-recover from any uncaught crash
    _crash_count = 0
    while True:
        try:
            run_bot()
        except Exception as e:
            _crash_count += 1
            wait = min(60, 5 * _crash_count)
            print(f"{RED}[CRITICAL] Bot crashed (#{_crash_count}): {e} — restarting in {wait}s{RESET}")
            time.sleep(wait)
        else:
            _crash_count = 0
