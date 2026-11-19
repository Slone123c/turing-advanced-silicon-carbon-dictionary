// 发布页 /intro/：讲清痛点、Hook 怎么工作、测试数据，然后把人送进词典。
// 统计数字来自 replay/render.py 生成的 replay/intro.json，跟着回放结果更新。
import './intro.css';
import brandMark from './brand-mark-default.svg?raw';
import antigravityIcon from './assets/harnesses/antigravity.svg';
import claudeIcon from './assets/harnesses/claude.svg';
import cursorIconRaw from './assets/harnesses/cursor.svg?raw';
import deepseekIcon from './assets/harnesses/deepseek.svg';
import grokIconRaw from './assets/harnesses/grok.svg?raw';
import openaiIconRaw from './assets/harnesses/openai.svg?raw';
import { createDictionaries } from './dictionaries.js';

const DICTS = createDictionaries();

const cleanSvg = (raw) => raw
  .replace(/<title[^>]*>.*?<\/title>/is, '')
  .replace('<svg ', '<svg class="stat-icon" aria-hidden="true" ');

const HARNESS_ICONS = {
  'Antigravity CLI': `<img class="stat-icon" src="${antigravityIcon}" alt="" aria-hidden="true">`,
  'Claude Code': `<img class="stat-icon" src="${claudeIcon}" alt="" aria-hidden="true">`,
  'Codex CLI': cleanSvg(openaiIconRaw),
  'Cursor Agent': cleanSvg(cursorIconRaw),
  'DeepSeek Harness': `<img class="stat-icon" src="${deepseekIcon}" alt="" aria-hidden="true">`,
  'Grok CLI': cleanSvg(grokIconRaw),
};

const TERM_CHIPS = ['基线', '收口', '契约', '门控', '夹具', '真源', '漂移', '账本', '兜底', '抓手'];
const REWRITE_PAIRS = [
  ['收口', '统一处理'],
  ['基线', '改动前版本'],
  ['契约', '接口约定'],
  ['账本', '执行记录'],
  ['兜底', '默认处理'],
  ['门控', '特性开关'],
];

function marqueeTrack(itemsHtml, cls, durationSec) {
  return `<div class="stat-marquee ${cls}" style="--dur:${durationSec}s" aria-hidden="true"><div class="stat-track"><span class="stat-group">${itemsHtml}</span><span class="stat-group">${itemsHtml}</span></div></div>`;
}

function statVisual(kind, d) {
  if (kind === 'terms') {
    const items = TERM_CHIPS.map((w) => `<span class="stat-chip stat-chip-term">${esc(w)}</span>`).join('');
    return marqueeTrack(items, 'stat-marquee-terms', 20);
  }
  if (kind === 'cases') {
    const list = (d.caseSnippets && d.caseSnippets.length) ? d.caseSnippets : ['搞定了，重构已经全部落地。', '你的直觉被数据验证了…', '因为内存对齐。'];
    const items = list.map((text) => `<span class="stat-chip stat-chip-case">“${esc(text)}”</span>`).join('');
    return marqueeTrack(items, 'stat-marquee-cases', Math.max(48, list.length * 2.2));
  }
  if (kind === 'models') {
    const list = (d.modelNames && d.modelNames.length)
      ? [...d.modelNames].sort((a, b) => a.localeCompare(b, 'en', { sensitivity: 'base' }))
      : ['claude-haiku-5-5', 'claude-opus-5-5', 'composer-2.5', 'deepseek-v4.1-flash', 'gemini-4-hydrogen', 'gpt-6.2-sol', 'grok-4.7'];
    const items = list.map((name) => `<span class="stat-chip stat-chip-mono">${esc(name)}</span>`).join('');
    return marqueeTrack(items, 'stat-marquee-models', 28);
  }
  if (kind === 'harnesses') {
    const list = (d.harnessNames && d.harnessNames.length) ? d.harnessNames : Object.keys(HARNESS_ICONS);
    const items = list.map((name) => `<span class="stat-chip stat-chip-harness">${HARNESS_ICONS[name] || ''}<span>${esc(name)}</span></span>`).join('');
    return marqueeTrack(items, 'stat-marquee-harnesses', 22);
  }
  if (kind === 'clearRate') {
    const items = REWRITE_PAIRS.map(([before, after]) =>
      `<span class="stat-chip stat-chip-pair"><span class="stat-pair-old">${esc(before)}</span><span class="stat-pair-arrow">→</span><span class="stat-pair-new">${esc(after)}</span></span>`
    ).join('');
    return marqueeTrack(items, 'stat-marquee-clear', 24);
  }
  if (kind === 'lenDelta') {
    const toPos = (v) => Math.max(4, Math.min(96, ((v + 0.15) / 0.35) * 100));
    const lo = toPos(d.lenDeltaNegP50 ?? -0.038);
    const p50 = toPos(d.lenDeltaP50 ?? 0.031);
    const hi = toPos(d.lenDeltaPosP50 ?? 0.08);
    const zero = toPos(0);
    return `<div class="stat-range" aria-hidden="true"><span class="stat-range-label">-15%</span><div class="stat-range-track"><span class="stat-range-zero" style="left:${zero}%"></span><span class="stat-range-band" style="left:${lo}%;width:${Math.max(4, hi - lo)}%"><span class="stat-meter-sheen"></span></span><span class="stat-range-mid" style="left:${p50}%"></span></div><span class="stat-range-label">+20%</span></div>`;
  }
  return '';
}

