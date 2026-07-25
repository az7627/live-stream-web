# Live Stream Web

[简体中文（中国大陆）](README.md) / English (US)

A self-hosted live streaming platform with password-protected viewing, OBS
push, and danmaku (bullet chat). Built with Python FastAPI + Node-Media-Server.

## Architecture

```
OBS ──RTMP──→ Node-Media-Server (:1935) ──HLS──→ FastAPI (:443) ←── Browser
                      │                                  │
                      └── auth callback → /api/validate_push
```

- **Backend**: Python FastAPI (HTTPS on :443)
- **Media Server**: Node-Media-Server (RTMP on :1935, HLS generation)
- **Frontend**: Dark-blue themed HTML/CSS/JS with canvas-based danmaku
- **Auth**: Salted SHA256 for both push password and viewing passwords

## Prerequisites

| Software   | Notes                                    |
| ---------- | ---------------------------------------- |
| Python 3.10+ | [python.org](https://python.org)       |
| Node.js 18+  | [nodejs.org](https://nodejs.org)      |
| OBS Studio  | [obsproject.com](https://obsproject.com) |
| SSL Certificates | In `C:\Users\a233d\Documents\cert` (`az7627.top.pem` + `az7627.top.key`) |

## Quick Start

### 1. Install dependencies

```bash
# Python
pip install -r backend\requirements.txt

# Node (media server)
cd media-server
npm install
cd ..
```

### 2. Set the push password

Run the script _before_ starting the server (or any time you want to change it):

```bash
python change_push_password.py
```

You'll be prompted for the new password. This is the password streamers enter
in OBS. It is stored as salt + SHA256 — never in plaintext.

### 3. Start the server

```bash
python start.py
```

This launches both the FastAPI web backend (HTTPS :443) and the
Node-Media-Server (RTMP :1935). Press Ctrl+C to stop both.

### 4. Create a stream

1. Open **https://localhost** in your browser.
2. Click **"Go Live"**.
3. Enter a **stream name** (e.g. `my-broadcast`) and click **Check**.
4. Set a **viewing password** (viewers need this to watch).
5. Click **"Start Stream"**.
6. The page will show the OBS settings. Copy them.

### 5. Configure OBS

| Setting      | Value                                                       |
| ------------ | ----------------------------------------------------------- |
| Service      | Custom…                                                     |
| Server       | `rtmp://YOUR_SERVER_IP/live`                                |
| Stream Key   | `your-stream-name`                                          |

> **Important**: In OBS → Advanced → Network, you may also pass the push
> password in the stream key as:
> `your-stream-name?password=YOUR_PUSH_PASSWORD`

The **server** field is `rtmp://` followed by your domain or IP, then `/live`.
The **stream key** is whatever name you entered on the web page.

To include the push password, append `?password=xxx` to the stream key.
Example: `my-broadcast?password=secret123`.

After clicking "Start Streaming" in OBS, the stream will appear on the home
page as "LIVE".

### 6. Watch & danmaku

1. On the home page, click **"Watch"** next to a stream.
2. Enter the **viewing password** (the one set during stream creation).
3. The video loads automatically when the stream goes live.
4. Type in the danmaku bar and hit Enter to send bullet comments!

## Changing the push password

```bash
python change_push_password.py
```

This updates the server-wide push password. All streamers must use the new
password going forward. The script stores salt + SHA256 in the database —
the plaintext password is never written to disk.

## File structure

```
live-stream-web/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── auth.py              # Salted SHA256 utilities
│   └── requirements.txt     # Python dependencies
├── media-server/
│   ├── server.js            # Node-Media-Server config
│   └── package.json         # npm dependencies
├── frontend/
│   ├── index.html           # Home page (stream list)
│   ├── go-live.html         # Stream creation + OBS instructions
│   ├── watch.html           # Video player + danmaku
│   ├── css/style.css        # Dark blue theme
│   └── js/
│       ├── app.js           # Shared API helpers
│       └── danmaku.js       # Canvas-based bullet chat
├── data/
│   └── live_stream.db       # SQLite database (auto-created)
├── media/hls/               # HLS segments (auto-created)
├── change_push_password.py  # Push password management
├── start.py                 # Unified launcher
└── README.md
```

## Security notes

- **Viewing passwords** are set per-stream by the stream creator, stored as
  salt + SHA256.
- **Push password** is a single server-wide secret, also stored as salt +
  SHA256.
- The `change_push_password.py` script never logs or prints the password.
- HTTPS is required for the web interface. The media server uses a local
  HTTP connection for internal auth callbacks only.
- Danmaku (WebSocket) is available to anyone who knows the viewing
  password — no additional authentication.

## Troubleshooting

| Symptom                          | Likely fix                                        |
| -------------------------------- | ------------------------------------------------- |
| Browser shows "Connection refused" | Check the server is running (`python start.py`) |
| OBS cannot connect               | Ensure port 1935 is open in firewall              |
| "Push password not configured"   | Run `python change_push_password.py`              |
| "Stream not found"               | Create the stream via the web UI first            |
| Video doesn't play in browser    | Check that OBS is actually pushing (RTMP status)  |
| Mixed content warning            | Ensure all URLs use HTTPS (HLS is proxied)        |
