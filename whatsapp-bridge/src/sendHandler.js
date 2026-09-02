const http = require('http');
const { normalizePhone } = require('./ingestHandler');

function startSendServer(client, options = {}) {
  const port = Number(process.env.WHATSAPP_BRIDGE_PORT || options.port || 3001);
  const secret = process.env.WHATSAPP_BRIDGE_SECRET || '';

  const server = http.createServer(async (req, res) => {
    if (req.method === 'POST' && req.url === '/api/send') {
      let raw = '';
      req.on('data', (chunk) => {
        raw += chunk;
      });
      req.on('end', async () => {
        try {
          if (secret && req.headers['x-zenith-bridge-token'] !== secret) {
            res.writeHead(401, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: false, error: 'Unauthorized' }));
            return;
          }
          const body = raw ? JSON.parse(raw) : {};
          const to = normalizePhone(body.to || '');
          const text = String(body.body || '').trim();
          if (!to || !text) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: false, error: 'Missing to or body' }));
            return;
          }
          const digits = to.replace(/\D/g, '');
          const chatId = `${digits}@c.us`;
          await client.sendMessage(chatId, text);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: true, to }));
        } catch (err) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: false, error: String(err.message || err) }));
        }
      });
      return;
    }

    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: true, service: 'zenith-whatsapp-bridge' }));
      return;
    }

    res.writeHead(404);
    res.end();
  });

  server.listen(port, '127.0.0.1', () => {
    console.log(`[bridge] send API listening on http://127.0.0.1:${port}`);
  });
  return server;
}

module.exports = { startSendServer };
