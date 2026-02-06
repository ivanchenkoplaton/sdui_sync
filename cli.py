import os
import json
import time
import sys
import re
from datetime import datetime
import requests
import pytz

# Google Auth Imports
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- CONFIGURATION ---
SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = 'auth/credentials.json'
TOKEN_FILE = 'auth/token.json'

# In-Memory Cache for the current session only
CACHED_SERVICE = None

# --- CUSTOM SUBJECT STYLING ---
# Map subject shortcuts from SDUI to a full name, emoji, and Google Calendar color.
# This makes the calendar entries much more readable.
#
# Find your subject shortcuts in the SDUI data (e.g., 'Ph' from '1_Ph5').
# Google Calendar Color IDs: 1-11.
SUBJECT_CONFIG = {
    'Ph': ('Physics', '⚛️', '9'),      # 9: Blue
    'M':  ('Math', '🧮', '4'),        # 4: Purple
    # --- Add or change your own subjects here ---
}

# Global Config
CONFIG = {
    'SDUI_USER_ID': os.getenv('SDUI_USER_ID'),
    'SDUI_AUTH_TOKEN': os.getenv('SDUI_AUTH_TOKEN'),
    'SDUI_EMAIL': os.getenv('SDUI_EMAIL'),
    'SDUI_PASSWORD': os.getenv('SDUI_PASSWORD'),
    'SDUI_SCHOOL_ID': os.getenv('SDUI_SCHOOL_ID'),
    'SDUI_SCHOOL_SLINK': os.getenv('SDUI_SCHOOL_SLINK'),
    'TIMEZONE': os.getenv('TIMEZONE', 'UTC'),
    'GOOGLE_CALENDAR_ID': os.getenv('GOOGLE_CALENDAR_ID', 'primary'),
    'SYNC_YEAR': str(datetime.now().year),
    'SYNC_ONLY_CHANGES': 'false'
}

