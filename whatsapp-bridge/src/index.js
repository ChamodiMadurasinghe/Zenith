require('./loadEnv').loadEnv();

const fs = require('fs');
const path = require('path');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const { ensureQueueDir, processImageMessage, formatError } = require('./ingestHandler');
const { startSendServer } = require('./sendHandler');
const { acquireBridgeLock, releaseBridgeLock } = require('./sessionGuard');

ensureQueueDir();

const lock = acquireBridgeLock();
if (!lock.ok) {
  console.error(
    `[bridge] Another bridge instance is already running (PID ${lock.pid}).\n` +
      '[bridge] Stop it first (Ctrl+C in that terminal), then run npm start again.\n' +
      '[bridge] Or use the running instance — do not start a second copy.'
  );
  process.exit(1);
}

function resolveChromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) {
    return process.env.PUPPETEER_EXECUTABLE_PATH;
  }
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ];
  return candidates.find((p) => fs.existsSync(p));
}

const chromePath = resolveChromePath();
const puppeteerOptions = {
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
};
if (chromePath) {
  puppeteerOptions.executablePath = chromePath;
  console.log(`[bridge] using Chrome at ${chromePath}`);
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: './.wwebjs_auth' }),
  puppeteer: puppeteerOptions,
  webVersion: '2.3000.1046395181-alpha',
  webVersionCache: {
    type: 'remote',
    remotePath:
      'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/{version}.html',
    strict: false,
  },
  bypassCSP: true,
  takeoverOnConflict: true,
});

let loadingStuckTimer;
client.on('qr', (qr) => {
  console.log('[bridge] Scan QR code with WhatsApp (first time only):');
  qrcode.generate(qr, { small: true });
});

client.on('loading_screen', (percent, message) => {
  console.log(`[bridge] loading ${percent}% — ${message || 'WhatsApp Web'}`);
  if (percent >= 99) {
    clearTimeout(loadingStuckTimer);
    loadingStuckTimer = setTimeout(() => {
      console.warn(
        '[bridge] stuck at 99%? Run: npm run reset-session — then npm start and scan QR again'
      );
    }, 90000);
  }
});

client.on('change_state', (state) => {
  console.log(`[bridge] state: ${state}`);
});

client.on('disconnected', (reason) => {
  console.error('[bridge] disconnected:', reason);
});

client.on('authenticated', () => {
  console.log('[bridge] authenticated');
});

client.on('auth_failure', (msg) => {
  console.error('[bridge] auth failure:', msg);
});

async function catchUpUnreadImages(client) {
  const maxAttempts = 5;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const chats = await client.getChats();
      let processed = 0;
      for (const chat of chats) {
        if (!chat.unreadCount) continue;
        const limit = Math.min(chat.unreadCount + 20, 100);
        const messages = await chat.fetchMessages({ limit });
        const sorted = [...messages].sort((a, b) => a.timestamp - b.timestamp);
        for (const msg of sorted) {
          if (msg.fromMe) continue;
          try {
            await processImageMessage(msg, client);
            processed += 1;
          } catch (err) {
            console.error('[bridge] catch-up failed:', err.message || err);
          }
        }
      }
      console.log(`[bridge] catch-up complete (${processed} message(s) checked)`);
      return;
    } catch (err) {
      if (attempt < maxAttempts) {
        console.log(`[bridge] catch-up waiting for chat sync (${attempt}/${maxAttempts})…`);
        await new Promise((resolve) => setTimeout(resolve, 3000 * attempt));
        continue;
      }
      console.warn(
        `[bridge] catch-up skipped: ${err?.message || err}. ` +
          'New invoice photos still work — send one now to test.'
      );
    }
  }
}

client.on('ready', async () => {
  clearTimeout(loadingStuckTimer);
  const secret = process.env.WHATSAPP_BRIDGE_SECRET || '';
  if (!secret) {
    console.warn('[bridge] WHATSAPP_BRIDGE_SECRET is not set — ingest API calls will be rejected (401)');
  } else {
    console.log('[bridge] bridge secret loaded from .env');
  }
  console.log('[bridge] ready — listening for invoice photos');
  startSendServer(client);
  catchUpUnreadImages(client).catch((err) => {
    console.warn('[bridge] catch-up error:', err?.message || err);
  });
});

client.on('message_create', async (msg) => {
  if (msg.fromMe) return;
  try {
    await processImageMessage(msg, client);
  } catch (err) {
    console.error('[bridge] realtime ingest failed:', formatError(err));
  }
});

let shuttingDown = false;
async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`[bridge] shutting down (${signal})…`);
  try {
    await client.destroy();
  } catch (err) {
    console.warn('[bridge] destroy warning:', err.message || err);
  }
  releaseBridgeLock();
  process.exit(0);
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

client.initialize().catch((err) => {
  releaseBridgeLock();
  if ((err.message || '').includes('browser is already running')) {
    console.error(
      '[bridge] Chrome session is still open from a previous bridge run.\n' +
        '[bridge] Fix: close the other bridge terminal (Ctrl+C), or end leftover node/chrome\n' +
        '[bridge] processes tied to whatsapp-bridge/.wwebjs_auth/session, then npm start again.'
    );
  } else {
    console.error('[bridge] failed to start:', err.message || err);
  }
  process.exit(1);
});
