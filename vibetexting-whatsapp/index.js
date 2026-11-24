#!/usr/bin/env node
/**
 * VibeTexting WhatsApp bridge
 * ---------------------------
 * A local-only HTTP bridge that links WhatsApp as a companion device
 * (multi-device protocol) and exposes chats / messages / sending to the
 * Python provider. Nothing is sent anywhere except to WhatsApp itself.
 *
 * Endpoints (bound to 127.0.0.1 by default):
 *   GET  /health                       -> link status + QR when unlinked
 *   GET  /chats?limit=50               -> recent conversations
 *   GET  /messages?chat_id=..&limit=20 -> recent messages for one chat
 *   GET  /search?chat_id=..&q=..&limit=5
 *   POST /send   {chat_id, text}
 *   POST /logout                       -> unlink this device
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  downloadMediaMessage,
} = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');

const DATA_DIR =
  process.env.VIBETEXTING_DATA_DIR || path.join(os.homedir(), '.vibetexting');
const AUTH_DIR =
  process.env.VIBETEXTING_WHATSAPP_AUTH_DIR || path.join(DATA_DIR, 'whatsapp_auth');
const STORE_FILE = path.join(DATA_DIR, 'whatsapp_messages.jsonl');
const MEDIA_DIR = path.join(DATA_DIR, 'whatsapp_media');
const PORT = Number(process.env.VIBETEXTING_WHATSAPP_PORT || 8787);
const HOST = process.env.VIBETEXTING_WHATSAPP_HOST || '127.0.0.1';

const MAX_PER_CHAT = 500;
const MAX_STORE_LINES = 20000;
const MAX_MEDIA_BYTES = 8 * 1024 * 1024;
const MAX_BODY_BYTES = 1024 * 1024;

for (const dir of [DATA_DIR, AUTH_DIR, MEDIA_DIR]) {
  fs.mkdirSync(dir, { recursive: true });
}

// Baileys expects a pino-like logger. Keep it silent: stdout is for operators.
const silent = {
  level: 'silent',
  child() {
    return silent;
  },
  trace() {},
  debug() {},
  info() {},
  warn() {},
  error() {},
  fatal() {},
};

const status = {
  connected: false,
  me: null,
  qr: null,
  qr_ascii: null,
  error: null,
  loggedOut: false,
  startedAt: new Date().toISOString(),
};

/** @type {any} */
let sock = null;

/** chat jid -> [{id, chat_id, ts, from_me, sender, text, media_path}] */
const messagesByChat = new Map();
const seenMessageIds = new Set();
/** chat jid -> {chat_id, label, is_group, participant_count, last_ts, subject, participants} */
const chatMeta = new Map();
/** contact jid -> display name */
const contactNames = new Map();
const groupMetaPending = new Map();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toSeconds(value) {
  if (value === null || value === undefined) return 0;
  if (typeof value === 'number') return Math.floor(value);
  if (typeof value.toNumber === 'function') return Math.floor(value.toNumber());
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.floor(parsed) : 0;
}

function jidNumber(jid) {
  const user = String(jid || '').split('@')[0].split(':')[0];
  if (/^\d{6,}$/.test(user)) return `+${user}`;
  return user || String(jid || 'unknown');
}

function isGroupJid(jid) {
  return String(jid || '').endsWith('@g.us');
}

function defaultLabel(jid) {
  return isGroupJid(jid) ? `Group ${jidNumber(jid)}` : jidNumber(jid);
}

function sanitizeFilename(value) {
  return String(value || 'media').replace(/[^A-Za-z0-9_-]/g, '_');
}

function ensureChat(jid) {
  let meta = chatMeta.get(jid);
  if (!meta) {
    meta = {
      chat_id: jid,
      label: defaultLabel(jid),
      is_group: isGroupJid(jid),
      participant_count: 0,
      last_ts: 0,
      subject: null,
      participants: [],
    };
    chatMeta.set(jid, meta);
  }
  return meta;
}

function rememberContact(contact) {
  if (!contact || !contact.id) return;
  const name = contact.name || contact.notify || contact.verifiedName;
  if (!name) return;
  contactNames.set(contact.id, name);
  const existing = chatMeta.get(contact.id);
  if (existing) existing.label = name;
}

function unwrapMessageContent(content) {
  if (!content) return content;
  if (content.ephemeralMessage?.message) {
    return unwrapMessageContent(content.ephemeralMessage.message);
  }
  if (content.viewOnceMessage?.message) {
    return unwrapMessageContent(content.viewOnceMessage.message);
  }
  if (content.viewOnceMessageV2?.message) {
    return unwrapMessageContent(content.viewOnceMessageV2.message);
  }
  if (content.documentWithCaptionMessage?.message) {
    return unwrapMessageContent(content.documentWithCaptionMessage.message);
  }
  if (content.editedMessage?.message) {
    return unwrapMessageContent(content.editedMessage.message);
  }
  return content;
}

