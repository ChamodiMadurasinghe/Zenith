const fs = require('fs');
const path = require('path');
const { downloadMediaWithRetry } = require('./mediaDownload');

const INGEST_URL = process.env.ZENITH_INGEST_URL || 'http://127.0.0.1:5000/api/invoices/ingest';
const BRIDGE_SECRET = process.env.WHATSAPP_BRIDGE_SECRET || '';
const QUEUE_DIR = path.resolve(
  process.env.INBOUND_QUEUE_DIR || path.join(__dirname, '..', '..', 'data', 'inbound_queue')
);
const PHOTO_ACK_MESSAGE =
  process.env.WHATSAPP_PHOTO_ACK_MESSAGE || 'Photo received (Zenith test).';

function ensureQueueDir() {
  fs.mkdirSync(QUEUE_DIR, { recursive: true });
}

function isPhotoAckEnabled() {
  const raw = process.env.WHATSAPP_PHOTO_ACK;
  if (raw === undefined || raw === '') return true;
  return !['0', 'false', 'no', 'off'].includes(String(raw).trim().toLowerCase());
}

function normalizePhone(raw) {
  const digits = String(raw || '').replace(/\D/g, '');
  return digits ? `+${digits}` : String(raw || '').trim();
}

function senderFromMessage(msg) {
  if (msg.author) {
    return normalizePhone(msg.author);
  }
  const from = String(msg.from || '');
  if (from.endsWith('@c.us')) {
    return normalizePhone(from.replace('@c.us', ''));
  }
  return normalizePhone(from);
}

async function postIngest(payload) {
  const headers = { 'Content-Type': 'application/json' };
  if (BRIDGE_SECRET) {
    headers['X-Zenith-Bridge-Token'] = BRIDGE_SECRET;
  }

  let lastError;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const resp = await fetch(INGEST_URL, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      const text = await resp.text();
      let body = {};
      try {
        body = text ? JSON.parse(text) : {};
      } catch {
        body = { raw: text };
      }
      if (resp.status >= 200 && resp.status < 300) {
        return { ok: true, status: resp.status, body };
      }
      if (resp.status >= 500) {
        lastError = new Error(`HTTP ${resp.status}: ${text}`);
        await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
        continue;
      }
      return { ok: false, status: resp.status, body };
    } catch (err) {
      lastError = err;
      await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
    }
  }
  throw lastError || new Error('ingest failed');
}

function isIngestibleImage(msg, media) {
  if (!msg.hasMedia) return false;
  if (msg.type === 'image') return true;
  const mime = (media && media.mimetype) || '';
  return msg.type === 'document' && mime.startsWith('image/');
}

function formatError(err) {
  if (!err) return 'unknown error';
  if (typeof err === 'string') return err;
  if (err.message) return err.message;
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

async function sendPhotoAck(msg, sender, pipelineStatus) {
  if (!isPhotoAckEnabled()) return;
  try {
    await msg.reply(PHOTO_ACK_MESSAGE);
    console.log(`[bridge] photo ack sent to ${sender} -> ${pipelineStatus || 'ok'}`);
  } catch (err) {
    console.warn('[bridge] photo ack failed:', err.message || err);
  }
}

async function processImageMessage(msg, client) {
  const waMsgId = msg.id?._serialized || 'unknown';
  const sender = senderFromMessage(msg);

  if (!msg.hasMedia) {
    console.log(`[bridge] skip ${waMsgId}: no media (type=${msg.type})`);
    return null;
  }

  console.log(`[bridge] photo received ${waMsgId} type=${msg.type} from ${sender}`);
  ensureQueueDir();
  await new Promise((resolve) => setTimeout(resolve, 2000));
  const media = await downloadMediaWithRetry(msg, client);

  if (!isIngestibleImage(msg, media)) {
    console.log(
      `[bridge] skip ${waMsgId}: not an image (type=${msg.type}, mimetype=${media.mimetype || 'unknown'})`
    );
    return null;
  }

  const ext = (media.mimetype || '').includes('png') ? '.png' : '.jpg';
  const filePath = path.join(QUEUE_DIR, `${waMsgId}${ext}`);
  fs.writeFileSync(filePath, Buffer.from(media.data, 'base64'));

  const payload = {
    whatsapp_message_id: waMsgId,
    sender_phone: sender,
    timestamp: new Date((msg.timestamp || 0) * 1000).toISOString(),
    image_path: filePath,
  };

  const result = await postIngest(payload);
  if (result.ok) {
    try {
      const chat = await msg.getChat();
      await chat.sendSeen();
    } catch (err) {
      console.warn('[bridge] sendSeen failed:', formatError(err));
    }
    const pipelineStatus = result.body.status || 'ok';
    console.log(`[bridge] ingested ${waMsgId} -> ${pipelineStatus}`);
    if (pipelineStatus === 'ignored_sender') {
      console.warn(`[bridge] sender ${sender} not whitelisted — add in app → WhatsApp settings`);
    }
    await sendPhotoAck(msg, sender, pipelineStatus);
  } else {
    console.warn(`[bridge] ingest rejected ${waMsgId}: HTTP ${result.status}`, result.body);
  }
  return result;
}

module.exports = {
  QUEUE_DIR,
  ensureQueueDir,
  processImageMessage,
  postIngest,
  normalizePhone,
  isPhotoAckEnabled,
  sendPhotoAck,
  formatError,
};
