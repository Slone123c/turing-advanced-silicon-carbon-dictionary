/** Cached localStorage helpers (avoids repeated synchronous storage reads). */
const storageCache = new Map();

export function invalidateStorageCache(key) {
  if (key === undefined) {
    storageCache.clear();
  } else {
    storageCache.delete(key);
  }
}

export function readStorage(key) {
  if (storageCache.has(key)) return storageCache.get(key);
  try {
    const val = window.localStorage.getItem(key);
    storageCache.set(key, val);
    return val;
  } catch (_) {
    return null;
  }
}

export function writeStorage(key, value) {
  const str = String(value);
  storageCache.set(key, str);
  try {
    window.localStorage.setItem(key, str);
  } catch (_) {
    // 内存会话状态已更新，忽略受限环境写入异常
  }
}

export function removeStorage(key) {
  storageCache.delete(key);
  try {
    window.localStorage.removeItem(key);
  } catch (_) {
    // 忽略受限环境写入异常
  }
}

export function readJsonStorage(key, fallback) {
  const raw = readStorage(key);
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : fallback;
  } catch (_) {
    return fallback;
  }
}
