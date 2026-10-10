/**
 * Node-Media-Server + FFmpeg HLS
 *
 * NMS handles RTMP ingestion from OBS (port 1935) with built-in auth.
 * FFmpeg is spawned per stream to convert RTMP → HLS segments on disk.
 * FastAPI serves the HLS files and the web frontend.
 */

const NodeMediaServer = require('node-media-server');
const Database = require('better-sqlite3');
const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const DB_PATH = path.resolve(__dirname, '..', 'data', 'live_stream.db');
const HLS_ROOT = path.resolve(__dirname, '..', 'media', 'hls');
const FFMPEG =
  process.env.FFMPEG_PATH ||
  (process.platform === 'win32'
    ? 'C:/Program Files/ffmpeg/bin/ffmpeg'
    : 'ffmpeg');

// ── Sync database ────────────────────────────────────────────────────────

let db;
try {
  db = new Database(DB_PATH, { readonly: false });
  db.pragma('journal_mode = WAL');
  console.log(`[DB] Connected to ${DB_PATH}`);
} catch (err) {
  console.error(`[DB] FATAL: ${err.message}`);
  process.exit(1);
}

// ── Auth secret (push password hash from DB) ──────────────────────────────

function getPushPasswordHash() {
  try {
    const row = db
      .prepare("SELECT value FROM config WHERE key = 'push_password_hash'")
      .get();
    return row ? row.value : null;
  } catch {
    return null;
  }
}

const pushHash = getPushPasswordHash();
let authConfig = {};
if (pushHash) {
  authConfig = { play: false, publish: true, secret: pushHash };
  console.log('[AUTH] Publish auth enabled');
} else {
  console.warn('[AUTH] No push password in DB — run change_push_password.py');
}

// Refresh auth secret every 60 s
setInterval(() => {
  const h = getPushPasswordHash();
  if (h && nms && nms.config && nms.config.auth) {
    nms.config.auth.secret = h;
  }
}, 60_000);

// ── FFmpeg process tracking ─────────────────────────────────────────────

const ffmpegProcesses = new Map();

function startHls(streamName) {
  if (ffmpegProcesses.has(streamName)) return; // already running

  const outDir = path.join(HLS_ROOT, 'live', streamName);
  fs.mkdirSync(outDir, { recursive: true });

  const rtmpUrl = `rtmp://127.0.0.1:1935/live/${streamName}`;
  const indexM3u8 = path.join(outDir, 'index.m3u8');
  const segPattern = path.join(outDir, '%d.ts');

  const args = [
    '-i', rtmpUrl,
    '-c', 'copy',
    '-f', 'hls',
    '-hls_time', '2',
    '-hls_list_size', '6',
    '-hls_flags', 'delete_segments+append_list',
    '-hls_segment_filename', segPattern,
    indexM3u8,
  ];

  const proc = spawn(FFMPEG, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  proc.stdout.on('data', () => {}); // drain
  proc.stderr.on('data', () => {}); // drain (ffmpeg logs to stderr)

  proc.on('error', (err) => {
    console.error(`[FFMPEG] "${streamName}" error: ${err.message}`);
  });

  proc.on('exit', (code) => {
    console.log(`[FFMPEG] "${streamName}" exited (code ${code})`);
    ffmpegProcesses.delete(streamName);
  });

  ffmpegProcesses.set(streamName, proc);
  console.log(`[FFMPEG] Started for "${streamName}"`);
}

function stopHls(streamName) {
  const proc = ffmpegProcesses.get(streamName);
  if (!proc) return;
  proc.kill('SIGINT');
  // Give FFmpeg a moment to finalize the HLS segments, then force-kill
  setTimeout(() => {
    try { proc.kill('SIGKILL'); } catch {}
  }, 3000);
  ffmpegProcesses.delete(streamName);
  console.log(`[FFMPEG] Stopped for "${streamName}"`);
}

// ── NMS configuration ───────────────────────────────────────────────────

const config = {
  rtmp: {
    port: 1935,
    host: '::',
    chunk_size: 60000,
    gop_cache: true,
    ping: 30,
    ping_timeout: 60,
  },
  auth: authConfig,
};

const nms = new NodeMediaServer(config);

// ── Lifecycle hooks ──────────────────────────────────────────────────────

nms.on('postPublish', (id, StreamPath) => {
  const streamName = StreamPath.split('/').pop();
  console.log(`[STREAM] "${streamName}" is now live`);

  // Update DB
  try {
    const existing = db
      .prepare("SELECT id, status FROM streams WHERE name = ?")
      .get(streamName);
    if (!existing) {
      const salt = crypto.randomBytes(16).toString('hex');
      const defaultPwd = crypto.randomBytes(4).toString('hex');
      const hash = crypto
        .createHash('sha256')
        .update(salt + defaultPwd)
        .digest('hex');
      db.prepare(
        "INSERT INTO streams (name, view_password_hash, view_password_salt, status, started_at) VALUES (?, ?, ?, 'live', datetime('now'))"
      ).run(streamName, hash, salt);
      console.log(`[STREAM] Auto-created "${streamName}" (view pw: ${defaultPwd})`);
    } else if (existing.status === 'waiting') {
      db.prepare(
        "UPDATE streams SET status = 'live', started_at = datetime('now') WHERE name = ?"
      ).run(streamName);
    } else if (existing.status !== 'live') {
      db.prepare(
        "UPDATE streams SET status = 'live', started_at = datetime('now') WHERE name = ?"
      ).run(streamName);
    }
  } catch (err) {
    console.error('[DB]', err.message);
  }

  // Start HLS transcoding
  startHls(streamName);
});

nms.on('donePublish', (id, StreamPath) => {
  const streamName = StreamPath.split('/').pop();
  console.log(`[STREAM] "${streamName}" has ended`);

  // Stop FFmpeg
  stopHls(streamName);

  // Update DB
  try {
    db.prepare(
      "UPDATE streams SET status = 'ended', ended_at = datetime('now') WHERE name = ?"
    ).run(streamName);
  } catch (err) {
    console.error('[DB]', err.message);
  }
});

// ── Start ────────────────────────────────────────────────────────────────

nms.run();
console.log('[Media-Server] RTMP  : rtmp://0.0.0.0:1935/live');
console.log('[Media-Server] FFmpeg:', FFMPEG);
console.log('[Media-Server] HLS   : →', HLS_ROOT + '/live/{stream}/index.m3u8');

// ── Cleanup on exit ──────────────────────────────────────────────────────

function cleanup() {
  console.log('[Media-Server] Shutting down…');
  for (const [name, proc] of ffmpegProcesses) {
    try { proc.kill('SIGKILL'); } catch {}
  }
  ffmpegProcesses.clear();
}

process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(0); });
process.on('SIGTERM', () => { cleanup(); process.exit(0); });