function extractText(content) {
  if (!content) return '';
  if (content.conversation) return content.conversation;
  if (content.extendedTextMessage?.text) return content.extendedTextMessage.text;
  if (content.imageMessage) return content.imageMessage.caption || '[Image]';
  if (content.videoMessage) return content.videoMessage.caption || '[Video]';
  if (content.audioMessage) return '[Voice note]';
  if (content.stickerMessage) return '[Sticker]';
  if (content.documentMessage) return '[Document]';
  if (content.locationMessage) return '[Location]';
  if (content.contactMessage || content.contactsArrayMessage) return '[Contact card]';
  if (content.pollCreationMessage || content.pollCreationMessageV3) return '[Poll]';
  return '';
}

async function qrToAscii(qr) {
  return new Promise((resolve) => {
    qrcode.generate(qr, { small: true }, (ascii) => resolve(ascii));
  });
}

async function refreshGroupMeta(jid) {
  if (!isGroupJid(jid) || !sock) return;
  const meta = ensureChat(jid);
  if (meta.subject) return;
  if (groupMetaPending.has(jid)) return groupMetaPending.get(jid);

  const pending = (async () => {
    try {
      const info = await sock.groupMetadata(jid);
      if (info) {
        meta.subject = info.subject || null;
        meta.participants = (info.participants || []).map((p) => p.id);
        meta.participant_count = meta.participants.length;
        if (info.subject) meta.label = info.subject;
      }
    } catch (err) {
      // Group metadata is best-effort: subjects are also available from history.
    } finally {
      groupMetaPending.delete(jid);
    }
  })();

  groupMetaPending.set(jid, pending);
  return pending;
}

async function downloadImageFor(msg, content, id) {
  try {
    const size = Number(content.imageMessage?.fileLength || 0);
    if (size && size > MAX_MEDIA_BYTES) return null;

    const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: silent });
    if (!buffer || !buffer.length || buffer.length > MAX_MEDIA_BYTES) return null;

    const mime = String(content.imageMessage?.mimetype || 'image/jpeg');
    const ext = mime.includes('png') ? '.png' : mime.includes('webp') ? '.webp' : '.jpg';
    const file = path.join(MEDIA_DIR, `${sanitizeFilename(id)}${ext}`);
    await fs.promises.writeFile(file, buffer);
    return file;
  } catch (err) {
    return null;
  }
}

function addEntry(entry, { persist = true } = {}) {
  const chatId = entry.chat_id;
  if (!chatId) return;

  const dedupeKey = `${chatId}:${entry.id}`;
  if (seenMessageIds.has(dedupeKey)) return;
  seenMessageIds.add(dedupeKey);

  const list = messagesByChat.get(chatId) || [];
  list.push(entry);
  if (list.length > MAX_PER_CHAT) list.splice(0, list.length - MAX_PER_CHAT);
  messagesByChat.set(chatId, list);

  const meta = ensureChat(chatId);
  if (entry.ts > meta.last_ts) meta.last_ts = entry.ts;
  if (meta.is_group && !meta.participant_count) meta.participant_count = 2;

  if (persist) {
    fs.promises
      .appendFile(STORE_FILE, `${JSON.stringify(entry)}\n`)
      .catch(() => {});
  }
}

function loadStore() {
  if (!fs.existsSync(STORE_FILE)) return;
  let lines = [];
  try {
    lines = fs.readFileSync(STORE_FILE, 'utf8').split('\n').slice(-MAX_STORE_LINES);
  } catch (err) {
    return;
  }
  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      addEntry(JSON.parse(line), { persist: false });
    } catch (err) {
      // Skip corrupt lines rather than failing the whole bridge.
    }
  }
  for (const [jid, list] of messagesByChat) {
    list.sort((a, b) => a.ts - b.ts);
    const meta = ensureChat(jid);
    const last = list[list.length - 1];
    if (last && last.ts > meta.last_ts) meta.last_ts = last.ts;
  }
}

async function ingestMessage(msg, { download = true } = {}) {
  const jid = msg?.key?.remoteJid;
  if (!jid || jid === 'status@broadcast') return;

  const content = unwrapMessageContent(msg.message);
  const text = extractText(content).replace(/\uFFFC/g, '').trim();
  if (!text) return;

  const ts = toSeconds(msg.messageTimestamp) || Math.floor(Date.now() / 1000);
  const id = msg.key.id || `${jid}:${ts}:${text.slice(0, 24)}`;
  const dedupeKey = `${jid}:${id}`;
  if (seenMessageIds.has(dedupeKey)) return;

  const fromMe = Boolean(msg.key.fromMe);
  const senderJid = msg.key.participant || jid;
  const sender = fromMe
    ? 'Me'
    : msg.pushName || contactNames.get(senderJid) || jidNumber(senderJid);

  const entry = {
    id,
    chat_id: jid,
    ts,
    from_me: fromMe,
    sender,
    text,
  };

  if (download && content.imageMessage) {
    const mediaPath = await downloadImageFor(msg, content, id);
    if (mediaPath) entry.media_path = mediaPath;
  }

  addEntry(entry);
}

