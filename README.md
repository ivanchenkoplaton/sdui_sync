SDUI to Google Calendar Sync Tool
=================================

This tool synchronizes your school timetable from the SDUI app directly to a Google Calendar. It supports regular lessons, substitutions, cancellations, exams, and school events.

⚠️ **SECURITY NOTICE**
---------
This tool requires authentication credentials to access your SDUI account and Google Calendar. Your credentials are stored **locally only** and never transmitted to external services.

**Important**:
- **Do NOT commit** `.env`, `auth/credentials.json`, or `auth/token.json` to version control
- The `.gitignore` file prevents accidental commits of sensitive files
- Always use `.env.example` as a template to create your `.env` file
- Treat your SDUI token as a password - never share it
- If you commit sensitive data by mistake, rotate your credentials immediately

Features
--------
- **Smart Sync**: Checks if events already exist to update them instead of creating duplicates.
- **Change Detection**: Option to sync only changes (substitutions, cancellations, exams) and ignore regular lessons.
- **Custom Styling**: Maps subjects (e.g., "Ph", "M") to specific colors and emojis in Google Calendar for better readability.
- **Event Prefixes**: Automatically adds prefixes like "❌" for cancellations, "🔄" for substitutions, or "🚫" if a teacher is missing.
- **Interactive CLI**: Easy-to-use command-line interface for selecting date ranges and settings.

Prerequisites
-------------
1. **Python 3.x** installed.
2. **Google Cloud Project** with the Calendar API enabled.
3. **SDUI Account** access (to retrieve User ID and Auth Token).

User Data Requirements
----------------------
To use this tool, you must provide the following sensitive information locally. **These files are protected by `.gitignore` and should never be committed to version control.**

1.  **`auth/credentials.json`** *(Required)*: Your Google Cloud OAuth 2.0 Client ID or Service Account key file.
2.  **`.env`** *(Required)*: A configuration file containing your SDUI credentials and settings.
   - **START HERE**: Copy `.env.example` to `.env` and fill in your actual values
   - Template: `cp .env.example .env`
3.  **`auth/token.json`** *(Auto-generated)*: Cached Google session token (created automatically, already in `.gitignore`)

### ⚠️ Protecting Your Credentials

Your `.env` file contains sensitive credentials. To ensure they're never accidentally committed:

- **Always verify** `.gitignore` is in place: `cat .gitignore | grep ".env"`
- **Never copy-paste** credentials into public repositories
- If you accidentally commit credentials:
  1. Remove the commit from history: `git filter-branch --tree-filter 'rm -f .env' HEAD`
  2. **Rotate your credentials** immediately on SDUI and Google
- For team environments, use environment variables instead of `.env` files

### Credentials File Format
The `auth/credentials.json` file should contain your Google OAuth 2.0 Client ID. It should look like this:

```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "YOUR_PROJECT_ID",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": ["http://localhost"]
  }
}
```

Installation & Setup
--------------------

### 1. Clone the Repository

```bash
git clone https://github.com/ivanchenkoplaton/sdui_sync.git
cd sdui_sync
```

### 2. Install Dependencies

Ensure you have Python 3.x installed. Then install required libraries:

```bash
pip install requests google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client pytz
```

### 3. Set Up Your Configuration

Create your `.env` file from the template:

```bash
cp .env.example .env
```

Then edit `.env` and fill in your credentials:
```bash
nano .env  # or use your preferred editor
```

### 4. Set Up Google Authentication

