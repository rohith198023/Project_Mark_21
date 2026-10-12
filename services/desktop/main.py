import os
import sys
import string
import logging
import subprocess
import re
import shutil
import time
import difflib
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Ensure project root is in python path to resolve shared module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from shared.contracts.schemas import HealthResponse, ReadinessResponse, Task, ActionResult

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("desktop-agent")

app = FastAPI(
    title="JARVIS Desktop Agent",
    description="Desktop automation agent for application control and window management.",
    version="1.0.0"
)

IS_WINDOWS = sys.platform == "win32"

pywinauto_available = False
pyautogui_available = False

if IS_WINDOWS:
    try:
        import pywinauto
        from pywinauto import Application, Desktop
        pywinauto_available = True
        logger.info("Successfully imported win32 automation library (pywinauto).")
    except ImportError as e:
        logger.warning(f"Failed to import pywinauto on Windows: {e}. Falling back to simulation.")
        
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui_available = True
        logger.info("Successfully imported PyAutoGUI (FAILSAFE disabled).")
    except Exception as e:
        logger.warning(f"Failed to import pyautogui: {e}")
else:
    logger.info("Running on non-Windows host (Linux/Docker). Win32 automation is disabled (simulated mode active).")


# APP_REGISTRY maps standard app name aliases to Win32 executables and URI protocol handlers
APP_REGISTRY = [
    {
        "canonical": "notepad",
        "aliases": ["notepad"],
        "launch_type": "exe",
        "target": "notepad.exe",
        "title_hints": ["notepad"]
    },
    {
        "canonical": "chrome",
        "aliases": ["chrome", "google chrome"],
        "launch_type": "exe",
        "target": "chrome.exe",
        "title_hints": ["google chrome", "chrome"]
    },
    {
        "canonical": "explorer",
        "aliases": ["explorer", "file explorer", "file manager", "my files", "file folder", "my file folder"],
        "launch_type": "exe",
        "target": "explorer.exe",
        "title_hints": ["file explorer", "explorer"]
    },
    {
        "canonical": "whatsapp",
        "aliases": ["whatsapp"],
        "launch_type": "uri",
        "target": "whatsapp://",
        "title_hints": ["whatsapp"]
    },
    {
        "canonical": "teams",
        "aliases": ["microsoft teams", "teams"],
        "launch_type": "uri",
        "target": "ms-teams://",
        "title_hints": ["microsoft teams", "teams"]
    },
    {
        "canonical": "store",
        "aliases": ["microsoft store", "store", "windows store"],
        "launch_type": "uri",
        "target": "ms-windows-store://",
        "title_hints": ["microsoft store", "store"]
    },
    {
        "canonical": "copilot",
        "aliases": ["copilot", "windows copilot"],
        "launch_type": "uri",
        "target": "ms-copilot://",
        "title_hints": ["copilot"]
    },
    {
        "canonical": "calculator",
        "aliases": ["calculator"],
        "launch_type": "uri",
        "target": "ms-calculator://",
        "title_hints": ["calculator"]
    },
    {
        "canonical": "settings",
        "aliases": ["settings", "system settings", "windows settings"],
        "launch_type": "uri",
        "target": "ms-settings://",
        "title_hints": ["settings"]
    },
    {
        "canonical": "terminal",
        "aliases": ["terminal", "windows terminal"],
        "launch_type": "exe",
        "target": "wt.exe",
        "title_hints": ["terminal", "windows terminal"]
    },
    {
        "canonical": "paint",
        "aliases": ["paint"],
        "launch_type": "exe",
        "target": "mspaint.exe",
        "title_hints": ["paint", "paint 3d"]
    },
    {
        "canonical": "task manager",
        "aliases": ["task manager"],
        "launch_type": "exe",
        "target": "taskmgr.exe",
        "title_hints": ["task manager"]
    },
    {
        "canonical": "edge",
        "aliases": ["edge", "browser", "microsoft edge"],
        "launch_type": "uri",
        "target": "ms-edge://",
        "title_hints": ["microsoft edge", "edge"]
    },
    {
        "canonical": "discord",
        "aliases": ["discord"],
        "launch_type": "uri",
        "target": "discord://",
        "title_hints": ["discord"]
    },
    {
        "canonical": "spotify",
        "aliases": ["spotify"],
        "launch_type": "uri",
        "target": "spotify://",
        "title_hints": ["spotify"]
    },
    {
        "canonical": "slack",
        "aliases": ["slack"],
        "launch_type": "exe",
        "target": "slack.exe",
        "title_hints": ["slack"]
    },
    {
        "canonical": "zoom",
        "aliases": ["zoom"],
        "launch_type": "uri",
        "target": "zoom://",
        "title_hints": ["zoom"]
    },
    {
        "canonical": "vs code",
        "aliases": ["vs code", "visual studio code"],
        "launch_type": "exe",
        "target": "Code.exe",
        "title_hints": ["visual studio code", "vscode", "vs code"]
    },
    {
        "canonical": "word",
        "aliases": ["word", "microsoft word"],
        "launch_type": "uri",
        "target": "ms-word://",
        "title_hints": ["word", "microsoft word"]
    },
    {
        "canonical": "excel",
        "aliases": ["excel", "microsoft excel"],
        "launch_type": "uri",
        "target": "ms-excel://",
        "title_hints": ["excel", "microsoft excel"]
    },
    {
        "canonical": "powerpoint",
        "aliases": ["powerpoint", "microsoft powerpoint"],
        "launch_type": "uri",
        "target": "ms-powerpoint://",
        "title_hints": ["powerpoint", "microsoft powerpoint"]
    },
    {
        "canonical": "google keep",
        "aliases": ["google keep", "keep", "google keep app"],
        "launch_type": "uri",
        "target": "https://keep.google.com/",
        "title_hints": ["google keep", "keep"]
    },
    {
        "canonical": "youtube",
        "aliases": ["youtube", "you tube", "yt"],
        "launch_type": "uri",
        "target": "https://www.youtube.com",
        "title_hints": ["youtube"]
    }
]