// 每个词一条改写示例，竖向列出。source 写模型名的节选自 replay/ 的真实回放：
// before 取 cases.json 原文中命中词所在的分句，after 取该模型改写后对应的分句。
// 「门控」在回放用例里没有出现，按词条的改写建议手写，标为「词典示例」。
const EXAMPLES = [
  {
    term: '基线',
    case: 'c8',
    before: '和改动前的基线比，LCP 从 3.8s 降到 2.1s，首屏 JS 体积从 612KB 降到 287KB。',
    after: '和改动前的版本比，LCP 从 3.8s 降到 2.1s，首屏 JS 体积从 612KB 降到 287KB。',
    source: 'claude-opus',
  },
  {
    term: '门控',
    before: '新的导出入口加了门控，只有灰度用户能看到。',
    after: '新的导出入口加了特性开关，只对灰度用户开启。',
  },
  {
    term: '契约',
    case: 'd23',
    before: '我把接口契约写在 `docs/api/order.md` 里了。',
    after: '我把接口约定写在 `docs/api/order.md` 里了。',
    source: 'claude-opus',
  },
  {
    term: '夹具',
    case: 'c3',
    before: '你说得对，但我将要开始探针、快照、证据、门禁、夹具，还有哈希、冒烟、基线了。',
    after: '你说得对，我会先检查支付回调服务是否正常，保存迁移前的配置副本和检查记录，准备测试数据，并明确上线前必须通过的检查项。',
    source: 'gpt-6.1-sol',
  },
  {
    term: '收口',
    case: 'c10',
    before: '原来 6 个页面各自拼报错文案，现在统一收口到 `authErrors.ts` 的 `formatAuthError(code)`。',
    after: '原来 6 个页面各自拼报错文案，现在都改为调用 `authErrors.ts` 的 `formatAuthError(code)` 生成文案。',
    source: 'claude-opus',
  },
  {
    term: '真源 · 漂移',
    case: 'c1',
    before: '真源无漂移。',
    after: '与作为基准的源文件核对一致、未发现改动。',
    mark: ['真源', '漂移'],
    source: 'claude-opus',
  },
  {
    term: '账本',
    case: 'c1',
    before: '账本 15/15 全绿。',
    after: '执行记录中 15 项检查全部通过。',
    mark: ['账本', '全绿'],
    source: 'claude-opus',
  },
];

const TEXT = {
  zh: {
    docTitle: '关于 · 图灵高阶硅碳词典',
    eyebrow: '图灵高阶硅碳词典',
    heroTitle: '匪夷所思的<br>AI 回答',
    heroLede: (n) => `「基线」「门控」「契约」「收口」……这本词典收录了 ${n} 个 AI 回答里高频出现、难以理解的说法，并为每个词语都写明了问题和改写建议。`,
    ctaDict: '开始查词',
    ctaInstall: '安装 Agent Hook',
    howTitle: 'Hook 怎么工作',
    proofTitle: '测试数据',
    stats: (d) => [
      ['terms', d.terms, '个词条，附问题说明和改写建议'],
      ['cases', d.cases, `条真实 AI 回复用例，含 ${d.keepCases} 条应保留原文的正当用法`],
      ['models', d.models, '个参与回放测试的模型'],
      ['harnesses', d.harnesses, '个 Agent Harness'],
      ['clearRate', pct(d.clearRate), '命中黑话直接替换为大白话'],
      ['lenDelta', deltaRange(d.lenDeltaNegP50, d.lenDeltaPosP50), '改写后字数的平均变化范围'],
    ],
    proofLink: '查看全部改写对比 →',
    installTitle: '装上 Hook',
    installLede: '把下面这段话发给你的编码 Agent（Claude Code、Cursor、Codex、Gemini CLI 等），它会自己完成安装。',
    promptLabel: '安装提示词',
    copy: '复制',
    copied: '已复制',
    copyFailed: '复制失败',
    closingTitle: '看看收录了哪些词',
    footNote: '图灵高阶硅碳词典 · 开源项目',
  },
  en: {
    docTitle: 'About · Turing Advanced Silicon–Carbon Dictionary',
    eyebrow: 'Turing Advanced Silicon–Carbon Dictionary',
    heroTitle: 'To be continued…',
    heroLede: () => 'The English word list is still small. We are collecting more real AI replies before writing this page. Meanwhile, the Chinese dictionary is live.',
    ctaDict: 'Open the dictionary',
    footNote: 'Turing Advanced Silicon–Carbon Dictionary · Open source',
  },
};