1. **Create a Google Cloud Project** (https://console.cloud.google.com/)
2. **Enable the Google Calendar API**
3. **Create OAuth 2.0 Client ID** or Service Account:
   - For **User Flow** (recommended): Download the Client ID JSON as `auth/credentials.json`
   - For **Service Account**: Download the Service Account JSON as `auth/credentials.json`
   - Share your target calendar with the Service Account email if using that method
4. **Create `auth/` directory**:
   ```bash
   mkdir -p auth
   ```

### 5. Get SDUI Credentials

Access SDUI in your browser and extract your credentials:
1. Open SDUI web app
2. Open **Developer Tools** (F12 → Network tab)
3. Look for requests to `api.sdui.app`
4. Find your **User ID** in the URL and **Token** in the `Authorization` header

Paste these into your `.env` file.

### 6. Run the Application

```bash
python cli.py
```

The setup wizard will guide you through any missing configuration on first run.

Usage
-----

Run the script using Python:

    python cli.py

### Main Menu Options

1. **Sync Today**: Syncs the timetable for the current day.
2. **Sync Specific Day**: Prompts for a date (DDMM format) to sync.
3. **Sync Current Week**: Syncs the current calendar week (Monday to Sunday).
4. **Sync Specific Week**: Prompts for a calendar week number (1-52) to sync.
5. **Clear Calendar**: Deletes all events created by this tool within a specified date range.
6. **Settings**: Configure global options.
   - **Change Token**: Update your SDUI Authorization Token.
   - **Change Year**: Set the target year for DDMM date inputs and week calculations.
   - **Change Sync Mode**: Toggle between "All Events" and "Changes Only".
   - **Change Calendar ID**: Set the target Google Calendar ID (default is 'primary' or a specific ID).
0. **Exit**: Closes the application.

Configuration
-------------

### Using `.env.example` Template

The easiest way to configure the tool is to use the provided `.env.example` template:

```bash
cp .env.example .env
# Then edit .env with your actual credentials
```

Available configuration variables:
- `SDUI_USER_ID`: Your numeric user ID from SDUI
- `SDUI_AUTH_TOKEN`: Your Bearer token (prefixed with "Bearer ")
- `SDUI_EMAIL`: Your SDUI login email (optional, for password-based auth)
- `SDUI_PASSWORD`: Your SDUI password (optional, for password-based auth)
- `SDUI_SCHOOL_ID`: Your school ID (optional, used for login)
- `SDUI_SCHOOL_SLINK`: Your school's unique link (optional)
- `GOOGLE_CALENDAR_ID`: Target calendar ID (default: "primary")
- `TIMEZONE`: Your timezone (default: "UTC", examples: "Europe/Berlin", "America/New_York")
- `SYNC_ONLY_CHANGES`: Set to "true" to skip regular lessons (default: "false")
- `SYNC_YEAR`: Year for date parsing in DDMM format (auto-set to current year)

### Interactive Configuration

On first run, the tool will launch a setup wizard if configuration is incomplete. You can also update settings anytime:

1. Run `python cli.py`
2. Select **Settings (7)** from the main menu
3. Choose what to change:
   - Change Token
   - Change Year
   - Change Sync Mode (All Events vs Changes Only)
   - Change Calendar ID

### Subject Styling (Advanced)
You can customize how subjects appear in the calendar by editing the `SUBJECT_CONFIG` dictionary in `cli.py`.

Format: `'Shortcut': ('Full Name', 'Emoji', 'ColorID')`

Example:
```python
SUBJECT_CONFIG = {
    'Ph': ('Physics', '⚛️', '9'),
    'M':  ('Math', '🧮', '4'),
}
```
*Google Calendar Color IDs range from 1 to 11.*

File Structure
--------------
```
sdui_sync/
├── cli.py                 # Main application script
├── README.md              # This documentation
├── .gitignore            # Git ignore file (protects sensitive data)
├── .env.example          # Template for configuration
├── .env                  # Your actual config (created from .env.example, protected by .gitignore)
└── auth/                 # Authentication files directory
    ├── credentials.json  # Your Google API credentials (protected by .gitignore)
    └── token.json       # Cached Google session (auto-generated, protected by .gitignore)
```

**Note**: Files listed in `.gitignore` are automatically excluded from git commits to prevent accidental credential leaks.

Troubleshooting
---------------

### Authentication Issues

**"AUTH ERROR: Token missing"**
- Ensure your `.env` file has `SDUI_AUTH_TOKEN` and `SDUI_USER_ID` filled in
- Use Settings (7) → Change Token to update an expired token
- Extract a fresh token from SDUI's Developer Tools (see "Get SDUI Credentials" above)

**"Login Failed" when using Email/Password**
- Ensure your SDUI email and password are correct in `.env`
- Some schools require additional setup - try using the token method instead
- Verify your school ID and slink are correct (optional fields)

### Google Calendar Issues

**"MISSING: auth/credentials.json"**
- Create the `auth/` directory: `mkdir -p auth`
- Download your Google credentials file and save as `auth/credentials.json`
- Ensure the JSON file is valid (copy from Google Cloud Console directly)

**"Calendar Not Updating" or "Permission Denied"**
- Verify `GOOGLE_CALENDAR_ID` is correct (check Google Calendar settings)
- If using Service Account: share the calendar with the service account email and grant "Make changes to events" permission
- If using OAuth: ensure the Google Cloud project has Calendar API enabled

**"Rate limit exceeded"**
- The tool automatically retries with delay, but reduce sync range if it persists
- Sync one week at a time instead of multiple weeks

### Date & Timezone Issues

**"Wrong dates in calendar"**
- Check `SYNC_YEAR` in Settings (7) - ensure it matches your school year
- Verify `TIMEZONE` in `.env` matches your location
- Use "Sync Specific Day" to test with known dates first

### Security & Credentials

**"I accidentally committed my credentials!"**
1. Stop - don't push to remote yet
2. Remove from git history:
   ```bash
   git filter-branch --tree-filter 'rm -f .env' HEAD
   git filter-branch --tree-filter 'rm -rf auth/' HEAD
   ```
3. **Immediately rotate your credentials**:
   - SDUI: Change your password
   - Google: Revoke the credentials in Google Cloud Console
4. Create new credentials and update your `.env` file

**How to keep credentials safe**
- Always use `.gitignore` (verified by: `cat .gitignore | grep .env`)
- Never paste credentials in chat, issues, or pull requests
- Use `.env.example` as a template for sharing configuration
- For team setups, use environment variables or secure vaults instead

### Performance Tips

- **"Sync is slow"**: Reduce the date range; sync smaller chunks (weeks instead of months)
- **"Too many events"**: Use Settings (7) → Change Sync Mode to "Changes Only"
- **"Calendar looks cluttered"**: Customize subject colors in Settings or edit `SUBJECT_CONFIG` in `cli.py`