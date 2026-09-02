const fs = require('fs');
const path = require('path');

const PID_FILE = path.resolve(__dirname, '..', '.bridge.pid');

function isProcessAlive(pid) {
  if (!pid || Number.isNaN(pid)) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code !== 'ESRCH';
  }
}

function readPidFile() {
  try {
    const raw = fs.readFileSync(PID_FILE, 'utf8').trim();
    const pid = Number.parseInt(raw, 10);
    return Number.isFinite(pid) ? pid : null;
  } catch {
    return null;
  }
}

function acquireBridgeLock() {
  const existingPid = readPidFile();
  if (existingPid && existingPid !== process.pid && isProcessAlive(existingPid)) {
    return {
      ok: false,
      reason: 'already_running',
      pid: existingPid,
    };
  }

  fs.writeFileSync(PID_FILE, String(process.pid), 'utf8');
  return { ok: true, pid: process.pid };
}

function releaseBridgeLock() {
  const existingPid = readPidFile();
  if (existingPid === process.pid) {
    try {
      fs.unlinkSync(PID_FILE);
    } catch {
      // ignore
    }
  }
}

function sessionLockPath() {
  return path.resolve(__dirname, '..', '.wwebjs_auth', 'session', 'lockfile');
}

function chromeSessionLockExists() {
  try {
    return fs.existsSync(sessionLockPath());
  } catch {
    return false;
  }
}

module.exports = {
  PID_FILE,
  acquireBridgeLock,
  releaseBridgeLock,
  chromeSessionLockExists,
  isProcessAlive,
  readPidFile,
};