function clampInt(value, fallback, min, max) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function chatList(limit) {
  const all = [...chatMeta.values()];
  all.sort((a, b) => (b.last_ts || 0) - (a.last_ts || 0));
  return all.slice(0, limit);
}

function searchChat(chatId, query, limit) {
  const tokens = String(query || '')
    .toLowerCase()
    .split(/\s+/)
    .map((token) => token.replace(/[^a-z0-9']/g, ''))
    .filter((token) => token.length > 2);
  if (!tokens.length) return [];

  const entries = messagesByChat.get(chatId) || [];
  const scored = [];
  for (const entry of entries) {
    const haystack = String(entry.text || '').toLowerCase();
    let score = 0;
    for (const token of tokens) {
      if (haystack.includes(token)) score += 1;
    }
    if (score > 0) scored.push({ entry, score });
  }
  scored.sort((a, b) => b.score - a.score || b.entry.ts - a.entry.ts);
  return scored.slice(0, limit).map((item) => item.entry);
}

// ---------------------------------------------------------------------------
// WhatsApp connection
// ---------------------------------------------------------------------------

async function connect() {
  const { state: authState, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  sock = makeWASocket({
    auth: authState,
    logger: silent,
    printQRInTerminal: false,
    syncFullHistory: true,
    markOnlineOnConnect: false,
    generateHighQualityLinkPreview: false,
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      status.connected = false;
      status.qr = qr;
      status.qr_ascii = await qrToAscii(qr);
      console.log('\n[whatsapp] Scan this QR with WhatsApp > Linked devices > Link a device:\n');
      console.log(status.qr_ascii);
    }

    if (connection === 'open') {
      status.connected = true;
      status.qr = null;
      status.qr_ascii = null;
      status.error = null;
      status.loggedOut = false;
      status.me = {
        id: sock.user?.id || null,
        name: sock.user?.name || sock.user?.verifiedName || null,
      };
      console.log(`[whatsapp] linked as ${status.me.id || 'unknown'}`);
    }

    if (connection === 'close') {
      status.connected = false;
      const code = lastDisconnect?.error?.output?.statusCode;
      status.error = lastDisconnect?.error?.message || `closed (${code ?? 'unknown'})`;
      console.log(`[whatsapp] connection closed: ${status.error}`);

      if (code === DisconnectReason.loggedOut) {
        status.loggedOut = true;
        console.log('[whatsapp] device was unlinked; run again and scan a new QR code.');
        return;
      }
      setTimeout(() => {
        connect().catch((err) => {
          status.error = String(err?.message || err);
          console.error('[whatsapp] reconnect failed:', status.error);
        });
      }, 3000);
    }
  });

  sock.ev.on('messages.upsert', async ({ messages }) => {
    for (const msg of messages || []) {
      try {
        await ingestMessage(msg);
        await refreshGroupMeta(msg?.key?.remoteJid);
      } catch (err) {
        console.error('[whatsapp] failed to ingest message:', err?.message || err);
      }
    }
  });

  sock.ev.on('messaging-history.set', async ({ messages, contacts, chats }) => {
    for (const contact of contacts || []) rememberContact(contact);
    for (const chat of chats || []) {
      if (!chat?.id) continue;
      const meta = ensureChat(chat.id);
      if (chat.name) meta.label = chat.name;
      if (chat.subject) {
        meta.subject = chat.subject;
        meta.label = chat.subject;
      }
    }
    for (const msg of (messages || []).slice(-3000)) {
      try {
        await ingestMessage(msg, { download: false });
      } catch (err) {
        // Ignore individual history failures.
      }
    }
    console.log(`[whatsapp] history synced (${(messages || []).length} messages)`);
  });

  sock.ev.on('contacts.upsert', (contacts) => {
    for (const contact of contacts || []) rememberContact(contact);
  });

  sock.ev.on('contacts.update', (contacts) => {
    for (const contact of contacts || []) rememberContact(contact);
  });
}

// ---------------------------------------------------------------------------
// HTTP API
// ---------------------------------------------------------------------------

function sendJson(res, code, payload) {
  const body = JSON.stringify(payload ?? {});
  res.writeHead(code, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > MAX_BODY_BYTES) {
        reject(new Error('request body too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!raw.trim()) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch (err) {
        reject(new Error('invalid JSON body'));
      }
    });
    req.on('error', reject);
  });
}

async function handle(req, res) {
  const url = new URL(req.url, `http://${HOST}:${PORT}`);

  if (req.method === 'GET' && url.pathname === '/health') {
    return sendJson(res, 200, {
      ok: true,
      connected: status.connected,
      me: status.me,
      qr: status.qr,
      qr_ascii: status.qr_ascii,
      error: status.error,
      logged_out: status.loggedOut,
      started_at: status.startedAt,
    });
  }

  if (req.method === 'GET' && url.pathname === '/chats') {
    const limit = clampInt(url.searchParams.get('limit'), 50, 1, 200);
    const chats = chatList(limit);
    await Promise.all(chats.map((chat) => refreshGroupMeta(chat.chat_id)));
    return sendJson(
      res,
      200,
      chats.map((chat) => ({
        chat_id: chat.chat_id,
        label: chat.label,
        is_group: chat.is_group,
        participant_count: chat.participant_count,
        last_ts: chat.last_ts,
      }))
    );
  }

  if (req.method === 'GET' && url.pathname === '/messages') {
    const chatId = url.searchParams.get('chat_id');
    if (!chatId) return sendJson(res, 400, { error: 'chat_id is required' });

    const limit = clampInt(url.searchParams.get('limit'), 20, 1, MAX_PER_CHAT);
    await refreshGroupMeta(chatId);

    const entries = messagesByChat.get(chatId) || [];
    const meta = ensureChat(chatId);
    const sliced = entries.slice(-limit);

    return sendJson(res, 200, {
      chat_id: chatId,
      label: meta.label,
      is_group: meta.is_group,
      participant_count: meta.participant_count,
      participants: (meta.participants || []).slice(0, 12),
      total_count: entries.length,
      last_is_from_me: sliced.length ? Boolean(sliced[sliced.length - 1].from_me) : false,
      messages: sliced.map((entry) => ({
        id: entry.id,
        ts: entry.ts,
        from_me: Boolean(entry.from_me),
        sender: entry.sender,
        text: entry.text,
        media_path: entry.media_path || null,
      })),
    });
  }

  if (req.method === 'GET' && url.pathname === '/search') {
    const chatId = url.searchParams.get('chat_id');
    const query = url.searchParams.get('q');
    if (!chatId) return sendJson(res, 400, { error: 'chat_id is required' });

    const limit = clampInt(url.searchParams.get('limit'), 5, 1, 50);
    const matches = searchChat(chatId, query, limit).sort((a, b) => a.ts - b.ts);
    return sendJson(res, 200, {
      chat_id: chatId,
      messages: matches.map((entry) => ({
        id: entry.id,
        ts: entry.ts,
        from_me: Boolean(entry.from_me),
        sender: entry.sender,
        text: entry.text,
      })),
    });
  }

  if (req.method === 'POST' && url.pathname === '/send') {
    if (!status.connected || !sock) {
      return sendJson(res, 503, { error: 'WhatsApp is not linked yet' });
    }
    const body = await readJsonBody(req);
    const chatId = String(body.chat_id || '').trim();
    const text = String(body.text || '');
    if (!chatId.includes('@')) {
      return sendJson(res, 400, { error: 'chat_id must be a WhatsApp jid (user@s.whatsapp.net)' });
    }
    if (!text.trim()) return sendJson(res, 400, { error: 'text is required' });

    const sent = await sock.sendMessage(chatId, { text });
    if (sent) {
      try {
        await ingestMessage(sent, { download: false });
      } catch (err) {
        // The message is already sent; failing to store it is not fatal.
      }
    }
    return sendJson(res, 200, { ok: true });
  }

  if (req.method === 'POST' && url.pathname === '/logout') {
    if (sock) {
      try {
        await sock.logout();
      } catch (err) {
        // Ignore: logout still clears local state below.
      }
    }
    status.connected = false;
    status.me = null;
    status.loggedOut = true;
    return sendJson(res, 200, { ok: true });
  }

  return sendJson(res, 404, { error: 'not found' });
}

loadStore();
connect().catch((err) => {
  status.error = String(err?.message || err);
  console.error('[whatsapp] failed to start connection:', status.error);
});

const server = http.createServer((req, res) => {
  handle(req, res).catch((err) => {
    console.error('[whatsapp] request failed:', err?.message || err);
    if (!res.headersSent) sendJson(res, 500, { error: String(err?.message || err) });
  });
});

server.listen(PORT, HOST, () => {
  console.log(`[whatsapp] bridge listening on http://${HOST}:${PORT}`);
});

function shutdown() {
  console.log('\n[whatsapp] shutting down');
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 2000);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
