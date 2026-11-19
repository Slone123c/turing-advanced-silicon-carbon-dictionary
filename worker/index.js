import TERMS_BY_LANG from './terms.json';

const VALID_LANGS = new Set(['zh', 'en']);
const VALID_TERMS_BY_LANG = Object.fromEntries(
  Object.entries(TERMS_BY_LANG).map(([lang, list]) => [lang, new Set(list)]),
);

const TERM_COOLDOWN_TTL_SEC = 86400;
const IP_WINDOW_TTL_SEC = 600;
const IP_WINDOW_MAX_HITS = 15;

function parseAllowedOrigins(env) {
  const raw = typeof env?.ALLOWED_ORIGINS === 'string' ? env.ALLOWED_ORIGINS : '';
  const list = raw
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return new Set(list);
}

function buildCorsHeaders(request, allowedOrigins) {
  const headers = {
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
  if (allowedOrigins.size === 0) {
    headers['Access-Control-Allow-Origin'] = '*';
    return headers;
  }
  const origin = request.headers.get('Origin') || '';
  if (allowedOrigins.has(origin)) {
    headers['Access-Control-Allow-Origin'] = origin;
    headers.Vary = 'Origin';
  }
  return headers;
}

function jsonResponse(data, status = 200, corsHeaders = {}, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      ...corsHeaders,
      ...extraHeaders,
    },
  });
}

async function sha256Hex(input) {
  const bytes = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function verifyTurnstile(env, token, ip) {
  const secret = typeof env?.TURNSTILE_SECRET_KEY === 'string' ? env.TURNSTILE_SECRET_KEY.trim() : '';
  if (!secret) {
    return { ok: true, skipped: true };
  }
  const cleanToken = typeof token === 'string' ? token.trim() : '';
  if (!cleanToken || cleanToken.length > 2048) {
    return { ok: false, reason: 'missing_token' };
  }
  const form = new URLSearchParams({
    secret,
    response: cleanToken,
  });
  if (ip && ip !== 'unknown') {
    form.set('remoteip', ip);
  }
  const res = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form.toString(),
  });
  if (!res.ok) {
    return { ok: false, reason: `siteverify_http_${res.status}` };
  }
  const data = await res.json().catch(() => null);
  if (!data || !data.success) {
    return { ok: false, codes: data?.['error-codes'] || [] };
  }
  return { ok: true };
}

async function readCounts(kv, lang) {
  const raw = await kv.get(`counts:${lang}`, 'json');
  return raw && typeof raw === 'object' ? raw : {};
}

function sortObjectKeys(obj) {
  const sorted = {};
  for (const key of Object.keys(obj).sort()) {
    sorted[key] = obj[key];
  }
  return sorted;
}

