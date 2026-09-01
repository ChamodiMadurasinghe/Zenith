const { MessageMedia } = require('whatsapp-web.js');

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

async function diagnoseMedia(client, msgId) {
  try {
    return await client.pupPage.evaluate(async (id) => {
      const out = {};
      try {
        out.hasRequire = typeof window.require === 'function';
        out.hasWWebJS = typeof window.WWebJS !== 'undefined';
        const msg =
          window.require?.('WAWebCollections')?.Msg?.get(id) ||
          (await window.require?.('WAWebCollections')?.Msg?.getMessagesById?.([id]))
            ?.messages?.[0];
        out.msgFound = Boolean(msg);
        out.mediaStage = msg?.mediaData?.mediaStage || null;
        out.type = msg?.type || null;
        out.mimetype = msg?.mimetype || null;
        out.hasDownloadManager = Boolean(window.require?.('WAWebDownloadManager'));
      } catch (e) {
        out.error = e?.message || String(e);
      }
      return out;
    }, msgId);
  } catch (err) {
    return { evaluateError: formatError(err) };
  }
}

async function downloadMediaViaPage(client, msgId) {
  const result = await client.pupPage.evaluate(async (id) => {
    try {
      const msg =
        window.require('WAWebCollections').Msg.get(id) ||
        (await window.require('WAWebCollections').Msg.getMessagesById([id]))?.messages?.[0];

      if (!msg || !msg.mediaData) {
        return { ok: false, step: 'lookup', error: 'message or mediaData missing' };
      }
      if (msg.mediaData.mediaStage === 'REUPLOADING') {
        return { ok: false, step: 'stage', error: 'media REUPLOADING on phone' };
      }
      if (msg.mediaData.mediaStage !== 'RESOLVED') {
        await msg.downloadMedia({ downloadEvenIfExpensive: true, rmrReason: 1 });
      }
      if (
        msg.mediaData.mediaStage?.includes('ERROR') ||
        msg.mediaData.mediaStage === 'FETCHING'
      ) {
        return {
          ok: false,
          step: 'stage',
          error: `media stage ${msg.mediaData.mediaStage}`,
        };
      }

      const mockQpl = {
        addAnnotations() {
          return this;
        },
        addPoint() {
          return this;
        },
      };
      const decryptedMedia = await window
        .require('WAWebDownloadManager')
        .downloadManager.downloadAndMaybeDecrypt({
          directPath: msg.directPath,
          encFilehash: msg.encFilehash,
          filehash: msg.filehash,
          mediaKey: msg.mediaKey,
          mediaKeyTimestamp: msg.mediaKeyTimestamp,
          type: msg.type,
          signal: new AbortController().signal,
          downloadQpl: mockQpl,
        });

      const data = await window.WWebJS.arrayBufferToBase64Async(decryptedMedia);
      return {
        ok: true,
        data,
        mimetype: msg.mimetype,
        filename: msg.filename,
        filesize: msg.size,
      };
    } catch (e) {
      return {
        ok: false,
        step: 'download',
        error: e?.message || String(e),
        detail: (e?.stack || '').slice(0, 240),
      };
    }
  }, msgId);

  if (!result?.ok) {
    const parts = [result?.step, result?.error, result?.detail].filter(Boolean);
    throw new Error(parts.join(' | ') || 'unknown download error');
  }

  return new MessageMedia(result.mimetype, result.data, result.filename, result.filesize);
}

async function downloadMediaWithRetry(msg, client, attempts = 5) {
  const msgId = msg.id?._serialized;
  if (!msgId) throw new Error('missing message id');

  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      let activeMsg = msg;
      if (client?.getMessageById) {
        try {
          activeMsg = await client.getMessageById(msgId);
        } catch {
          // use original message object
        }
      }

      let media;
      if (client?.pupPage) {
        media = await downloadMediaViaPage(client, msgId);
      } else {
        media = await activeMsg.downloadMedia();
      }
      if (media?.data) return media;
      lastError = new Error('empty media payload');
    } catch (err) {
      lastError = err;
    }

    if (attempt < attempts) {
      console.log(`[bridge] downloadMedia retry ${attempt}/${attempts}…`);
      await new Promise((resolve) => setTimeout(resolve, 2000 * attempt));
    }
  }

  if (client) {
    const diag = await diagnoseMedia(client, msgId);
    console.warn('[bridge] media diagnostic:', JSON.stringify(diag));
  }

  throw new Error(`downloadMedia failed: ${formatError(lastError)}`);
}

module.exports = { downloadMediaWithRetry, diagnoseMedia };