# --- LOGGING & UTILS ---
def log_msg(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    colors = {"INFO": "\033[92m", "WARN": "\033[93m", "ERROR": "\033[91m", "RESET": "\033[0m"}
    print(f"{colors.get(level, '')}[{timestamp}] {message}{colors['RESET']}")

def input_safe(prompt):
    try:
        return input(prompt).strip()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return None

# --- ENV FILE MANAGEMENT ---
def save_env_file():
    lines = []
    for k, v in CONFIG.items():
        if v is not None: lines.append(f"{k}='{v}'\n")
    with open('.env', 'w', encoding='utf-8') as f: f.writelines(lines)
    log_msg("Configuration saved to .env file.", "INFO")

def load_config():
    if not os.path.exists('.env'): return False
    with open('.env', 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k, v = line.split('=', 1)
            k, v = k.strip(), v.strip().strip("'").strip('"')
            if k in CONFIG: CONFIG[k] = v
    return True

def get_sdui_token(email, password, school_id=None, slink=None):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    if slink:
        url = "https://api.sdui.app/v1/auth/login"
        payload = {
            "identifier": email,
            "password": password,
            "slink": slink,
            "showError": True,
            "token": ""
        }
    else:
        # Fallback to old endpoint if no slink
        url = "https://api.sdui.app/v1/users/login"
        payload = {"email": email, "password": password}
        if school_id: payload['school_id'] = int(school_id)

    response = requests.post(url, json=payload, headers=headers)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        p_log = payload.copy()
        if 'password' in p_log: p_log['password'] = '***'
        log_msg(f"Login Failed. Payload: {p_log}", "ERROR")
        log_msg(f"Response: {response.text}", "ERROR")
        raise e

    data = response.json()
    # Check for 'access_token' (v1/auth) or 'token' (v1/users)
    token = data.get('data', {}).get('access_token') or data.get('data', {}).get('token') or data.get('token')
    
    if not token:
        raise Exception("No token found in login response.")

    uid = data.get('data', {}).get('user_id') or data.get('user_id')
    
    # If User ID is missing (common in v1/auth/login), fetch it from /users/self
    if not uid:
        h2 = headers.copy()
        h2['Authorization'] = f"Bearer {token}"
        r2 = requests.get("https://api.sdui.app/v1/users/self", headers=h2)
        r2.raise_for_status()
        uid = r2.json().get('data', {}).get('id')
        
    return {'token': token, 'user_id': uid}

def action_login():
    print("\n--- Login with SDUI Credentials ---")
    
    school_id = CONFIG.get('SDUI_SCHOOL_ID')
    slink = CONFIG.get('SDUI_SCHOOL_SLINK')
    
    if not school_id or not slink:
        school_name = input_safe("School Name: ")
        if not school_name: return

        print(f"Searching for '{school_name}'...")
        try:
            # Search for school to get ID
            r = requests.get("https://api.sdui.app/v1/schools/public", params={'name': school_name, 'limit': 10})
            r.raise_for_status()
            schools = r.json().get('data', [])
        except Exception as e:
            log_msg(f"Search failed: {e}", "ERROR")
            return

        if not schools:
            print("No schools found.")
            return

        for i, s in enumerate(schools):
            print(f" {i+1}. {s['name']} ({s.get('city', '')})")
        
        sel = input_safe("Select School #: ")
        if not sel or not sel.isdigit(): return
        idx = int(sel) - 1
        if idx < 0 or idx >= len(schools): return
        
        school_id = schools[idx]['id']
        slink = schools[idx].get('slink')
    else:
        print(f"Using configured School ID: {school_id}")
    
    user = CONFIG.get('SDUI_EMAIL')
    if not user: user = input_safe("Username/Email: ")
    
    pw = CONFIG.get('SDUI_PASSWORD')
    if not pw: pw = input_safe("Password: ")
    
    print("Logging in...")
    try:
        res = get_sdui_token(user, pw, school_id, slink)
        token = res.get('token')
        uid = res.get('user_id')
        
        if token and uid:
            print(f"\nSuccess! User ID: {uid}")
            CONFIG['SDUI_USER_ID'] = str(uid)
            CONFIG['SDUI_AUTH_TOKEN'] = f"Bearer {token}"
            CONFIG['SDUI_EMAIL'] = user
            CONFIG['SDUI_PASSWORD'] = pw
            CONFIG['SDUI_SCHOOL_ID'] = str(school_id)
            if slink: CONFIG['SDUI_SCHOOL_SLINK'] = slink
            save_env_file()
        else:
            log_msg("Login successful but token not found in response.", "ERROR")
    except Exception as e:
        log_msg(f"Login failed: {e}", "ERROR")

def run_setup_wizard():
    print("\n" + "!"*50 + "\n CONFIGURATION MISSING - SETUP WIZARD\n" + "!"*50)
    
    if input_safe("Do you want to login with Email/Password? (y/n): ").lower() == 'y':
        action_login()
        if CONFIG['SDUI_USER_ID'] and CONFIG['SDUI_AUTH_TOKEN']:
            print("\nSetup Complete!\n")
            time.sleep(1)
            return

    if not CONFIG['SDUI_USER_ID']:
        uid = input_safe("Enter your SDUI User ID (e.g. 557035): ")
        if uid: CONFIG['SDUI_USER_ID'] = uid
    if not CONFIG['SDUI_AUTH_TOKEN']:
        token = input_safe("Paste SDUI Token (starts with Bearer): ")
        if token:
            if not token.lower().startswith("bearer "): token = "Bearer " + token
            CONFIG['SDUI_AUTH_TOKEN'] = token
    save_env_file()
    print("\nSetup Complete!\n")
    time.sleep(1)

# --- GOOGLE AUTH (NO SAVING) ---
def get_calendar_service():
    global CACHED_SERVICE
    
    # 1. Use cached service if available (prevents login loop during same session)
    if CACHED_SERVICE:
        return CACHED_SERVICE

    # 2. Check for credentials.json
    if not os.path.exists(CREDENTIALS_FILE):
        log_msg(f"MISSING: {CREDENTIALS_FILE}", "ERROR")
        print(f"Please put {CREDENTIALS_FILE} in the 'auth' folder.")
        return None

    # 3. Determine Auth Type based on JSON content
    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            creds_data = json.load(f)
    except Exception as e:
        log_msg(f"Error reading credentials file: {e}", "ERROR")
        return None

    creds = None

    # A) Service Account Strategy
    if 'type' in creds_data and creds_data['type'] == 'service_account':
        log_msg("Authenticating with Service Account...", "INFO")
        try:
            creds = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        except Exception as e:
            log_msg(f"Service Account Auth Failed: {e}", "ERROR")
            return None

    # B) OAuth Client ID Strategy (User Flow)
    elif 'installed' in creds_data or 'web' in creds_data:
        log_msg("Authenticating with OAuth Client (User Flow)...", "INFO")
        if os.path.exists(TOKEN_FILE):
            try: creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except: os.remove(TOKEN_FILE)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try: creds.refresh(Request())
                except: creds = None
            
            if not creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                    creds = flow.run_local_server(port=0)
                    with open(TOKEN_FILE, 'w') as token: token.write(creds.to_json())
                except Exception as e:
                    log_msg(f"OAuth Login Failed: {e}", "ERROR")
                    return None
    else:
        log_msg("Unknown credentials format. Please use Service Account or OAuth Client ID JSON.", "ERROR")
        return None

    CACHED_SERVICE = build('calendar', 'v3', credentials=creds)
    return CACHED_SERVICE

# --- SDUI LOGIC ---
def get_sdui_data(start_date, end_date):
    token = CONFIG['SDUI_AUTH_TOKEN']
    uid = CONFIG['SDUI_USER_ID']
    if not token or not uid:
        log_msg("AUTH ERROR: Token missing.", "ERROR")
        return None
    
    headers = {'Authorization': token, 'User-Agent': 'Mozilla/5.0'}
    url = f"https://api.sdui.app/v1/timetables/users/{uid}/timetable?begins_at={start_date}&ends_at={end_date}"
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log_msg(f"SDUI API Error: {e}", "ERROR")
        return None

def process_sdui_data(sdui_data, only_changes=False):
    events = []
    if not sdui_data or 'data' not in sdui_data: return events
    lessons = sdui_data.get('data', {}).get('lessons', [])
    tz = pytz.timezone(CONFIG['TIMEZONE'])
    oftype_map = {
        "CANCLED": "❌ ", 
        "BOOKABLE_CHANGE": "⚠️ Room: ", 
        "SUBSTITUTION": "🔄 Sub: ", 
        "EXAM": "📝 Exam: ",
        "ADDITIONAL": "➕ ",
        "GRADE_MISSING": "🚫 Class: "
    }
    
    for lesson in lessons:
        kind = lesson.get('kind')
        oftype = lesson.get('oftype') or kind
        
        if only_changes:
            if kind not in ['HOLIDAY', 'EVENT'] and oftype not in oftype_map:
                continue

        color_id = '9'
        if kind in ['HOLIDAY', 'EVENT']:
            subj = (lesson.get('meta') or {}).get('displayname') or lesson.get('comment') or "Event"
            summary = f"🏖️ {subj}" if kind == 'HOLIDAY' else f"📅 {subj}"
            color_id = '10' if kind == 'HOLIDAY' else '3'
            description = f"Type: {kind}\nComment: {lesson.get('comment', '')}"
            location = ""
        else:
            display_name = ((lesson.get('course') or {}).get('meta') or {}).get('displayname', 'Unknown')

            # --- Subject Parsing & Styling ---
            subj = display_name  # Default subject name
            subj_emoji = '📚'   # Default emoji
            # color_id is already '9' from the outer scope

            # Heuristic to find subject key from displayname like '1_Ph5' or '1_geo_11a'
            parts = display_name.split('_')
            if len(parts) > 1:
                # The subject code is usually the first group of letters in the second part.
                # e.g., 'Ph' from 'Ph5' in '1_Ph5', or 'geo' from 'geo' in '1_geo_11a'
                potential_key = parts[1]
                match = re.match(r'([a-zA-Z]+)', potential_key)
                if match:
                    subj_key = match.group(1)
                    # If a mapping exists, use it for full name, emoji, and color
                    if subj_key in SUBJECT_CONFIG:
                        subj, subj_emoji, color_id = SUBJECT_CONFIG[subj_key]
                    else:
                        # Otherwise, use the extracted key as the subject name
                        subj = subj_key
                else:
                    subj = potential_key # Fallback if the second part doesn't start with letters

            teachers = [t['name'] for t in (lesson.get('teachers') or []) if 'name' in t]
            prefix = oftype_map.get(oftype, '')
            if not teachers and oftype != 'CANCLED':
                prefix = "🚫 " + prefix

            summary_parts = [prefix.strip(), subj_emoji, subj]
            summary = ' '.join(p for p in summary_parts if p)

            # Override color for special event types, as they are more important
            if oftype == 'EXAM': color_id = '11'
            elif oftype in ['SUBSTITUTION', 'BOOKABLE_CHANGE', 'ADDITIONAL']: color_id = '6'
            elif oftype in ['CANCLED', 'GRADE_MISSING']: color_id = '8'
            rooms = [b['name'] for b in (lesson.get('bookables') or []) if 'name' in b]
            location = ", ".join(rooms)
            description = f"Teacher: {', '.join(teachers)}\nType: {kind or oftype}"

        if lesson.get('begins_at') and lesson.get('ends_at'):
            events.append({
                'sdui_id': lesson.get('id'),
                'summary': summary,
                'start': datetime.fromtimestamp(lesson['begins_at'], tz).isoformat(),
                'end': datetime.fromtimestamp(lesson['ends_at'], tz).isoformat(),
                'location': location, 'description': description, 'colorId': color_id
            })
    return events

# --- ACTIONS ---
def action_sync(start, end):
    only_changes = CONFIG.get('SYNC_ONLY_CHANGES', 'false') == 'true'
    data = get_sdui_data(start, end)
    sdui_events = process_sdui_data(data, only_changes=only_changes)
    if not sdui_events:
        log_msg("No events found from SDUI.", "WARN")
        return

    service = get_calendar_service()
    if not service: return

    # Fetch existing events to check for duplicates/updates
    tz = pytz.timezone(CONFIG['TIMEZONE'])
    start_dt = tz.localize(datetime.combine(start, datetime.min.time())).isoformat()
    end_dt = tz.localize(datetime.combine(end, datetime.max.time())).isoformat()
    
    existing_events = []
    page_token = None
    while True:
        res = service.events().list(calendarId=CONFIG['GOOGLE_CALENDAR_ID'], timeMin=start_dt, timeMax=end_dt, singleEvents=True, pageToken=page_token).execute()
        existing_events.extend(res.get('items', []))
        page_token = res.get('nextPageToken')
        if not page_token: break

    # Map existing events by SDUI ID (if present) and Start Time
    id_map = {e['extendedProperties']['private']['sdui_id']: e for e in existing_events if 'extendedProperties' in e and 'private' in e['extendedProperties'] and 'sdui_id' in e['extendedProperties']['private']}
    time_map = {e['start']['dateTime']: e for e in existing_events if 'dateTime' in e.get('start', {})}

    log_msg(f"Syncing {len(sdui_events)} events...", "INFO")
    count_ins, count_upd = 0, 0

    for event in sdui_events:
        sdui_id = str(event['sdui_id'])
        body = {
            'summary': event['summary'], 'location': event['location'],
            'description': event['description'], 'colorId': event['colorId'],
            'start': {'dateTime': event['start'], 'timeZone': CONFIG['TIMEZONE']},
            'end': {'dateTime': event['end'], 'timeZone': CONFIG['TIMEZONE']},
            'extendedProperties': {'private': {'sdui_id': sdui_id}}
        }

        # Determine target: Match by ID first, then by Time (legacy fallback)
        target_id = None
        if sdui_id in id_map: target_id = id_map[sdui_id]['id']
        elif event['start'] in time_map and not time_map[event['start']].get('extendedProperties', {}).get('private', {}).get('sdui_id'):
            target_id = time_map[event['start']]['id']

        try:
            if target_id:
                service.events().update(calendarId=CONFIG['GOOGLE_CALENDAR_ID'], eventId=target_id, body=body).execute()
                print(f"  [~] Updated: {event['summary']}")
                count_upd += 1
            else:
                service.events().insert(calendarId=CONFIG['GOOGLE_CALENDAR_ID'], body=body).execute()
                print(f"  [+] Created: {event['summary']}")
                count_ins += 1
        except HttpError as e:
            if 'rate' in str(e).lower():
                time.sleep(2)
                if target_id: 
                    service.events().update(calendarId=CONFIG['GOOGLE_CALENDAR_ID'], eventId=target_id, body=body).execute()
                    count_upd += 1
                else: 
                    service.events().insert(calendarId=CONFIG['GOOGLE_CALENDAR_ID'], body=body).execute()
                    count_ins += 1
                print(f"  [R] Retry Success: {event['summary']}")
            else: log_msg(f"Err: {e}", "ERROR")
    log_msg(f"Done. Created {count_ins}, Updated {count_upd}.", "INFO")

def action_clear(start, end):
    service = get_calendar_service()
    if not service: return
    tz = pytz.timezone(CONFIG['TIMEZONE'])
    start_dt = tz.localize(datetime.combine(start, datetime.min.time())).isoformat()
    end_dt = tz.localize(datetime.combine(end, datetime.max.time())).isoformat()
    
    deleted = 0
    while True:
        res = service.events().list(calendarId=CONFIG['GOOGLE_CALENDAR_ID'], timeMin=start_dt, timeMax=end_dt, singleEvents=True).execute()
        events = res.get('items', [])
        if not events: break
        for e in events:
            try:
                service.events().delete(calendarId=CONFIG['GOOGLE_CALENDAR_ID'], eventId=e['id']).execute()
                print(f"  [-] Deleted: {e.get('summary')}")
                deleted += 1
            except: pass
    log_msg(f"Deleted {deleted} events.", "INFO")

# --- MENU ---
def main_menu():
    load_config()
    
    if CONFIG.get('SDUI_EMAIL') and CONFIG.get('SDUI_PASSWORD'):
        try:
            res = get_sdui_token(CONFIG['SDUI_EMAIL'], CONFIG['SDUI_PASSWORD'], CONFIG.get('SDUI_SCHOOL_ID'), CONFIG.get('SDUI_SCHOOL_SLINK'))
            token = res.get('token')
            CONFIG['SDUI_AUTH_TOKEN'] = f"Bearer {token}"
            if res.get('user_id'): CONFIG['SDUI_USER_ID'] = str(res['user_id'])
            log_msg("Auto-login successful. Token refreshed.", "INFO")
        except Exception as e:
            log_msg(f"Auto-login failed: {e}", "WARN")

    if not CONFIG['SDUI_AUTH_TOKEN'] or not CONFIG['SDUI_USER_ID']: run_setup_wizard()

    while True:

        mode = "Changes Only" if CONFIG.get('SYNC_ONLY_CHANGES') == 'true' else "All Events"
        print(f"\n SDUI SYNC | Year: {CONFIG['SYNC_YEAR']} | Mode: {mode}")
        print(" 1. Sync Today")
        print(" 2. Sync Specific Day")
        print(" 3. Sync Current Week")
        print(" 4. Sync Specific Week")
        print(" 5. Sync Multiple Weeks")
        print(" 6. Clear Calendar")
        print(" 7. Settings")
        print(" 8. Login with Password")
        print(" 0. Exit")
        
        opt = input_safe("\nSelect: ")
        if opt == '0': sys.exit(0)
        elif opt == '1': 
            t = datetime.now().date()
            action_sync(t, t)
        elif opt == '2':
            date_str = input_safe("Enter date (DDMM): ")
            if date_str:
                try:
                    d = datetime.strptime(f"{date_str}{CONFIG['SYNC_YEAR']}", "%d%m%Y").date()
                    action_sync(d, d)
                except ValueError:
                    log_msg("Invalid date format. Please use DDMM.", "ERROR")
        elif opt == '3':
            y, w, _ = datetime.now().isocalendar()
            s = datetime.fromisocalendar(y, w, 1).date()
            e = datetime.fromisocalendar(y, w, 7).date()
            action_sync(s, e)
        elif opt == '4':
            w = input_safe("Week #: ")
            if w and w.isdigit():
                s = datetime.fromisocalendar(int(CONFIG['SYNC_YEAR']), int(w), 1).date()
                e = datetime.fromisocalendar(int(CONFIG['SYNC_YEAR']), int(w), 7).date()
                action_sync(s, e)
        elif opt == '5':
            start_w = input_safe("Start Week #: ")
            end_w = input_safe("End Week #: ")
            if start_w and end_w and start_w.isdigit() and end_w.isdigit():
                sw = int(start_w)
                ew = int(end_w)
                if sw <= ew:
                    try:
                        s = datetime.fromisocalendar(int(CONFIG['SYNC_YEAR']), sw, 1).date()
                        e = datetime.fromisocalendar(int(CONFIG['SYNC_YEAR']), ew, 7).date()
                        action_sync(s, e)
                    except ValueError as err:
                        log_msg(f"Invalid week range: {err}", "ERROR")
                else:
                    log_msg("Start week must be less than or equal to end week.", "ERROR")
        elif opt == '6':
             print("Clear range (DDMM)...")
             s = input_safe("Start: ")
             e = input_safe("End: ")
             try: action_clear(datetime.strptime(f"{s}{CONFIG['SYNC_YEAR']}", "%d%m%Y").date(), datetime.strptime(f"{e}{CONFIG['SYNC_YEAR']}", "%d%m%Y").date())
             except: pass
        elif opt == '8':
            action_login()
        elif opt == '7':
            while True:
                print("\n --- SETTINGS ---")
                print(f" 1. Change Token (Current: {CONFIG['SDUI_AUTH_TOKEN'][:10]}...)")
                print(f" 2. Change Year (Current: {CONFIG['SYNC_YEAR']})")
                print(f" 3. Change Sync Mode (Current: {'Changes Only' if CONFIG.get('SYNC_ONLY_CHANGES') == 'true' else 'All Events'})")
                cal_id = CONFIG['GOOGLE_CALENDAR_ID']
                if len(cal_id) > 20: cal_id = cal_id[:17] + "..."
                print(f" 4. Change Calendar ID (Current: {cal_id})")
                print(" 0. Back")
                
                s_opt = input_safe("\nSelect: ")
                if s_opt == '0': break
                
                changed = False
                if s_opt == '1':
                    CONFIG['SDUI_AUTH_TOKEN'] = input_safe("New Token: ")
                    changed = True
                elif s_opt == '2':
                    CONFIG['SYNC_YEAR'] = input_safe("New Year (YYYY): ")
                    changed = True
                elif s_opt == '3':
                    val = input_safe("Sync only changes? (y/n): ")
                    CONFIG['SYNC_ONLY_CHANGES'] = 'true' if val == 'y' else 'false'
                    changed = True
                elif s_opt == '4':
                    CONFIG['GOOGLE_CALENDAR_ID'] = input_safe("New Calendar ID: ")
                    changed = True
                
                if changed: save_env_file()

if __name__ == "__main__":
    try: main_menu()
    except KeyboardInterrupt: pass