function pct(x) {
  return x == null ? '–' : `${(x * 100).toFixed(x === 1 ? 0 : 1)}%`;
}

function signedPct(x, digits = 1) {
  if (x == null) return '–';
  const v = x * 100;
  const abs = Math.abs(v) < 0.05 ? 0 : v;
  const sign = abs > 0 ? '+' : '';
  return `${sign}${abs.toFixed(abs === 0 ? 0 : digits)}%`;
}

function deltaRange(lo, hi) {
  if (lo == null || hi == null) return '–';
  return `${signedPct(lo, 0)} ~ ${signedPct(hi, 0)}`;
}

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// 反引号包住的标识符显示为代码；命中词标红
function richText(text, marks = []) {
  return text.split(/(`[^`]+`)/).map((part) => {
    if (part.startsWith('`') && part.endsWith('`')) return `<code>${esc(part.slice(1, -1))}</code>`;
    let html = esc(part);
    [...marks].sort((a, b) => b.length - a.length).forEach((w) => {
      html = html.split(esc(w)).join(`<mark>${esc(w)}</mark>`);
    });
    return html;
  }).join('');
}

const $ = (id) => document.getElementById(id);
let data = null;
let lang = 'zh';
try {
  const q = new URLSearchParams(location.search).get('lang');
  const stored = localStorage.getItem('la-dictionary-lang');
  lang = q === 'en' || q === 'zh' ? q : stored === 'en' ? 'en' : 'zh';
} catch (_) {}

function renderExamples() {
  $('convo').innerHTML = EXAMPLES.map((ex) => {
    const marks = ex.mark ? [].concat(ex.mark) : [ex.term];
    return `<li class="example">
      <div class="example-head"><span class="example-term">${esc(ex.term)}</span></div>
      <div class="example-row" data-kind="before"><span class="example-label">Before</span><p class="example-text">${richText(ex.before, marks)}</p></div>
      <div class="example-row" data-kind="after"><span class="example-label">After</span><p class="example-text">${richText(ex.after)}</p></div>
    </li>`;
  }).join('');
}

function render() {
  const t = TEXT[lang];
  const zh = lang === 'zh';
  document.documentElement.lang = zh ? 'zh-CN' : 'en';
  document.title = t.docTitle;
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const v = t[el.dataset.i18n];
    if (typeof v === 'string') el.textContent = v;
  });
  document.querySelectorAll('[data-i18n-html]').forEach((el) => {
    el.innerHTML = t[el.dataset.i18nHtml];
  });
  document.querySelectorAll('a[href^="../"]').forEach((a) => {
    if (a.classList.contains('text-link')) return;
    a.href = `../?lang=${lang}`;
  });
  const sw = $('lang-switch');
  sw.dataset.active = lang;
  sw.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.lang === lang)));

  // 英文语料还少，英文版只留首屏和进入词典的按钮
  document.body.dataset.lang = lang;
  ['convo', 'how', 'install'].forEach((id) => { $(id).hidden = !zh; });
  document.querySelector('.closing').hidden = !zh;
  document.querySelector('.cta-row a[href="#install"]').hidden = !zh;
  $('hero-lede').textContent = t.heroLede(data ? data.terms : DICTS.zh.totalCatalogSize);

  $('proof').hidden = !zh || !data;
  if (!zh) return;
  $('install-prompt').textContent = DICTS.zh.ui.agentInstallPrompt;
  if (data) {
    $('stats').innerHTML = t.stats(data)
      .map(([kind, num, label]) => `<div class="stat"><span class="stat-num">${esc(num)}</span><span class="stat-label">${esc(label)}</span><div class="stat-viz">${statVisual(kind, data)}</div></div>`)
      .join('');
  }
}

$('brand-mark').innerHTML = brandMark.replace(/<title[^>]*>.*?<\/title>/is, '');

$('lang-switch').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-lang]');
  if (!b || b.dataset.lang === lang) return;
  lang = b.dataset.lang;
  try { localStorage.setItem('la-dictionary-lang', lang); } catch (_) {}
  render();
});

$('theme-toggle').addEventListener('click', () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('la-dictionary-theme', root.dataset.theme); } catch (_) {}
});

$('copy-btn').addEventListener('click', async () => {
  const btn = $('copy-btn');
  try {
    await navigator.clipboard.writeText($('install-prompt').textContent);
    btn.textContent = TEXT.zh.copied;
  } catch (_) {
    btn.textContent = TEXT.zh.copyFailed;
  }
  setTimeout(() => { btn.textContent = TEXT.zh.copy; }, 1600);
});

// Hook 工作流动效：一条回复先被 Hook 拦下一次，Agent 改写后直接交付给你
const FLOW_BEFORE = '统一<mark>收口</mark>到 <code>authErrors.ts</code>';
const FLOW_AFTER = '改为调用 <code>authErrors.ts</code>';
const FLOW = [
  { at: 'agent', active: 'agent', tone: 'bad', text: FLOW_BEFORE, hook: 'idle', step: 0, ms: 1500 },
  { at: 'hook', active: '', tone: 'bad', hook: 'idle', step: 0, ms: 800 },
  { at: 'hook', active: '', tone: 'bad', hook: 'block', badge: '命中「收口」', step: 1, ms: 1500 },
  { at: 'agent', active: 'agent', tone: 'bad', hook: 'block', badge: '命中「收口」', step: 1, ms: 800 },
  { at: 'agent', active: 'agent', tone: 'good', text: FLOW_AFTER, hook: 'idle', step: 2, ms: 1500 },
  { at: 'you', active: 'you', tone: 'good', hook: 'idle', step: 3, ms: 2800 },
];
const STEP_START = [0, 2, 4, 5];
let flowIndex = 0;
let flowTimer = null;
let flowVisible = false;
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');

function showFlow(i) {
  const f = FLOW[i], el = $('flow'), packet = $('flow-packet'), text = $('flow-packet-text');
  flowIndex = i;
  el.dataset.hook = f.hook;
  el.dataset.tone = f.tone;
  el.dataset.active = f.active;
  packet.dataset.at = f.at;
  $('flow-badge').textContent = f.badge || '';
  if (f.text && text.innerHTML !== f.text) {
    text.innerHTML = f.text;
    packet.classList.remove('is-swapping');
    void packet.offsetWidth;
    packet.classList.add('is-swapping');
  }
  $('flow-steps').querySelectorAll('button').forEach((b) => {
    if (Number(b.dataset.step) === f.step) b.setAttribute('aria-current', 'step');
    else b.removeAttribute('aria-current');
  });
}

function scheduleFlow() {
  clearTimeout(flowTimer);
  if (!flowVisible || reduceMotion.matches || document.hidden) return;
  flowTimer = setTimeout(() => {
    const next = (flowIndex + 1) % FLOW.length;
    // 回到开头时先把文字换回原话
    if (next === 0) $('flow-packet-text').innerHTML = '';
    showFlow(next);
    scheduleFlow();
  }, FLOW[flowIndex].ms);
}

$('flow-steps').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-step]');
  if (!b) return;
  // 跳到某一步时，文字要和那一步一致
  const i = STEP_START[Number(b.dataset.step)];
  const lastText = FLOW.slice(0, i + 1).reverse().find((f) => f.text);
  $('flow-packet-text').innerHTML = lastText.text;
  showFlow(i);
  scheduleFlow();
});

new IntersectionObserver(([entry]) => {
  flowVisible = entry.isIntersecting;
  scheduleFlow();
}, { threshold: 0.35 }).observe($('flow'));
document.addEventListener('visibilitychange', scheduleFlow);
reduceMotion.addEventListener?.('change', scheduleFlow);
showFlow(0);

renderExamples();
render();
fetch('../replay/intro.json')
  .then((r) => (r.ok ? r.json() : null))
  .then((d) => { if (d) { data = d; render(); } })
  .catch(() => {});