async function backupToGist(env) {
  const gistId = typeof env?.GIST_ID === 'string' ? env.GIST_ID.trim() : '';
  const token = typeof env?.GITHUB_TOKEN === 'string' ? env.GITHUB_TOKEN.trim() : '';
  if (!gistId || !token) {
    console.log('[backup] skipped: GIST_ID or GITHUB_TOKEN not configured');
    return { skipped: true, reason: 'unconfigured' };
  }

  const [zhCounts, enCounts, prevDigest] = await Promise.all([
    readCounts(env.HOT_KV, 'zh'),
    readCounts(env.HOT_KV, 'en'),
    env.HOT_KV.get('backup:last_digest'),
  ]);

  const canonical = {
    zh: sortObjectKeys(zhCounts),
    en: sortObjectKeys(enCounts),
  };
  const digest = await sha256Hex(JSON.stringify(canonical));
  if (prevDigest === digest) {
    console.log('[backup] skipped: no changes since last snapshot');
    return { skipped: true, reason: 'unchanged' };
  }

  const filename = (typeof env?.GIST_FILENAME === 'string' && env.GIST_FILENAME.trim())
    || 'sic-dict-hot-backup.json';
  const snapshot = {
    backedUpAt: new Date().toISOString(),
    counts: canonical,
  };

  const res = await fetch(`https://api.github.com/gists/${encodeURIComponent(gistId)}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json; charset=utf-8',
      'User-Agent': 'sic-dict-hot-worker',
    },
    body: JSON.stringify({
      files: {
        [filename]: {
          content: `${JSON.stringify(snapshot, null, 2)}\n`,
        },
      },
    }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    console.error(`[backup] GitHub Gist PATCH failed: ${res.status} ${errText.slice(0, 200)}`);
    return { ok: false, status: res.status };
  }

  await env.HOT_KV.put('backup:last_digest', digest);
  console.log(`[backup] updated gist ${gistId} (${filename})`);
  return { ok: true, digest };
}

export default {
  async fetch(request, env) {
    const allowedOrigins = parseAllowedOrigins(env);
    const corsHeaders = buildCorsHeaders(request, allowedOrigins);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    const url = new URL(request.url);

    if (request.method === 'GET' && url.pathname === '/hot') {
      const requested = url.searchParams.get('lang');
      const lang = VALID_LANGS.has(requested) ? requested : 'zh';
      const counts = await readCounts(env.HOT_KV, lang);
      return jsonResponse({ lang, counts }, 200, corsHeaders, {
        'Cache-Control': 'public, max-age=30',
      });
    }

    if (request.method === 'POST' && url.pathname === '/hit') {
      if (allowedOrigins.size > 0) {
        const origin = request.headers.get('Origin') || '';
        if (!allowedOrigins.has(origin)) {
          return jsonResponse({ error: 'Origin not allowed' }, 403, corsHeaders);
        }
      }

      let body;
      try {
        body = await request.json();
      } catch {
        return jsonResponse({ error: 'Invalid JSON' }, 400, corsHeaders);
      }

      const lang = VALID_LANGS.has(body?.lang) ? body.lang : 'zh';
      const term = typeof body?.term === 'string' ? body.term.trim() : '';
      const validTerms = VALID_TERMS_BY_LANG[lang];
      if (!term || term.length > 64 || !validTerms || !validTerms.has(term)) {
        return jsonResponse({ error: 'Invalid term' }, 400, corsHeaders);
      }

      const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
      const turnstileCheck = await verifyTurnstile(env, body?.turnstileToken, ip);
      if (!turnstileCheck.ok) {
        return jsonResponse({ error: 'Turnstile verification failed' }, 403, corsHeaders);
      }

      const salt = typeof env?.IP_SALT === 'string' ? env.IP_SALT : '';
      const ipHash = (await sha256Hex(`${salt}:${ip}`)).slice(0, 24);
      const termRlKey = `rl:${ipHash}:${lang}:${term}`;
      const globalRlKey = `rlg:${ipHash}`;

      const [seenTerm, globalHitsRaw, counts] = await Promise.all([
        env.HOT_KV.get(termRlKey),
        env.HOT_KV.get(globalRlKey),
        readCounts(env.HOT_KV, lang),
      ]);
      const current = Number(counts[term]) || 0;
      const globalHits = Number(globalHitsRaw) || 0;

      if (seenTerm || globalHits >= IP_WINDOW_MAX_HITS) {
        return jsonResponse({ ok: true, limited: true, term, count: current }, 200, corsHeaders);
      }

      const next = current + 1;
      counts[term] = next;
      await Promise.all([
        env.HOT_KV.put(`counts:${lang}`, JSON.stringify(counts)),
        env.HOT_KV.put(termRlKey, '1', { expirationTtl: TERM_COOLDOWN_TTL_SEC }),
        env.HOT_KV.put(globalRlKey, String(globalHits + 1), { expirationTtl: IP_WINDOW_TTL_SEC }),
      ]);

      return jsonResponse({ ok: true, term, count: next }, 200, corsHeaders);
    }

    return jsonResponse({ error: 'Not found' }, 404, corsHeaders);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(backupToGist(env));
  },
};