LAST_WA_CONTACT: Optional[str] = None

def get_first_yt_video(query: str) -> str:
    """Finds direct video link for a YouTube search query."""
    import urllib.request, urllib.parse
    encoded = urllib.parse.quote(query)
    search_url = f"https://www.youtube.com/results?search_query={encoded}"
    try:
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        )
        with urllib.request.urlopen(req, timeout=4) as res:
            html = res.read().decode("utf-8", errors="ignore")
            video_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html)
            if video_ids:
                return f"https://www.youtube.com/watch?v={video_ids[0]}"
    except Exception as e:
        logger.warning(f"Error fetching direct YouTube video: {e}")
    return search_url

def generate_text_content(prompt_text: str) -> str:
    """Generates content using Groq if available, or returns clean structured code/text."""
    try:
        from shared.config.settings import settings
        from groq import Groq
        if settings.groq_api_key:
            client = Groq(api_key=settings.groq_api_key)
            res = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": "You are a specialized code and text writer for Project JARVIS. Generate only the requested algorithm, code, or text clearly and concisely without conversational filler or markdown fences, ready to paste directly into an editor."},
                    {"role": "user", "content": f"Write {prompt_text}"}
                ],
                max_tokens=500,
                temperature=0.7
            )
            return (res.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning(f"Failed to generate text content via Groq: {e}")
    return f"# {prompt_text.title()}\n\ndef nucleus_sampling(logits, p=0.9):\n    import numpy as np\n    probs = np.exp(logits) / np.sum(np.exp(logits))\n    sorted_indices = np.argsort(probs)[::-1]\n    sorted_probs = probs[sorted_indices]\n    cumulative_probs = np.cumsum(sorted_probs)\n    top_indices = sorted_indices[cumulative_probs <= p]\n    return top_indices\n"

def focus_whatsapp_window() -> bool:
    """Brings WhatsApp to foreground on Windows."""
    if not IS_WINDOWS:
        return False
    try:
        import win32gui, win32con
        matched_hwnds = []
        def _enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                cname = win32gui.GetClassName(hwnd).lower()
                if "whatsapp" in title or "whatsapp" in cname:
                    matched_hwnds.append(hwnd)
            return True
        win32gui.EnumWindows(_enum_cb, None)
        if matched_hwnds:
            hwnd = matched_hwnds[0]
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            logger.info(f"Focused WhatsApp window (hwnd={hwnd})")
            return True
    except Exception as e:
        logger.warning(f"Could not focus WhatsApp window: {e}")
    return False

def extract_whatsapp_details(user_input_raw: str, params: dict = None) -> tuple[Optional[str], Optional[str]]:
    """Extracts recipient contact and message text from various speech/text variations."""
    params = params or {}
    wa_contact = params.get("contact") or params.get("recipient")
    wa_msg = params.get("message") or params.get("text")

    if wa_contact and wa_msg:
        return str(wa_contact).strip(), str(wa_msg).strip()

    text = user_input_raw.strip()

    # Pattern: message/text <contact> saying/that/: <msg>
    m = re.search(r"\b(?:text|msg|message|send\s+message\s+to|send\s+msg\s+to)\s+([a-zA-Z0-9_\-\.]+)\s+(?:saying|that|with\s+text|with\s+message|\:)\s*(.*)", text, re.IGNORECASE)
    if m:
        c = m.group(1).strip()
        msg = m.group(2).strip()
        return (wa_contact or c), (wa_msg or msg)

    # Pattern: message/text <contact> <msg> (e.g. "open WhatsApp and message Siddhartha hello")
    m = re.search(r"\b(?:text|msg|message|send\s+message\s+to|send\s+msg\s+to)\s+([a-zA-Z0-9_\-\.]+)\s+(hello.*|hi.*|hey.*|where.*|how.*|can.*|please.*|call.*|i\s+.*|we\s+.*|good\s+.*|are\s+.*|what.*)", text, re.IGNORECASE)
    if m:
        c = m.group(1).strip()
        msg = m.group(2).strip()
        return (wa_contact or c), (wa_msg or msg)

    # Pattern: message/text <contact> (no message, e.g. "open WhatsApp and message Siddhartha")
    m = re.search(r"\b(?:text|msg|message|send\s+message\s+to|send\s+msg\s+to)\s+([a-zA-Z0-9_\-\.]+)", text, re.IGNORECASE)
    if m:
        c = m.group(1).strip()
        return (wa_contact or c), wa_msg

    return wa_contact, wa_msg

def clean_desktop_query(query: str, action: str) -> str:
    """Cleans command verbs and structural filler words from queries using word boundaries to avoid corruption."""
    if action == "open":
        words_to_remove = r"\b(open|launch|app)\b"
    elif action == "close":
        words_to_remove = r"\b(close|terminate|exit|app)\b"
    elif action == "focus":
        words_to_remove = r"\b(focus|switch to|bring to front)\b"
    else:
        return query.strip()
        
    cleaned = re.sub(words_to_remove, "", query, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()

def normalize_user_phrase(query: str) -> str:
    """Stage A: Cleans user queries into lowercase, removes punctuation, handles spacing and removes filler verbs."""
    text = query.lower()
    
    # Replace separators like _ and - with space FIRST (before punctuation strip)
    text = text.replace("_", " ").replace("-", " ")
    
    # Strip remaining punctuation (everything except alphanumerics and spaces)
    # Build table that maps each punctuation character to None (delete)
    punct_except_space = string.punctuation.replace("-", "")  # - already handled above
    text = text.translate(str.maketrans("", "", punct_except_space))
    
    # Filler words/command wrappers to remove cleanly (order matters: multi-word first)
    fillers = [
        r"\bopen up\b",
        r"\bbring up\b",
        r"\bpop up\b",
        r"\bopen\b",
        r"\blaunch\b",
        r"\bstart\b",
        r"\bshow\b",
        r"\brun\b"
    ]
    for filler in fillers:
        text = re.sub(filler, "", text, flags=re.IGNORECASE)
        
    # Collapse multiple spaces and trim
    text = re.sub(r"\s+", " ", text).strip()
    return text

def resolve_app_name(normalized_phrase: str):
    """Stage B: Resolves normalized phrase to registry entry using exact, alias, and fuzzy matching."""
    if not normalized_phrase:
        return None, "unknown", "search_fallback"
        
    # 1. Exact canonical check
    for entry in APP_REGISTRY:
        if normalized_phrase == entry["canonical"]:
            logger.info(f"Resolved app canonical exact match: '{normalized_phrase}'")
            return entry, entry["canonical"], "exact_match"
            
    # 2. Exact alias check
    for entry in APP_REGISTRY:
        if normalized_phrase in entry["aliases"]:
            logger.info(f"Resolved app alias match: '{normalized_phrase}' -> '{entry['canonical']}'")
            return entry, entry["canonical"], "alias_match"

    # 2b. Containment match (e.g. 'whatsapp and text motati hi' contains 'whatsapp')
    for entry in APP_REGISTRY:
        if re.search(rf"\b{re.escape(entry['canonical'])}\b", normalized_phrase):
            logger.info(f"Resolved app containment match: '{normalized_phrase}' contains canonical '{entry['canonical']}'")
            return entry, entry["canonical"], "containment_match"
        for alias in entry["aliases"]:
            if re.search(rf"\b{re.escape(alias)}\b", normalized_phrase):
                logger.info(f"Resolved app containment match: '{normalized_phrase}' contains alias '{alias}'")
                return entry, entry["canonical"], "containment_match"
            
    # 3. Fuzzy matching on canonical & aliases
    best_entry = None
    best_name = None
    best_score = 0.0
    best_match_type = None
    
    for entry in APP_REGISTRY:
        # Check canonical
        score = difflib.SequenceMatcher(None, normalized_phrase, entry["canonical"]).ratio()
        if score > best_score:
            best_score = score
            best_entry = entry
            best_name = entry["canonical"]
            best_match_type = "fuzzy_match"
            
        # Check aliases
        for alias in entry["aliases"]:
            score = difflib.SequenceMatcher(None, normalized_phrase, alias).ratio()
            if score > best_score:
                best_score = score
                best_entry = entry
                best_name = alias
                best_match_type = "fuzzy_match"
                
    if best_score >= 0.70:
        logger.info(f"Resolved app via fuzzy match: '{normalized_phrase}' -> '{best_name}' (score: {best_score:.2f})")
        return best_entry, best_entry["canonical"], "fuzzy_match"
        
    logger.info(f"No registry match found for '{normalized_phrase}', using search fallback.")
    return None, normalized_phrase, "search_fallback"

def resolve_app_path(app_name: str) -> Optional[str]:
    """Resolves human app name or executable candidate name to a full path or shortcut on Windows."""
    name_clean = app_name.lower().strip()
    if not name_clean:
        return None
        
    # Construct candidate exe name if not already an executable or shortcut path
    if name_clean.endswith(".exe") or name_clean.endswith(".lnk") or name_clean.endswith(".msc"):
        exec_names = [app_name]
    else:
        exec_names = [f"{app_name}.exe"]
        # If there are spaces, also check spaceless version of the executable
        if " " in name_clean:
            exec_names.append(f"{app_name.replace(' ', '')}.exe")

    # 1. Search Start Menu shortcuts on Windows (most human-like lookup)
    if IS_WINDOWS:
        start_menu_dirs = [
            os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")
        ]
        
        # We will collect shortcuts to perform exact, spaceless, and fuzzy matching
        shortcuts = []
        for start_dir in start_menu_dirs:
            if not os.path.isdir(start_dir):
                continue
            for root, dirs, files in os.walk(start_dir):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        shortcuts.append((os.path.join(root, file), os.path.splitext(file)[0].lower()))
        
        # 1a. Try Exact or word boundary match on shortcuts
        for path, shortcut_name in shortcuts:
            if name_clean == shortcut_name or f" {name_clean} " in f" {shortcut_name} ":
                logger.info(f"Resolved app via Start Menu shortcut (exact/word): '{path}'")
                return path

        # 1b. Try matching spaceless name on shortcuts
        if " " in name_clean:
            spaceless_name = name_clean.replace(" ", "")
            for path, shortcut_name in shortcuts:
                spaceless_shortcut = shortcut_name.replace(" ", "")
                if spaceless_name == spaceless_shortcut or spaceless_name in spaceless_shortcut:
                    logger.info(f"Resolved app via Start Menu shortcut (spaceless): '{path}'")
                    return path

        # 1c. Try Fuzzy Matching on shortcuts (for unregistered apps like VLC player, Zoom, etc.)
        best_fuzzy_match = None
        best_fuzzy_score = 0.0
        for path, shortcut_name in shortcuts:
            score = difflib.SequenceMatcher(None, name_clean, shortcut_name).ratio()
            if score > best_fuzzy_score:
                best_fuzzy_score = score
                best_fuzzy_match = path
        
        if best_fuzzy_score >= 0.70:
            logger.info(f"Resolved app via Start Menu shortcut (fuzzy match: {best_fuzzy_score:.2f}): '{best_fuzzy_match}'")
            return best_fuzzy_match

    # 2. Chrome special path checking on Windows
    for exec_name in exec_names:
        if exec_name.lower() == "chrome.exe" and IS_WINDOWS:
            common_paths = [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
            ]
            for path in common_paths:
                if os.path.exists(path):
                    return path
            return "chrome.exe"

    # 3. Check if it's already a full path that exists
    for exec_name in exec_names:
        if os.path.exists(exec_name):
            return exec_name

    # 4. Check if it is on the system PATH
    for exec_name in exec_names:
        resolved_path = shutil.which(exec_name)
        if resolved_path:
            return resolved_path

    # 5. Search common Windows directory trees for the executable
    if IS_WINDOWS:
        search_dirs = [
            os.path.expandvars(r"%ProgramFiles%"),
            os.path.expandvars(r"%ProgramFiles(x86)%"),
            os.path.expandvars(r"%LocalAppData%"),
            os.path.expandvars(r"%APPDATA%"),
            os.path.expandvars(r"%LocalAppData%\Programs"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\WindowsApps")
        ]
        for base_dir in search_dirs:
            if not os.path.isdir(base_dir):
                continue
            for exec_name in exec_names:
                # Direct check
                candidate = os.path.join(base_dir, exec_name)
                if os.path.isfile(candidate):
                    return candidate
                
                # Check immediate subdirectories (up to 2 levels deep)
                try:
                    for entry in os.scandir(base_dir):
                        if entry.is_dir():
                            candidate = os.path.join(entry.path, exec_name)
                            if os.path.isfile(candidate):
                                return candidate
                            # Check 1 level deeper
                            for subentry in os.scandir(entry.path):
                                if subentry.is_dir():
                                    subcandidate = os.path.join(subentry.path, exec_name)
                                    if os.path.isfile(subcandidate):
                                        return subcandidate
                except Exception:
                    continue

    return exec_names[0]


@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """Liveness probe."""
    return HealthResponse(status="healthy", service="desktop", version="1.0.0")

@app.get("/readyz", response_model=ReadinessResponse)
def readyz():
    """Readiness probe checking environment capability status."""
    mode = "native_win32" if (IS_WINDOWS and pywinauto_available) else "simulation_fallback"
    return ReadinessResponse(
        status="ready", 
        service="desktop", 
        checks={"mode": mode, "platform": sys.platform}
    )

@app.post("/api/v1/desktop/speak")
def speak_out_loud(payload: Dict[str, Any]):
    """Speaks text out loud directly through Windows audio hardware using SAPI SpVoice."""
    text = payload.get("text", "")
    if not text:
        return {"success": False, "error": "No text provided"}
    
    clean_text = re.sub(r"\[.*?\]", "", text).replace("link", "").strip()
    logger.info(f"Speaking aloud via Windows SAPI: '{clean_text[:60]}...'")
    
    def _speak_worker():
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(clean_text)
        except Exception as e:
            logger.error(f"SAPI speak error: {e}")
            
    import threading
    t = threading.Thread(target=_speak_worker, daemon=True)
    t.start()
    return {"success": True, "spoken_text": clean_text[:60]}

@app.post("/api/v1/desktop/execute", response_model=ActionResult)
def execute_desktop_action(task: Task):
    """Executes a parsed desktop command (launching, closing, or managing apps)."""
    intent = task.intent
    user_input_raw = task.user_input
    user_input = user_input_raw.lower()
    
    logger.info(f"Received Desktop Execution request. TaskID={task.id}, Intent={intent}, Query='{task.user_input}'")

    if intent == "open_app":
        # Stage A: Normalize Phrase (Use LLM planner refined target if available)
        planner_target = (task.planner_metadata or {}).get("target") if task.planner_metadata else None
        if planner_target:
            normalized_phrase = planner_target.lower().strip()
            logger.info(f"Stage A: Using refined target from LLM Planner: '{normalized_phrase}'")
        else:
            normalized_phrase = normalize_user_phrase(user_input_raw)
            logger.info(f"Stage A: Raw query '{user_input_raw}' normalized to '{normalized_phrase}'")
        
        # Stage B: Resolve App Name
        matched_entry, resolved_name, match_type = resolve_app_name(normalized_phrase)
        logger.info(f"Stage B: Resolved name='{resolved_name}', match_type='{match_type}'")
        
        # 1. HANDLE SIMULATED ENVIRONMENT (Docker Linux)
        if not IS_WINDOWS or not pywinauto_available:
            strategy_used = "mock_simulation"
            if matched_entry:
                strategy_used = f"mock_{matched_entry['launch_type']}_launch"
            logger.info(f"Running in Docker/mock mode. Simulating action '{intent}' for '{resolved_name}' via {strategy_used}.")
            return ActionResult(
                success=True,
                output=f"Simulated launching of application '{resolved_name}' via Docker mock mode.",
                match_type=match_type,
                resolved_app=resolved_name,
                launch_strategy=strategy_used,
                verification_status="simulated"
            )

        # 2. HANDLE NATIVE WINDOWS AUTOMATION
        strategy_used = None
        success = False
        error_msg = None
        resolved_path_or_uri = resolved_name
        output_text = None
        global LAST_WA_CONTACT

        # Stage C: Choose Launch Strategy
        # Strategy 1: URI/protocol launch
        if matched_entry and matched_entry["launch_type"] == "uri":
            uri = matched_entry["target"]
            logger.info(f"Stage C: Selected Strategy 1 (URI launch) for '{uri}'")
            try:
                os.startfile(uri)
                strategy_used = "URI launch"
                success = True
                resolved_path_or_uri = uri

                # Special automation for WhatsApp contact & messaging
                if matched_entry["canonical"] == "whatsapp" and pyautogui_available:
                    import urllib.parse
                    params = task.parameters or {}
                    wa_contact, wa_msg = extract_whatsapp_details(user_input_raw, params)

                    # Filter out generic words like 'someone' or 'anyone'
                    generic_recipients = {"someone", "anyone", "somebody", "anybody", "person", "friend"}
                    if wa_contact and wa_contact.lower().strip() in generic_recipients:
                        wa_contact = None

                    # 1. Phone number direct URI
                    if wa_contact and wa_contact.replace("+", "").replace("-", "").replace(" ", "").isdigit() and wa_msg:
                        try:
                            clean_phone = wa_contact.replace("+", "").replace("-", "").replace(" ", "")
                            phone_uri = f"whatsapp://send?phone={clean_phone}&text={urllib.parse.quote(wa_msg)}"
                            os.startfile(phone_uri)
                            strategy_used = f"WhatsApp opened direct chat with +{clean_phone} and prepared message: '{wa_msg}'"
                            output_text = f"Opened WhatsApp and prepared message for +{clean_phone} according to your command: '{wa_msg}'."
                        except Exception as e:
                            logger.warning(f"Phone URI failed: {e}")

                    # 2. Contact name and message provided (e.g. 'open WhatsApp and message Siddhartha hello')
                    elif wa_contact and wa_msg:
                        logger.info(f"WhatsApp automation: contact='{wa_contact}', message='{wa_msg}'")
                        time.sleep(1.2)
                        try:
                            import pyperclip
                            focus_whatsapp_window()
                            time.sleep(0.3)
                            pyautogui.hotkey('ctrl', 'f')
                            time.sleep(0.4)
                            pyperclip.copy(wa_contact.strip(' .'))
                            pyautogui.hotkey('ctrl', 'v')
                            time.sleep(1.0)
                            pyautogui.press('enter')
                            time.sleep(0.8)
                            pyperclip.copy(wa_msg.strip(' .'))
                            pyautogui.hotkey('ctrl', 'v')
                            time.sleep(0.4)
                            pyautogui.press('enter')
                            strategy_used = f"WhatsApp opened chat with '{wa_contact}' and sent: '{wa_msg}'"
                            output_text = f"Opened WhatsApp and sent message to {wa_contact} according to your command: '{wa_msg}'."
                            LAST_WA_CONTACT = None
                        except Exception as auto_err:
                            logger.warning(f"WhatsApp typing automation warning: {auto_err}")

                    # 3. Contact name provided without message (e.g. 'open WhatsApp and message Siddhartha')
                    elif wa_contact and not wa_msg:
                        logger.info(f"WhatsApp automation: contact='{wa_contact}', awaiting message")
                        time.sleep(1.2)
                        try:
                            import pyperclip
                            focus_whatsapp_window()
                            time.sleep(0.3)
                            pyautogui.hotkey('ctrl', 'f')
                            time.sleep(0.4)
                            pyperclip.copy(wa_contact.strip(' .'))
                            pyautogui.hotkey('ctrl', 'v')
                            time.sleep(1.0)
                            pyautogui.press('enter')
                            strategy_used = f"WhatsApp opened chat with '{wa_contact}'"
                            output_text = f"Opened WhatsApp and selected {wa_contact}'s chat according to your command. What message would you like to send?"
                            LAST_WA_CONTACT = wa_contact
                        except Exception as auto_err:
                            logger.warning(f"WhatsApp typing automation warning: {auto_err}")

                    # 4. Message only without contact (or generic someone)
                    elif not wa_contact and wa_msg:
                        try:
                            send_uri = f"whatsapp://send?text={urllib.parse.quote(wa_msg)}"
                            os.startfile(send_uri)
                            strategy_used = f"WhatsApp opened with prepared message: '{wa_msg}'"
                            output_text = f"Opened WhatsApp with prepared message according to your command: '{wa_msg}'."
                        except Exception as e:
                            logger.warning(f"Send URI failed: {e}")

                    # 5. Generic 'someone' or 'new chat'
                    elif not wa_contact and not wa_msg and any(kw in user_input_raw.lower() for kw in ["someone", "anyone", "new chat"]):
                        time.sleep(1.5)
                        try:
                            pyautogui.hotkey('ctrl', 'n')
                            strategy_used = "Opened WhatsApp and launched New Chat selector"
                            output_text = "Opened WhatsApp and launched New Chat selector according to your command."
                        except Exception as e:
                            strategy_used = "Opened WhatsApp"
                            output_text = "Opened WhatsApp according to your command."

                    # 6. Default open WhatsApp
                    else:
                        strategy_used = "Opened WhatsApp"
                        output_text = "Opened WhatsApp according to your command."

                # Special automation for YouTube playback
                elif matched_entry["canonical"] == "youtube":
                    params = task.parameters or {}
                    yt_query = params.get("query") or params.get("video") or params.get("song")
                    if not yt_query:
                        m_yt = re.search(r"\b(?:play|watch|find|song|video)\s+(.*)", user_input_raw, re.IGNORECASE)
                        if m_yt:
                            yt_query = m_yt.group(1).strip()
                            yt_query = re.sub(r"\s+(?:on|in)\s+youtube\b.*", "", yt_query, flags=re.IGNORECASE).strip()

                    if yt_query and yt_query.lower() not in ("youtube", "video", "song"):
                        logger.info(f"YouTube playback requested for query: '{yt_query}'")
                        v_url = get_first_yt_video(yt_query)
                        os.startfile(v_url)
                        strategy_used = f"Opened YouTube and started playing '{yt_query}'"
                        output_text = f"Opened YouTube and started playing '{yt_query}' according to your command."
                    else:
                        os.startfile("https://www.youtube.com")
                        strategy_used = "Opened YouTube"
                        output_text = "Opened YouTube according to your command."
            except Exception as e:
                error_msg = f"URI launch failed: {str(e)}"
                logger.warning(error_msg)

        # Strategy 2: Win32 exe launch
        if not success:
            # Check if we have a resolved path on disk (Start Menu shortcut or file)
            # If matched_entry points to an exe target, we resolve it; otherwise use the normalized phrase to search
            lookup_name = matched_entry["target"] if (matched_entry and matched_entry["launch_type"] == "exe") else resolved_name
            resolved_path = resolve_app_path(lookup_name)
            
            if resolved_path and os.path.exists(resolved_path):
                logger.info(f"Stage C: Selected Strategy 2 (Direct path launch: {resolved_path})")
                
                # 1. Try os.startfile first (highly robust for shortcuts and spaces on Windows)
                try:
                    os.startfile(resolved_path)
                    strategy_used = "Direct path launch (os.startfile)"
                    success = True
                    resolved_path_or_uri = resolved_path

                    # Special automation for writing content in Notepad
                    if matched_entry and matched_entry["canonical"] == "notepad" and pyautogui_available:
                        m_write = re.search(r"\b(?:write|type|note down|add|generate)\s+(.*)", user_input_raw, re.IGNORECASE)
                        if m_write:
                            content_desc = m_write.group(1).strip()
                            logger.info(f"Generating and typing content into Notepad: '{content_desc}'")
                            content_to_write = generate_text_content(content_desc)
                            time.sleep(1.0)
                            try:
                                import pyperclip
                                pyperclip.copy(content_to_write)
                                time.sleep(0.3)
                                pyautogui.hotkey('ctrl', 'v')
                                output_text = f"Opened Notepad and wrote {content_desc} according to your command."
                            except Exception as write_err:
                                logger.warning(f"Failed to type content into Notepad: {write_err}")
                except Exception as start_err:
                    logger.warning(f"os.startfile failed: {start_err}. Trying pywinauto...")
                    
                    # 2. Try pywinauto fallback
                    if pywinauto_available:
                        try:
                            pywinauto.Application().start(resolved_path)
                            strategy_used = "Direct path launch (pywinauto)"
                            success = True
                            resolved_path_or_uri = resolved_path
                        except Exception as pwa_err:
                            logger.warning(f"pywinauto failed: {pwa_err}. Trying subprocess...")
                    
                    # 3. Try subprocess fallback with quoted path to handle spaces
                    if not success:
                        try:
                            subprocess.Popen(f'"{resolved_path}"', shell=True)
                            strategy_used = "Direct path launch (subprocess)"
                            success = True
                            resolved_path_or_uri = resolved_path
                        except Exception as sub_err:
                            error_msg = f"Subprocess launch failed: {str(sub_err)}"
                            logger.error(error_msg)
            
            # If path doesn't exist, but we have a registered exe, try system PATH execution fallback
            if not success and matched_entry and matched_entry["launch_type"] == "exe":
                exe_name = matched_entry["target"]
                logger.info(f"Stage C: Selected Strategy 2 (Win32 exe registry fallback: {exe_name})")
                try:
                    subprocess.Popen(exe_name, shell=True)
                    strategy_used = "Win32 exe registry fallback (subprocess)"
                    success = True
                    resolved_path_or_uri = exe_name
                except Exception as e:
                    error_msg = f"Win32 registry fallback failed: {str(e)}"
                    logger.warning(error_msg)

        # Strategy 3: Windows Search fallback (Fuzzy search using clipboard paste)
        if not success:
            logger.info(f"Stage C: Selected Strategy 3 (Windows Search fallback) for '{resolved_name}'")
            if pyautogui_available:
                try:
                    import pyperclip
                    # If the name has spaces (e.g. "anti gravity"), use the spaceless version to help Windows Search locate it
                    search_term = resolved_name
                    if " " in resolved_name:
                        search_term = resolved_name.replace(" ", "")
                        logger.info(f"Fuzzy search fallback: converted '{resolved_name}' to spaceless '{search_term}'")
                    
                    # Copy the search term to the clipboard to preserve casing and bypass layout/caps lock issues
                    pyperclip.copy(search_term)
                    time.sleep(0.1)
                    
                    pyautogui.hotkey('win', 's')
                    time.sleep(0.8) # Wait slightly longer for Search to activate
                    
                    # Paste using Ctrl+V
                    pyautogui.hotkey('ctrl', 'v')
                    time.sleep(0.4)
                    
                    pyautogui.press('enter')
                    strategy_used = "Windows Search fallback"
                    success = True
                    resolved_path_or_uri = "Windows Search: " + search_term
                except Exception as e:
                    error_msg = f"Windows Search fallback failed: {str(e)}"
                    logger.error(error_msg)
            else:
                error_msg = "pyautogui not available for Windows Search fallback"
                logger.error(error_msg)

        # Stage D: Verify launch
        if success:
            app_verified = False
            logger.info("Stage D: Verification system checking open windows...")
            
            search_terms = []
            if matched_entry:
                search_terms.append(matched_entry["canonical"].lower())
                search_terms.extend([a.lower() for a in matched_entry["aliases"]])
                if "title_hints" in matched_entry:
                    search_terms.extend([t.lower() for t in matched_entry["title_hints"]])
            else:
                search_terms.append(resolved_name.lower())
                if " " in resolved_name:
                    search_terms.append(resolved_name.replace(" ", "").lower())
            
            # De-duplicate terms
            search_terms = list(set(search_terms))
            
            for _ in range(6):  # Wait up to 3 seconds (6 * 0.5s)
                time.sleep(0.5)
                try:
                    if pywinauto_available:
                        windows = Desktop(backend="win32").windows()
                        for win in windows:
                            title = win.window_text().lower()
                            if not title:
                                continue
                                
                            # Exclude browser window titles unless we are explicitly opening a browser app
                            is_browser_app = False
                            if matched_entry and matched_entry["canonical"] in ["chrome", "edge"]:
                                is_browser_app = True
                            else:
                                is_browser_app = any(b in resolved_name.lower() for b in ["chrome", "edge", "firefox", "browser"])
                                
                            if not is_browser_app:
                                if any(sig in title for sig in ["- google chrome", "- microsoft edge", "- mozilla firefox"]):
                                    continue
                                    
                            if any(term in title for term in search_terms):
                                logger.info(f"Stage D: Launch result SUCCESS (verified window '{win.window_text()}')")
                                app_verified = True
                                break
                except Exception as verify_err:
                    logger.warning(f"Error checking windows for verification: {verify_err}")
            
            final_output = output_text if output_text else f"Opened {resolved_name.replace('_', ' ').title()} according to your command."
            return ActionResult(
                success=True,
                output=final_output,
                match_type=match_type,
                resolved_app=resolved_path_or_uri,
                launch_strategy=strategy_used,
                verification_status="verified_window" if app_verified else "window_not_verified"
            )
        
        # If execution failed on Windows
        return ActionResult(
            success=False,
            output=f"Failed to start application: '{resolved_name}'",
            error=error_msg or "All launch strategies failed.",
            match_type=match_type,
            resolved_app=resolved_name,
            launch_strategy=strategy_used or "unknown",
            verification_status="failed_to_launch"
        )

    elif intent == "close_app":
        # Use LLM planner refined target if available
        planner_target = (task.planner_metadata or {}).get("target") if task.planner_metadata else None
        if planner_target:
            cleaned_query = planner_target.lower().strip()
            logger.info(f"Using refined target from LLM Planner for close: '{cleaned_query}'")
        else:
            cleaned_query = clean_desktop_query(user_input, "close")
            
        resolved_path = resolve_app_path(cleaned_query)
        
        if not IS_WINDOWS or not pywinauto_available:
            logger.info(f"[SIMULATE] Simulated closing of application '{cleaned_query}' on {sys.platform}.")
            return ActionResult(success=True, output=f"Simulated closing of application '{cleaned_query}'.")

        if not resolved_path:
            err_msg = f"Cannot resolve application name to close for query: '{cleaned_query}'"
            logger.error(err_msg)
            return ActionResult(success=False, output="", error=err_msg)
        
        exe_name = os.path.basename(resolved_path)
        logger.info(f"Attempting to close process: '{exe_name}'")
        
        res = subprocess.run(
            ["taskkill", "/f", "/im", exe_name],
            capture_output=True,
            text=True,
            shell=True
        )
        
        if res.returncode == 0:
            logger.info(f"Terminated processes matching name: {exe_name} - SUCCESS")
            return ActionResult(success=True, output=f"Terminated processes matching name: {exe_name}")
        else:
            err_msg = f"Failed to close application {exe_name}. System error: {res.stderr.strip()}"
            logger.error(err_msg)
            return ActionResult(success=False, output="", error=err_msg)

    elif intent == "focus_app":
        # Use LLM planner refined target if available
        planner_target = (task.planner_metadata or {}).get("target") if task.planner_metadata else None
        if planner_target:
            cleaned_query = planner_target.lower().strip()
            logger.info(f"Using refined target from LLM Planner for focus: '{cleaned_query}'")
        else:
            cleaned_query = clean_desktop_query(user_input, "focus")
        
        if not IS_WINDOWS or not pywinauto_available:
            logger.info(f"[SIMULATE] Simulated focusing window matching '{cleaned_query}' on {sys.platform}.")
            return ActionResult(success=True, output=f"Simulated focusing window matching '{cleaned_query}'.")

        logger.info(f"Attempting to focus window matching: '{cleaned_query}'")
        windows = Desktop(backend="win32").windows()
        focused = False
        
        for win in windows:
            title = win.window_text().lower()
            if title and cleaned_query in title:
                win.set_focus()
                focused = True
                logger.info(f"Focused window: '{win.window_text()}' - SUCCESS")
                return ActionResult(success=True, output=f"Focused window: {win.window_text()}")
        
        if not focused:
            err_msg = f"No open window title matched search string: '{cleaned_query}'"
            logger.error(err_msg)
            return ActionResult(success=False, output="", error=err_msg)

    elif intent == "list_open_apps":
        if not IS_WINDOWS or not pywinauto_available:
            apps = ["Notepad", "Chrome", "File Explorer"]
            return ActionResult(success=True, output=f"Simulated open applications list: {apps}")

        logger.info("Listing active visible desktop windows...")
        windows = Desktop(backend="win32").windows()
        visible_apps = []
        
        for win in windows:
            title = win.window_text()
            if title and win.is_visible():
                if title not in ["Program Manager", "Start", ""]:
                    visible_apps.append(title)
        
        logger.info("Listed active desktop windows - SUCCESS")
        return ActionResult(success=True, output=f"Active desktop windows: {visible_apps}")

    else:
        err = f"Unsupported desktop automation intent: {intent}"
        logger.error(err)
        return ActionResult(success=False, output="", error=err)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8005))
    logger.info(f"Starting Desktop Agent on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
