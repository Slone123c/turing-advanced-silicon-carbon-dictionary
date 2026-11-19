// @ts-nocheck
import rulesData from './rules.json';
import { COLLAPSED_PANEL_HIDDEN, MOTION_EASE_OUT, createMotion } from './motion.js';
import { createDictionaries } from './dictionaries.js';
import { invalidateStorageCache, readJsonStorage, readStorage, removeStorage, writeStorage } from './storage.js';
import { buildAddWordIssuePayload, buildGithubIssueUrl, buildSuggestIssuePayload } from './githubIssues.js';

export function initDictionaryApp() {
  const THEME_STORAGE_KEY = 'la-dictionary-theme';
  const LANG_STORAGE_KEY = 'la-dictionary-lang';
  const THUMBS_SIDE_STORAGE_KEY = 'la-dictionary-thumbs-side';
  const COMMUNITY_STORAGE_KEY = 'la-dictionary-community-v1';
  const CUSTOM_TERMS_STORAGE_KEY = 'la-dictionary-custom-terms-v1';
  const VOTED_STORAGE_KEY = 'la-dictionary-voted-v1';
  const LOCAL_HOT_STORAGE_KEY = 'la-dictionary-local-hot-v1';
  const HOT_API = ((typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_HOT_API)
    || (typeof window !== 'undefined' && window.__HOT_API__)
    || '').replace(/\/+$/, '');
  const TURNSTILE_SITE_KEY = ((typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_TURNSTILE_SITE_KEY)
    || (typeof window !== 'undefined' && window.__TURNSTILE_SITE_KEY__)
    || '').trim();
  // 部署到 GitHub Pages 时填入 'owner/repo'，即可直接跳转预填好的 GitHub Issue 页面
  const GITHUB_REPO = rulesData.repo || '';

  const DICTIONARIES = createDictionaries();

  function getConfiguredRepo() {
    const base = GITHUB_REPO.trim();
    return /^[^/\s]+\/[^/\s]+$/.test(base) ? base : '';
  }

  function loadPersistedCommunity() {
    const saved = readJsonStorage(COMMUNITY_STORAGE_KEY, {});
    const out = { zh: {}, en: {} };
    for (const langKey of ['zh', 'en']) {
      const bucket = saved[langKey];
      if (!bucket || typeof bucket !== 'object') continue;
      for (const [term, list] of Object.entries(bucket)) {
        if (!Array.isArray(list)) continue;
        const clean = list
          .filter((entry) => entry && typeof entry.text === 'string' && entry.text.trim())
          .map((entry) => {
            const item = {
              text: entry.text.trim(),
              note: typeof entry.note === 'string' ? entry.note.trim() : '',
              mode: entry.mode === 'structured' ? 'structured' : 'freeform'
            };
            if (item.mode === 'structured' && entry.structured && typeof entry.structured === 'object') {
              const lvl = Number(entry.structured.level);
              item.structured = {
                level: lvl === 1 || lvl === 2 || lvl === 3 ? lvl : 1,
                why: typeof entry.structured.why === 'string' ? entry.structured.why.trim() : '',
                suggest: typeof entry.structured.suggest === 'string' ? entry.structured.suggest.trim() : '',
                ok: typeof entry.structured.ok === 'string' ? entry.structured.ok.trim() : '',
                bad: typeof entry.structured.bad === 'string' ? entry.structured.bad.trim() : '',
                alias: typeof entry.structured.alias === 'string' ? entry.structured.alias.trim() : ''
              };
            }
            return item;
          });
        if (clean.length > 0) out[langKey][term] = clean;
      }
    }
    return out;
  }

  function loadPersistedCustomTerms() {
    const saved = readJsonStorage(CUSTOM_TERMS_STORAGE_KEY, {});
    const out = { zh: [], en: [] };
    for (const langKey of ['zh', 'en']) {
      const list = saved[langKey];
      if (!Array.isArray(list)) continue;
      const validLetters = new Set(DICTIONARIES[langKey].letters);
      out[langKey] = list
        .filter((item) => item && typeof item.term === 'string' && item.term.trim() && typeof item.why === 'string')
        .map((item) => {
          const letter = typeof item.letter === 'string' && validLetters.has(item.letter.toUpperCase())
            ? item.letter.toUpperCase()
            : DICTIONARIES[langKey].letters[0];
          const lvl = Number(item.level);
          return {
            term: item.term.trim(),
            letter,
            level: lvl === 1 || lvl === 2 || lvl === 3 ? lvl : 1,
            why: item.why.trim(),
            suggest: typeof item.suggest === 'string' ? item.suggest.trim() : '',
            ok: typeof item.ok === 'string' ? item.ok.trim() : '',
            bad: typeof item.bad === 'string' ? item.bad.trim() : '',
            alias: typeof item.alias === 'string' ? item.alias.trim() : '',
            isCustom: true
          };
        });
    }
    return out;
  }

  const persistedCommunity = loadPersistedCommunity();
  const persistedCustomTerms = loadPersistedCustomTerms();
  const persistedVoted = readJsonStorage(VOTED_STORAGE_KEY, { zh: {}, en: {} });
  const persistedLocalHot = readJsonStorage(LOCAL_HOT_STORAGE_KEY, { zh: {}, en: {} });

  const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const paramLang = urlParams ? urlParams.get('lang') : null;
  const paramQuery = urlParams ? (urlParams.get('q') || '').trim() : '';
  const storedTheme = readStorage(THEME_STORAGE_KEY);
  const storedLang = readStorage(LANG_STORAGE_KEY);
  const storedThumbsSide = readStorage(THUMBS_SIDE_STORAGE_KEY);
  const initialThumbsSide = storedThumbsSide === 'left' ? 'left' : 'right';
  const initialLang = paramLang === 'en' || paramLang === 'zh'
    ? paramLang
    : (storedLang === 'en' || storedLang === 'zh' ? storedLang : 'zh');
  const colorSchemeMedia = typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;
  const reducedMotionMedia = typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : null;

  function buildInitialOpenTerms(langKey, customTerms) {
    const map = {};
    for (const group of DICTIONARIES[langKey].groups) {
      for (const item of group.items) {
        map[item.term] = true;
      }
    }
    for (const item of customTerms) {
      map[item.term] = true;
    }
    return map;
  }

  const state = {
    lang: initialLang,
    thumbsSide: initialThumbsSide,
    dark: storedTheme ? storedTheme === 'dark' : Boolean(colorSchemeMedia && colorSchemeMedia.matches),
    userThemeOverride: Boolean(storedTheme),
    query: paramQuery,
    levelFilter: 'all',
    openTermsByLang: {
      zh: buildInitialOpenTerms('zh', persistedCustomTerms.zh),
      en: buildInitialOpenTerms('en', persistedCustomTerms.en)
    },
    communityByLang: persistedCommunity,
    customTermsByLang: persistedCustomTerms,
    votedByLang: { zh: { ...(persistedVoted.zh || {}) }, en: { ...(persistedVoted.en || {}) } },
    localHotByLang: { zh: { ...(persistedLocalHot.zh || {}) }, en: { ...(persistedLocalHot.en || {}) } },
    remoteHotByLang: { zh: {}, en: {} },
    sortByHot: false,
    activeModalTerm: null,
    activeSuggestMode: 'structured',
    lastTriggerSelector: null,
    addWordLastTriggerSelector: null,
    addWordLetterTouched: false,
    currentLetter: null,
    toastTimer: null,
    toastToken: 0,
    scrollRaf: null
  };

  const skipToMainLink = document.getElementById('skip-to-main');
  const brandHomeLink = document.getElementById('brand-home-link');
  const rootEl = document.documentElement;
  const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
  const headerScrollProgress = document.getElementById('header-scroll-progress');
  const thumbsNav = document.getElementById('thumbs-nav');
  const thumbsTrack = document.getElementById('thumbs-track');
  const thumbsSideToggle = document.getElementById('thumbs-side-toggle');
  const mobileAlphaWrap = document.getElementById('mobile-alpha-wrap');
  const mobileAlphaRail = document.getElementById('mobile-alpha-rail');
  const headerSearchBtn = document.getElementById('header-search-btn');
  const headerSearchLabel = document.getElementById('header-search-label');
  const headerAddBtn = document.getElementById('header-add-btn');
  const headerAddLabel = document.getElementById('header-add-label');
  const headerGithubStar = document.getElementById('header-github-star');
  const headerStarLabel = document.getElementById('header-star-label');
  const headerGithubLink = document.getElementById('header-github-link');
  const themeToggle = document.getElementById('theme-toggle');
  const langSwitch = document.getElementById('lang-switch');
  const langButtons = Array.from(langSwitch.querySelectorAll('.lang-btn'));
  const langSwitchMore = document.getElementById('lang-switch-more');
  const langSwitchMoreText = document.getElementById('lang-switch-more-text');
  const heroEyebrow = document.getElementById('hero-eyebrow');
  const heroTitle = document.getElementById('hero-title');
  const heroLede = document.getElementById('hero-lede');
  const heroNotice = document.getElementById('hero-notice');
  const headerAboutLink = document.getElementById('header-about-link');
  const footerAboutLink = document.getElementById('footer-about-link');
  const heroReplayLink = document.getElementById('hero-replay-link');
  const heroReplayTitle = document.getElementById('hero-replay-title');
  const hookInstallToggle = document.getElementById('hook-install-toggle');
  const hookInstallToggleLabel = document.getElementById('hook-install-toggle-label');
  const hookInstallPanel = document.getElementById('hook-install-panel');
  const landingAgentsSummary = document.getElementById('landing-agents-summary');
  const landingCopyPromptLabel = document.getElementById('landing-copy-prompt-label');
  const landingAgentPrompt = document.getElementById('landing-agent-prompt');
  const metaDescription = document.getElementById('meta-description');
  const searchSection = document.getElementById('search-section');
  const searchBarSlot = document.getElementById('search-bar-slot');
  const searchBar = document.getElementById('search-bar');
  const searchSrLabel = document.getElementById('search-sr-label');
  const searchInput = document.getElementById('search-input');
  const searchClear = document.getElementById('search-clear');
  const searchClearLabel = document.getElementById('search-clear-label');
  const searchKbd = document.getElementById('search-kbd');
  const hotTermsLabel = document.getElementById('hot-terms-label');
  const hotTermsList = document.getElementById('hot-terms-list');
  const levelAllBtn = document.getElementById('level-all-btn');
  const levelAllLabel = document.getElementById('level-all-label');
  const levelAllCount = document.getElementById('level-all-count');
  const levelFiltersEl = document.getElementById('level-filters');
  const sortHotBtn = document.getElementById('sort-hot-btn');
  const toggleAllBtn = document.getElementById('toggle-all-btn');
  const searchStatus = document.getElementById('search-status');
  const searchStatusText = document.getElementById('search-status-text');
  const searchStatusReset = document.getElementById('search-status-reset');
  const groupsContainer = document.getElementById('dictionary-groups');
  const emptyState = document.getElementById('empty-state');
  const emptyTitle = document.getElementById('empty-title');
  const emptyDesc = document.getElementById('empty-desc');
  const emptyAddWordBtn = document.getElementById('empty-add-word');
  const emptyAddWordLabel = document.getElementById('empty-add-word-label');
  const emptyReset = document.getElementById('empty-reset');
  const footerLegend = document.getElementById('footer-legend');
  const footerMeta = document.getElementById('footer-meta');

  const suggestDialog = document.getElementById('suggest-dialog');
  const suggestForm = document.getElementById('suggest-form');
  const suggestDialogTitle = document.getElementById('suggest-dialog-title');
  const suggestDialogSub = document.getElementById('suggest-dialog-sub');
  const suggestClose = document.getElementById('suggest-close');
  const suggestCancel = document.getElementById('suggest-cancel');
  const suggestSubmit = document.getElementById('suggest-submit');
  const suggestTextLabel = document.getElementById('suggest-text-label');
  const suggestText = document.getElementById('suggest-text');
  const suggestTextError = document.getElementById('suggest-text-error');

  const addWordDialog = document.getElementById('add-word-dialog');
  const addWordForm = document.getElementById('add-word-form');
  const addWordDialogTitle = document.getElementById('add-word-dialog-title');
  const addWordDialogSub = document.getElementById('add-word-dialog-sub');
  const addWordClose = document.getElementById('add-word-close');
  const addWordTermLabel = document.getElementById('add-word-term-label');
  const addWordTerm = document.getElementById('add-word-term');
  const addWordTermError = document.getElementById('add-word-term-error');
  const addWordLevelLabel = document.getElementById('add-word-level-label');
  const addWordLevel = document.getElementById('add-word-level');
  const addWordWhyLabel = document.getElementById('add-word-why-label');
  const addWordWhy = document.getElementById('add-word-why');
  const addWordWhyError = document.getElementById('add-word-why-error');
  const addWordAliasLabel = document.getElementById('add-word-alias-label');
  const addWordAlias = document.getElementById('add-word-alias');
  const addWordCancel = document.getElementById('add-word-cancel');
  const addWordSubmit = document.getElementById('add-word-submit');
  const toastEl = document.getElementById('toast');

  let activeToastCtrl = null;

  const motion = createMotion({ reducedMotionMedia, headerScrollProgress });
  const {
    isReducedMotion,
    runElementAnimation,
    cancelElementAnimation,
    clearAnimationInlineProps,
    updateHeaderScrollProgressFallback,
    syncHeaderScrollProgressDriver,
    animateEntryPanelToggle
  } = motion;

  function getCssTokenColor(varName, fallback) {
    try {
      const val = getComputedStyle(rootEl).getPropertyValue(varName).trim();
      return val || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function getActiveDict() {
    return DICTIONARIES[state.lang];
  }

  function getActiveOpenTerms() {
    return state.openTermsByLang[state.lang];
  }

  function getActiveCommunityMap() {
    return state.communityByLang[state.lang];
  }

  function getActiveCustomTerms() {
    return state.customTermsByLang[state.lang];
  }

  function savePersistedCommunity() {
    writeStorage(COMMUNITY_STORAGE_KEY, JSON.stringify(state.communityByLang));
  }

  function savePersistedCustomTerms() {
    writeStorage(CUSTOM_TERMS_STORAGE_KEY, JSON.stringify(state.customTermsByLang));
  }

  function getAllGroups(langKey = state.lang) {
    const dict = DICTIONARIES[langKey];
    const customList = state.customTermsByLang[langKey] || [];
    const byLetter = new Map();

    for (const group of dict.groups) {
      byLetter.set(group.letter, group.items.slice());
    }

    for (const custom of customList) {
      const bucket = byLetter.get(custom.letter) || [];
      bucket.push(custom);
      byLetter.set(custom.letter, bucket);
    }

    const locale = langKey === 'zh' ? 'zh-Hans-CN' : 'en';
    const order = dict.letters;
    const sortedLetters = Array.from(byLetter.keys()).sort((a, b) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return a.localeCompare(b);
    });

    return sortedLetters.map((letter) => ({
      letter,
      items: byLetter.get(letter).slice().sort((a, b) => a.term.localeCompare(b.term, locale))
    }));
  }

  function getTotalSampleCount(allGroups = getAllGroups()) {
    return allGroups.reduce((sum, g) => sum + g.items.length, 0);
  }

  function findItemByTerm(term) {
    const needle = String(term || '').trim().toLowerCase();
    for (const group of getAllGroups()) {
      for (const item of group.items) {
        if (item.term === term || item.term.toLowerCase() === needle) return item;
      }
    }
    return null;
  }

  function itemMatchesQuery(item, rawQuery) {
    const raw = (rawQuery || '').trim();
    if (!raw) return true;
    const needle = raw.toLowerCase();
    const dict = getActiveDict();
    const extras = (getActiveCommunityMap()[item.term] || [])
      .map((s) => `${s.text} ${s.note || ''}`)
      .join(' ');
    const haystack = [
      item.term,
      item.alias || '',
      item.why,
      item.suggest,
      item.ok || '',
      item.bad || '',
      dict.ui.levels[item.level] || '',
      extras
    ].join(' ').toLowerCase();

    return haystack.includes(needle);
  }

  function getQueryMatchedGroups(allGroups = getAllGroups()) {
    return allGroups.map((group) => ({
      letter: group.letter,
      items: group.items.filter((item) => itemMatchesQuery(item, state.query))
    })).filter((group) => group.items.length > 0);
  }

  function getFilteredGroups(queryGroups = getQueryMatchedGroups()) {
    if (state.levelFilter === 'all') return queryGroups;
    const targetLevel = Number(state.levelFilter);
    return queryGroups.map((group) => ({
      letter: group.letter,
      items: group.items.filter((item) => item.level === targetLevel)
    })).filter((group) => group.items.length > 0);
  }

  function getLevelCounts(queryGroups) {
    const counts = { all: 0, '1': 0, '2': 0, '3': 0 };
    for (const group of queryGroups) {
      for (const item of group.items) {
        counts.all += 1;
        const key = String(item.level);
        if (Object.prototype.hasOwnProperty.call(counts, key)) {
          counts[key] += 1;
        }
      }
    }
    return counts;
  }

  function createHighlightedFragment(text, rawQuery) {
    const str = String(text || '');
    const needle = (rawQuery || '').trim();
    const frag = document.createDocumentFragment();
    if (!needle) {
      frag.appendChild(document.createTextNode(str));
      return frag;
    }

    const lowerStr = str.toLowerCase();
    const lowerNeedle = needle.toLowerCase();
    let cursor = 0;
    let idx = lowerStr.indexOf(lowerNeedle, cursor);

    if (idx === -1) {
      frag.appendChild(document.createTextNode(str));
      return frag;
    }

    while (idx !== -1) {
      if (idx > cursor) {
        frag.appendChild(document.createTextNode(str.slice(cursor, idx)));
      }
      const mark = document.createElement('mark');
      mark.className = 'search-hit';
      mark.textContent = str.slice(idx, idx + needle.length);
      frag.appendChild(mark);
      cursor = idx + needle.length;
      idx = lowerStr.indexOf(lowerNeedle, cursor);
    }

    if (cursor < str.length) {
      frag.appendChild(document.createTextNode(str.slice(cursor)));
    }
    return frag;
  }

  const svgIconTemplates = new Map();

  function createSvgIcon(pathMarkup, extraClass, strokeWidth = '1.8') {
    const key = `${strokeWidth}\n${extraClass || ''}\n${pathMarkup}`;
    let template = svgIconTemplates.get(key);
    if (!template) {
      template = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      template.setAttribute('class', extraClass ? `od-icon ${extraClass}` : 'od-icon');
      template.setAttribute('aria-hidden', 'true');
      template.setAttribute('viewBox', '0 0 24 24');
      template.setAttribute('fill', 'none');
      template.setAttribute('stroke', 'currentColor');
      template.setAttribute('stroke-width', strokeWidth);
      template.innerHTML = pathMarkup;
      svgIconTemplates.set(key, template);
    }
    return template.cloneNode(true);
  }

  function renderThemeToggle(animateIcon = false) {
    const ui = getActiveDict().ui;
    const resolvedScheme = state.dark ? 'dark' : 'light';
    if (colorSchemeMeta) {
      colorSchemeMeta.content = state.userThemeOverride ? resolvedScheme : 'light dark';
    }
    if (state.userThemeOverride) {
      rootEl.dataset.theme = resolvedScheme;
    } else {
      delete rootEl.dataset.theme;
    }

    if (state.dark) {
      themeToggle.setAttribute('aria-pressed', 'true');
      themeToggle.setAttribute('aria-label', ui.themeToLight);
      themeToggle.replaceChildren(
        createSvgIcon('<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>', '', '1.6')
      );
    } else {
      themeToggle.setAttribute('aria-pressed', 'false');
      themeToggle.setAttribute('aria-label', ui.themeToDark);
      themeToggle.replaceChildren(
        createSvgIcon('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path>', '', '1.6')
      );
    }
    if (animateIcon) {
      const iconSvg = themeToggle.querySelector('svg');
      if (iconSvg) {
        runElementAnimation(iconSvg, { rotate: [-28, 0], scale: [0.82, 1], opacity: [0.45, 1] }, {
          spring: true,
          bounce: 0.15,
          duration: 0.32,
          clearProps: ['opacity', 'transform']
        });
      }
    }
  }

  function applyStaticLocaleCopy() {
    const dict = getActiveDict();
    const ui = dict.ui;
    const sampleCount = getTotalSampleCount();
    const repo = getConfiguredRepo();

    rootEl.setAttribute('lang', dict.htmlLang);
    document.title = dict.docTitle;
    if (skipToMainLink) {
      skipToMainLink.textContent = state.lang === 'en' ? 'Skip to dictionary entries' : '跳转到词条列表';
    }

    langSwitch.dataset.active = state.lang;
    for (const btn of langButtons) {
      btn.setAttribute('aria-pressed', btn.dataset.lang === state.lang ? 'true' : 'false');
    }
    langSwitch.setAttribute('aria-label', ui.langSwitchAria);
    if (langSwitchMoreText) langSwitchMoreText.textContent = ui.langMoreLabel;
    if (langSwitchMore) {
      langSwitchMore.removeAttribute('title');
      langSwitchMore.removeAttribute('aria-label');
    }
    thumbsNav.setAttribute('aria-label', ui.thumbsAria);
    syncThumbsSide();
    mobileAlphaRail.setAttribute('aria-label', ui.mobileThumbsAria);

    headerSearchLabel.textContent = ui.headerSearchLabel;
    headerSearchBtn.setAttribute('aria-label', ui.headerSearchAria);
    headerAddLabel.textContent = ui.headerAddLabel;
    if (brandHomeLink) {
      brandHomeLink.href = `./?lang=${encodeURIComponent(state.lang)}`;
      brandHomeLink.setAttribute('aria-label', state.lang === 'en' ? 'Dictionary home' : '返回词典首页');
    }
    if (heroReplayLink) {
      heroReplayLink.href = `./replay/result.html?lang=${encodeURIComponent(state.lang)}`;
    }
    if (heroReplayTitle) heroReplayTitle.textContent = ui.replayLabel;
    if (hookInstallToggleLabel) hookInstallToggleLabel.textContent = ui.hookInstallToggleLabel;
    headerAddBtn.setAttribute('aria-label', ui.headerAddAria);
    const repoUrl = repo ? `https://github.com/${repo}` : 'https://github.com/';
    headerStarLabel.textContent = ui.headerStarLabel;
    headerGithubStar.href = repoUrl;
    headerGithubStar.setAttribute('aria-label', ui.headerStarAria);
    headerGithubStar.hidden = !repo;
    headerGithubLink.href = repoUrl;
    headerGithubLink.textContent = ui.headerGithubLabel;
    headerGithubLink.setAttribute('aria-label', ui.headerGithubAria);
    headerGithubLink.hidden = !repo;

    heroEyebrow.textContent = ui.heroEyebrow(sampleCount, dict.totalCatalogSize);
    heroTitle.textContent = ui.heroTitleHtml;
    if (heroLede && ui.heroLede) heroLede.textContent = ui.heroLede;
    if (heroNotice) {
      const noticeText = ui.heroNotice || '';
      heroNotice.textContent = noticeText;
      heroNotice.hidden = !noticeText;
    }
    if (metaDescription && ui.metaDescription) {
      metaDescription.setAttribute('content', ui.metaDescription);
    }
    // 词典 → 发布页 /intro/ 的入口，带上当前语言
    const introHref = `./intro/?lang=${encodeURIComponent(state.lang)}`;
    if (headerAboutLink) {
      headerAboutLink.href = introHref;
      headerAboutLink.textContent = ui.aboutLinkLabel;
    }
    if (footerAboutLink) {
      footerAboutLink.href = introHref;
      footerAboutLink.textContent = ui.footerAboutLabel;
    }
    if (landingAgentsSummary) landingAgentsSummary.textContent = ui.landingAgentsSummary;
    if (landingCopyPromptLabel) landingCopyPromptLabel.textContent = ui.landingCopyPromptLabel;
    if (landingAgentPrompt) landingAgentPrompt.textContent = ui.agentInstallPrompt;

    searchSrLabel.textContent = ui.searchSrLabel;
    searchInput.placeholder = ui.searchPlaceholder;
    searchClearLabel.textContent = ui.searchClearLabel;
    searchClear.setAttribute('aria-label', ui.searchClearAria);
    hotTermsLabel.textContent = ui.hotTermsLabel;
    levelAllLabel.textContent = ui.levelAllLabel;
    levelFiltersEl.setAttribute('aria-label', ui.levelFiltersAria);
    searchStatusReset.textContent = ui.statusReset;
    if (sortHotBtn) {
      sortHotBtn.textContent = ui.sortHotLabel;
      sortHotBtn.setAttribute('aria-pressed', state.sortByHot ? 'true' : 'false');
    }
    emptyAddWordLabel.textContent = ui.emptyAddWordLabel;
    emptyReset.textContent = ui.emptyReset;
    footerLegend.textContent = ui.footerLegend;

    suggestDialogTitle.textContent = ui.modalTitle;
    suggestClose.setAttribute('aria-label', ui.modalCloseAria);
    suggestTextLabel.textContent = ui.modalTextLabel;
    suggestText.placeholder = ui.modalTextPlaceholder;
    suggestCancel.textContent = ui.modalCancel;
    suggestSubmit.textContent = ui.modalSubmit;

    addWordDialogTitle.textContent = ui.addWordModalTitle;
    addWordDialogSub.textContent = ui.addWordModalSub;
    addWordClose.setAttribute('aria-label', ui.modalCloseAria);
    addWordTermLabel.textContent = ui.addWordTermLabel;
    addWordTerm.placeholder = ui.addWordTermPlaceholder;
    addWordLevelLabel.textContent = ui.addWordLevelLabel;
    addWordWhyLabel.textContent = ui.addWordWhyLabel;
    addWordWhy.placeholder = ui.addWordWhyPlaceholder;
    addWordAliasLabel.textContent = ui.addWordAliasLabel;
    addWordAlias.placeholder = ui.addWordAliasPlaceholder;
    addWordCancel.textContent = ui.addWordCancel;
    addWordSubmit.textContent = ui.addWordSubmit;

    populateAddWordSelects();
    renderThemeToggle();
  }

  function populateAddWordSelects() {
    const dict = getActiveDict();
    const prevLevel = addWordLevel.value;

    addWordLevel.innerHTML = '';
    for (const key of ['1', '2', '3']) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = dict.ui.levels[Number(key)];
      addWordLevel.appendChild(opt);
    }
    if (prevLevel && ['1', '2', '3'].includes(prevLevel)) {
      addWordLevel.value = prevLevel;
    }
  }

  let heatRevision = 0;
  let hotTermsCache = null;
  let hotTermsCacheKey = '';
  let renderedHotKey = '';
  const hotFetchGen = { zh: 0, en: 0 };
  const hotFetchCtrl = { zh: null, en: null };

  function invalidateHotTerms() {
    heatRevision += 1;
  }

  function sameCounts(prev, next) {
    if (prev === next) return true;
    if (!prev || !next) return false;
    const prevKeys = Object.keys(prev);
    if (prevKeys.length !== Object.keys(next).length) return false;
    for (let i = 0; i < prevKeys.length; i++) {
      const key = prevKeys[i];
      if (!Object.prototype.hasOwnProperty.call(next, key)) return false;
      if ((Number(prev[key]) || 0) !== (Number(next[key]) || 0)) return false;
    }
    return true;
  }

  function termRowSelector(term) {
    const escaped = typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
      ? CSS.escape(term)
      : String(term).replace(/["\\]/g, '\\$&');
    return `[data-term-row="${escaped}"]`;
  }

  function getTermHeat(term, langKey = state.lang) {
    const r = Number((state.remoteHotByLang[langKey] || {})[term]) || 0;
    const l = Number((state.localHotByLang[langKey] || {})[term]) || 0;
    return Math.max(r, l);
  }

  function hasVotedTerm(term, langKey = state.lang) {
    return Boolean((state.votedByLang[langKey] || {})[term]);
  }

  function sortItemsByHeat(items) {
    const rank = new Map();
    for (let i = 0; i < items.length; i++) rank.set(items[i], getTermHeat(items[i].term));
    items.sort((a, b) => rank.get(b) - rank.get(a));
    return items;
  }

  function getActiveHotTerms() {
    const cacheKey = `${state.lang}:${heatRevision}`;
    if (hotTermsCache && hotTermsCacheKey === cacheKey) return hotTermsCache;
    const dict = getActiveDict();
    const scored = [];
    for (const group of dict.groups) {
      for (const item of group.items) {
        const heat = getTermHeat(item.term);
        if (heat > 0) scored.push({ term: item.term, heat });
      }
    }
    scored.sort((a, b) => b.heat - a.heat);
    const maxChips = Math.max(5, dict.hotTerms.length);
    const merged = [];
    const seen = new Set();
    for (const s of scored) {
      if (merged.length >= maxChips) break;
      if (!seen.has(s.term)) {
        seen.add(s.term);
        merged.push(s.term);
      }
    }
    for (const fallback of dict.hotTerms) {
      if (merged.length >= maxChips) break;
      if (!seen.has(fallback)) {
        seen.add(fallback);
        merged.push(fallback);
      }
    }
    hotTermsCache = merged;
    hotTermsCacheKey = cacheKey;
    return merged;
  }

  async function fetchHotCounts(langKey) {
    if (!HOT_API) return;
    const gen = (hotFetchGen[langKey] = (hotFetchGen[langKey] || 0) + 1);
    if (hotFetchCtrl[langKey]) hotFetchCtrl[langKey].abort();
    const ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    hotFetchCtrl[langKey] = ctrl;
    const timer = ctrl ? setTimeout(() => ctrl.abort(), 1500) : null;
    try {
      const res = await fetch(`${HOT_API}/hot?lang=${encodeURIComponent(langKey)}`, {
        signal: ctrl ? ctrl.signal : undefined
      });
      if (gen !== hotFetchGen[langKey] || !res.ok) return;
      const data = await res.json();
      if (gen !== hotFetchGen[langKey]) return;
      if (!data || !data.counts || typeof data.counts !== 'object') return;
      if (sameCounts(state.remoteHotByLang[langKey], data.counts)) return;
      state.remoteHotByLang[langKey] = data.counts;
      invalidateHotTerms();
      if (state.lang !== langKey) return;
      if (state.sortByHot) renderDictionary();
      else refreshHeatInPlace();
    } catch (_) {
      // 静默降级，不影响静态词典浏览
    } finally {
      if (timer) clearTimeout(timer);
      if (hotFetchCtrl[langKey] === ctrl) hotFetchCtrl[langKey] = null;
    }
  }

  function refreshHeatInPlace() {
    renderHotTerms();
    if (!groupsContainer) return;
    for (const row of groupsContainer.querySelectorAll('.entry-row')) {
      const term = row.getAttribute('data-term-row');
      if (term) syncRowHeat(row, term, false);
    }
  }

  function createHeatBadge(heat) {
    const heatBadge = document.createElement('span');
    heatBadge.className = 'heat-badge';
    heatBadge.appendChild(
      createSvgIcon(
        '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline><polyline points="16 7 22 7 22 13"></polyline>',
        'heat-icon',
        '1.9'
      )
    );
    const valueEl = document.createElement('span');
    valueEl.className = 'heat-value';
    valueEl.textContent = String(heat);
    heatBadge.appendChild(valueEl);
    return heatBadge;
  }

  function triggerPulseClass(el, className) {
    if (!el) return;
    el.classList.remove(className);
    void el.offsetWidth;
    el.classList.add(className);
  }

  function syncVoteButton(voteBtn, term, animate = false, itemHeat = getTermHeat(term)) {
    if (!voteBtn) return;
    const ui = getActiveDict().ui;
    const isVoted = hasVotedTerm(term);
    const pressed = isVoted ? 'true' : 'false';
    if (voteBtn.getAttribute('aria-pressed') !== pressed) {
      voteBtn.setAttribute('aria-pressed', pressed);
    }
    const labelEl = voteBtn.querySelector('.vote-label');
    const text = `${ui.votePainBtn}${itemHeat > 0 ? ` · ${itemHeat}` : ''}`;
    if (labelEl && labelEl.textContent !== text) {
      labelEl.textContent = text;
    }

    if (animate) {
      triggerPulseClass(voteBtn, 'is-just-voted');
      const floatEl = document.createElement('span');
      floatEl.className = 'vote-float';
      floatEl.setAttribute('aria-hidden', 'true');
      floatEl.textContent = '+1';
      voteBtn.appendChild(floatEl);
      const cleanup = () => floatEl.remove();
      floatEl.addEventListener('animationend', cleanup, { once: true });
      window.setTimeout(cleanup, 700);
    }
  }

  function syncRowHeat(row, term, animate = false) {
    const heat = getTermHeat(term);
    const metaEnd = row.querySelector('.entry-meta-end');
    if (metaEnd) {
      let heatBadge = metaEnd.querySelector('.heat-badge');
      if (heat > 0) {
        if (!heatBadge) {
          heatBadge = createHeatBadge(heat);
          const levelBadge = metaEnd.querySelector('.level-badge');
          metaEnd.insertBefore(heatBadge, levelBadge || null);
        } else {
          const valEl = heatBadge.querySelector('.heat-value');
          if (valEl && valEl.textContent !== String(heat)) valEl.textContent = String(heat);
        }
        if (animate) triggerPulseClass(heatBadge, 'is-popping');
      } else if (heatBadge) {
        heatBadge.remove();
      }
    }
    syncVoteButton(row.querySelector('.vote-btn'), term, animate, heat);
  }

  function syncTermHeatInDom(term, animate = false) {
    if (!groupsContainer) return;
    for (const row of groupsContainer.querySelectorAll(termRowSelector(term))) {
      syncRowHeat(row, term, animate);
    }
  }

  let turnstileScriptPromise = null;
  let turnstileQueue = Promise.resolve();
  let turnstileWidgetId = null;
  let turnstileHostEl = null;
  let turnstilePending = null;

  function loadTurnstileScript() {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return Promise.resolve(null);
    }
    if (window.turnstile) return Promise.resolve(window.turnstile);
    if (turnstileScriptPromise) return turnstileScriptPromise;
    turnstileScriptPromise = new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      script.defer = true;
      script.onload = () => resolve(window.turnstile || null);
      script.onerror = () => {
        turnstileScriptPromise = null;
        resolve(null);
      };
      document.head.appendChild(script);
    });
    return turnstileScriptPromise;
  }

  function executeTurnstileOnce() {
    return loadTurnstileScript().then((api) => {
      if (!api || typeof api.render !== 'function') return '';
      return new Promise((resolve) => {
        let settled = false;
        const finish = (token) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          turnstilePending = null;
          resolve(typeof token === 'string' ? token : '');
        };
        const timer = window.setTimeout(() => finish(''), 10000);
        turnstilePending = finish;

        if (!turnstileHostEl) {
          turnstileHostEl = document.createElement('div');
          turnstileHostEl.className = 'turnstile-host';
          turnstileHostEl.setAttribute('aria-hidden', 'true');
          turnstileHostEl.style.cssText = 'position:fixed;bottom:12px;right:12px;z-index:2147483647;';
          document.body.appendChild(turnstileHostEl);
        }

        try {
          if (turnstileWidgetId === null) {
            turnstileWidgetId = api.render(turnstileHostEl, {
              sitekey: TURNSTILE_SITE_KEY,
              appearance: 'interaction-only',
              execution: 'execute',
              callback: (token) => {
                if (turnstilePending) turnstilePending(token);
              },
              'error-callback': () => {
                if (turnstilePending) turnstilePending('');
              },
              'expired-callback': () => {
                if (turnstilePending) turnstilePending('');
              },
            });
          } else {
            api.reset(turnstileWidgetId);
          }
          api.execute(turnstileWidgetId);
        } catch (_) {
          finish('');
        }
      });
    });
  }

  function requestTurnstileToken() {
    if (!TURNSTILE_SITE_KEY) return Promise.resolve('');
    const run = turnstileQueue.then(executeTurnstileOnce, executeTurnstileOnce);
    turnstileQueue = run.then(() => undefined, () => undefined);
    return run;
  }

  function voteTerm(term) {
    const langKey = state.lang;
    const ui = getActiveDict().ui;
    if (hasVotedTerm(term, langKey)) return;

    const prevLocalHeat = Number(state.localHotByLang[langKey][term]) || 0;
    state.votedByLang[langKey][term] = true;
    state.localHotByLang[langKey][term] = getTermHeat(term, langKey) + 1;
    writeStorage(VOTED_STORAGE_KEY, JSON.stringify(state.votedByLang));
    writeStorage(LOCAL_HOT_STORAGE_KEY, JSON.stringify(state.localHotByLang));
    invalidateHotTerms();

    renderHotTerms();
    syncTermHeatInDom(term, true);
    showToast(ui.toastVoted(term));

    if (HOT_API) {
      requestTurnstileToken()
        .then((turnstileToken) => {
          const payload = { term, lang: langKey };
          if (turnstileToken) payload.turnstileToken = turnstileToken;
          return fetch(`${HOT_API}/hit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            keepalive: true
          });
        })
        .then((res) => {
          if (res.status === 403) {
            delete state.votedByLang[langKey][term];
            if (prevLocalHeat > 0) state.localHotByLang[langKey][term] = prevLocalHeat;
            else delete state.localHotByLang[langKey][term];
            writeStorage(VOTED_STORAGE_KEY, JSON.stringify(state.votedByLang));
            writeStorage(LOCAL_HOT_STORAGE_KEY, JSON.stringify(state.localHotByLang));
            invalidateHotTerms();
            if (state.lang === langKey) {
              renderHotTerms();
              syncTermHeatInDom(term, false);
            }
            return null;
          }
          return res.ok ? res.json() : null;
        })
        .then((data) => {
          if (!data || typeof data.count !== 'number') return;
          const bucket = state.remoteHotByLang[langKey];
          let changed = false;
          if ((Number(bucket[term]) || 0) !== data.count) {
            bucket[term] = data.count;
            changed = true;
          }
          if (data.limited && (Number(state.localHotByLang[langKey][term]) || 0) !== data.count) {
            state.localHotByLang[langKey][term] = data.count;
            writeStorage(LOCAL_HOT_STORAGE_KEY, JSON.stringify(state.localHotByLang));
            changed = true;
          }
          if (!changed) return;
          invalidateHotTerms();
          if (state.lang === langKey) {
            renderHotTerms();
            syncTermHeatInDom(term, false);
          }
        })
        .catch(() => {});
    }
  }

  function renderHotTerms() {
    const dict = getActiveDict();
    const terms = getActiveHotTerms();
    const trimmed = state.query.trim().toLowerCase();
    const key = `${state.lang}\0${terms.join('\0')}`;
    if (renderedHotKey === key && hotTermsList.childElementCount === terms.length) {
      const buttons = hotTermsList.children;
      for (let i = 0; i < terms.length; i++) {
        buttons[i].classList.toggle('is-active', trimmed === terms[i].toLowerCase());
      }
      return;
    }
    renderedHotKey = key;
    hotTermsList.replaceChildren();
    for (const term of terms) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'hot-term-chip' + (trimmed === term.toLowerCase() ? ' is-active' : '');
      btn.textContent = term;
      btn.setAttribute('aria-label', dict.ui.hotTermAria(term));
      btn.addEventListener('click', () => {
        if (state.query.trim().toLowerCase() === term.toLowerCase() && state.levelFilter === 'all') {
          resetFilters(false);
          return;
        }
        state.query = term;
        state.levelFilter = 'all';
        getActiveOpenTerms()[term] = true;
        searchInput.value = term;
        renderDictionary({ animateGroups: true });
      });
      hotTermsList.appendChild(btn);
    }
  }

  const levelRing = document.createElement('span');
  levelRing.className = 'level-ring';
  levelRing.setAttribute('aria-hidden', 'true');
  let levelRingPlaced = false;
  let levelRingAnimation = null;

  function moveLevelRing(animate = true) {
    const row = levelAllBtn.parentElement;
    if (!row.contains(levelRing)) row.appendChild(levelRing);
    const active = row.querySelector('[aria-pressed="true"]');
    if (!active) {
      levelRingAnimation?.cancel();
      levelRingAnimation = null;
      levelRingPlaced = false;
      levelRing.style.opacity = '0';
      return;
    }
    const rowRect = row.getBoundingClientRect();
    const activeRect = active.getBoundingClientRect();
    const previousRect = levelRingPlaced ? levelRing.getBoundingClientRect() : null;
    levelRingAnimation?.cancel();
    levelRingAnimation = null;
    const left = activeRect.left - rowRect.left;
    const top = activeRect.top - rowRect.top;
    const targetTransform = `translate(${left}px, ${top}px)`;
    levelRing.style.width = `${activeRect.width}px`;
    levelRing.style.height = `${activeRect.height}px`;
    levelRing.style.transform = targetTransform;
    levelRing.style.opacity = '1';
    levelRingPlaced = true;
    if (!animate || isReducedMotion() || !previousRect || typeof levelRing.animate !== 'function' || !activeRect.width || !activeRect.height) return;
    const unchanged = Math.abs(previousRect.left - activeRect.left) < .5
      && Math.abs(previousRect.top - activeRect.top) < .5
      && Math.abs(previousRect.width - activeRect.width) < .5
      && Math.abs(previousRect.height - activeRect.height) < .5;
    if (unchanged) return;
    const animation = levelRing.animate([
      { transform: `translate(${previousRect.left - rowRect.left}px, ${previousRect.top - rowRect.top}px) scale(${previousRect.width / activeRect.width}, ${previousRect.height / activeRect.height})` },
      { transform: targetTransform },
    ], { duration: 280, easing: 'cubic-bezier(0.32, 0.72, 0, 1)' });
    levelRingAnimation = animation;
    animation.finished.then(() => {
      if (levelRingAnimation !== animation) return;
      levelRingAnimation = null;
      animation.cancel();
    }).catch(() => {});
  }

  function renderLevelFilters(counts) {
    const ui = getActiveDict().ui;
    levelAllBtn.setAttribute('aria-pressed', state.levelFilter === 'all' ? 'true' : 'false');
    levelAllCount.textContent = String(counts.all);

    levelFiltersEl.innerHTML = '';
    for (const card of ui.levelCards) {
      const item = document.createElement('div');
      item.className = 'level-badge-item';

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'level-chip-btn';
      btn.dataset.level = card.key;
      const isSelected = state.levelFilter === card.key;
      btn.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
      btn.setAttribute('aria-describedby', `level-tip-${card.key}`);

      const labelSpan = document.createElement('span');
      labelSpan.textContent = card.label;

      const countSpan = document.createElement('span');
      countSpan.className = 'level-chip-count';
      countSpan.textContent = String(counts[card.key]);

      btn.append(labelSpan, countSpan);
      btn.addEventListener('click', () => {
        state.levelFilter = state.levelFilter === card.key ? 'all' : card.key;
        renderDictionary({ animateGroups: true });
      });

      const tooltip = document.createElement('div');
      tooltip.className = 'level-tooltip';
      tooltip.id = `level-tip-${card.key}`;
      tooltip.setAttribute('role', 'tooltip');
      tooltip.dataset.level = card.key;

      const tipTitle = document.createElement('span');
      tipTitle.className = 'level-tooltip-title';
      const tipDot = document.createElement('span');
      tipDot.className = 'level-tooltip-dot';
      tipDot.setAttribute('aria-hidden', 'true');
      const tipLabel = document.createElement('span');
      tipLabel.textContent = card.label;
      tipTitle.append(tipDot, tipLabel);

      const tipDesc = document.createElement('span');
      tipDesc.className = 'level-tooltip-desc';
      tipDesc.textContent = card.desc;

      tooltip.append(tipTitle, tipDesc);
      item.append(btn, tooltip);
      levelFiltersEl.appendChild(item);
    }
  }

  function renderBulkToggle(groups) {
    const ui = getActiveDict().ui;
    const openTerms = getActiveOpenTerms();
    const visibleItems = groups.flatMap((g) => g.items);
    if (visibleItems.length === 0) {
      toggleAllBtn.disabled = true;
      toggleAllBtn.innerHTML = '';
      toggleAllBtn.append(
        createSvgIcon('<path d="m6 9 6 6 6-6"></path>'),
        document.createTextNode(ui.expandAll)
      );
      return;
    }

    toggleAllBtn.disabled = false;
    const allOpen = visibleItems.every((item) => !!openTerms[item.term]);
    toggleAllBtn.innerHTML = '';
    if (allOpen) {
      toggleAllBtn.append(
        createSvgIcon('<path d="m18 15-6-6-6 6"></path>'),
        document.createTextNode(ui.collapseAll)
      );
      toggleAllBtn.setAttribute('aria-pressed', 'true');
    } else {
      toggleAllBtn.append(
        createSvgIcon('<path d="m6 9 6 6 6-6"></path>'),
        document.createTextNode(ui.expandAll)
      );
      toggleAllBtn.setAttribute('aria-pressed', 'false');
    }
  }

  function scrollToLetter(letter) {
    const target = document.getElementById(`group-${letter}`);
    if (target) {
      state.currentLetter = letter;
      syncCurrentLetterHighlight();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      target.classList.remove('is-jump-flash');
      void target.offsetWidth;
      target.classList.add('is-jump-flash');
      setTimeout(() => target.classList.remove('is-jump-flash'), 1400);
    }
  }

  /* macOS Dock-style magnification controller for right-edge A-Z strip */
  const dockState = {
    rafId: null,
    pointerY: null,
    baseMetrics: null
  };

  function invalidateDockMetrics() {
    dockState.baseMetrics = null;
  }

  function resetDockMagnification() {
    if (dockState.rafId) {
      cancelAnimationFrame(dockState.rafId);
      dockState.rafId = null;
    }
    dockState.pointerY = null;
    thumbsNav.classList.remove('is-dock-active');
    const btns = thumbsTrack.querySelectorAll('.thumb-btn');
    for (const btn of btns) {
      btn.style.transform = '';
      btn.style.zIndex = '';
      btn.classList.remove('is-dock-focus');
    }
  }

  function getDockBaseMetrics() {
    if (dockState.baseMetrics) return dockState.baseMetrics;
    const btns = Array.from(thumbsTrack.querySelectorAll('.thumb-btn'));
    if (btns.length === 0) return [];
    const trackRect = thumbsTrack.getBoundingClientRect();
    dockState.baseMetrics = btns.map((btn) => ({
      el: btn,
      centerY: trackRect.top + btn.offsetTop + btn.offsetHeight / 2,
      height: btn.offsetHeight,
      isActive: btn.classList.contains('is-active')
    }));
    return dockState.baseMetrics;
  }

  function applyDockMagnification() {
    dockState.rafId = null;
    if (dockState.pointerY === null) return;
    if (reducedMotionMedia && reducedMotionMedia.matches) return;

    const metrics = getDockBaseMetrics();
    if (metrics.length === 0) return;

    const pointerY = dockState.pointerY;
    const radius = 84;
    const scales = new Array(metrics.length);
    const extras = new Array(metrics.length);
    const influences = new Array(metrics.length);

    let maxInf = -1;
    let focusIndex = -1;

    for (let i = 0; i < metrics.length; i += 1) {
      const m = metrics[i];
      const dist = Math.abs(pointerY - m.centerY);
      const raw = dist < radius ? Math.cos((dist / radius) * (Math.PI / 2)) : 0;
      const influence = Math.pow(Math.max(0, raw), 1.35);
      const maxGain = m.isActive ? 0.72 : 0.36;
      const scale = 1 + influence * maxGain;
      influences[i] = influence;
      scales[i] = scale;
      extras[i] = m.height * (scale - 1);
      if (influence > maxInf) {
        maxInf = influence;
        focusIndex = i;
      }
    }

    const prefixCenters = new Array(metrics.length);
    let running = 0;
    for (let i = 0; i < metrics.length; i += 1) {
      prefixCenters[i] = running + extras[i] * 0.5;
      running += extras[i];
    }

    let cursorExtra = 0;
    if (pointerY <= metrics[0].centerY) {
      cursorExtra = prefixCenters[0];
    } else if (pointerY >= metrics[metrics.length - 1].centerY) {
      cursorExtra = prefixCenters[metrics.length - 1];
    } else {
      for (let i = 0; i < metrics.length - 1; i += 1) {
        const y0 = metrics[i].centerY;
        const y1 = metrics[i + 1].centerY;
        if (pointerY >= y0 && pointerY <= y1) {
          const t = y1 === y0 ? 0 : (pointerY - y0) / (y1 - y0);
          cursorExtra = prefixCenters[i] + (prefixCenters[i + 1] - prefixCenters[i]) * t;
          break;
        }
      }
    }

    for (let i = 0; i < metrics.length; i += 1) {
      const el = metrics[i].el;
      const inf = influences[i];
      const scale = scales[i];
      const shiftY = prefixCenters[i] - cursorExtra;
      const shiftX = (state.thumbsSide === 'left' ? 4 : -4) * inf;

      if (inf > 0.005 || Math.abs(shiftY) > 0.2) {
        el.style.transform = `translate3d(${shiftX.toFixed(2)}px, ${shiftY.toFixed(2)}px, 0) scale(${scale.toFixed(4)})`;
        el.style.zIndex = String(Math.round(10 + inf * 30));
      } else {
        el.style.transform = '';
        el.style.zIndex = '';
      }
      el.classList.toggle('is-dock-focus', i === focusIndex && maxInf > 0.35);
    }
  }

  function scheduleDockMagnification(clientY) {
    dockState.pointerY = clientY;
    if (!thumbsNav.classList.contains('is-dock-active')) {
      thumbsNav.classList.add('is-dock-active');
    }
    if (!dockState.rafId) {
      dockState.rafId = requestAnimationFrame(applyDockMagnification);
    }
  }

  function renderAlphaNavs(activeLetters) {
    const dict = getActiveDict();
    const letters = dict.letters;
    resetDockMagnification();
    invalidateDockMetrics();
    thumbsTrack.innerHTML = '';

    for (const ch of letters) {
      const btn = document.createElement('button');
      btn.type = 'button';
      const isActive = activeLetters.has(ch);
      btn.className = 'thumb-btn' + (isActive ? ' is-active' : '');
      btn.dataset.letter = ch;
      btn.textContent = ch;
      if (isActive) {
        btn.setAttribute('aria-label', dict.ui.letterJumpAria(ch));
        btn.addEventListener('click', () => scrollToLetter(ch));
      } else {
        btn.disabled = true;
        btn.setAttribute('aria-disabled', 'true');
      }
      thumbsTrack.appendChild(btn);
    }

    const activeList = letters.filter((ch) => activeLetters.has(ch));
    mobileAlphaRail.innerHTML = '';
    if (activeList.length === 0) {
      mobileAlphaWrap.hidden = true;
    } else {
      mobileAlphaWrap.hidden = false;
      for (const ch of activeList) {
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.className = 'alpha-pill';
        pill.dataset.letter = ch;
        pill.textContent = ch;
        pill.setAttribute('aria-label', dict.ui.letterJumpAria(ch));
        pill.addEventListener('click', () => scrollToLetter(ch));
        mobileAlphaRail.appendChild(pill);
      }
    }
  }

  function syncCurrentLetterHighlight() {
    const thumbBtns = thumbsTrack.querySelectorAll('.thumb-btn');
    for (const btn of thumbBtns) {
      const isCurr = btn.classList.contains('is-active') && btn.dataset.letter === state.currentLetter;
      btn.classList.toggle('is-current', isCurr);
      if (isCurr) {
        btn.setAttribute('aria-current', 'true');
      } else {
        btn.removeAttribute('aria-current');
      }
    }

    const mobileBtns = mobileAlphaRail.querySelectorAll('.alpha-pill');
    for (const btn of mobileBtns) {
      const isCurr = btn.dataset.letter === state.currentLetter;
      btn.classList.toggle('is-current', isCurr);
      if (isCurr) {
        btn.setAttribute('aria-current', 'true');
      } else {
        btn.removeAttribute('aria-current');
      }
    }
  }

  function updateCurrentLetterFromScroll() {
    const groupEls = Array.from(groupsContainer.querySelectorAll('.letter-group'));
    if (groupEls.length === 0) {
      state.currentLetter = null;
      syncCurrentLetterHighlight();
      return;
    }

    const threshold = window.innerWidth <= 760 ? 156 : 108;
    let activeLetter = groupEls[0].dataset.letter;
    for (const el of groupEls) {
      const rect = el.getBoundingClientRect();
      if (rect.top <= threshold) {
        activeLetter = el.dataset.letter;
      } else {
        break;
      }
    }

    if (state.currentLetter !== activeLetter) {
      state.currentLetter = activeLetter;
      syncCurrentLetterHighlight();
    }
  }

  function createSuggestRow(item) {
    const ui = getActiveDict().ui;
    const label = document.createElement('span');
    label.className = 'detail-label';
    label.textContent = ui.detailSuggest;

    const box = document.createElement('div');
    box.className = 'suggest-box';

    const textSpan = document.createElement('div');
    textSpan.className = 'suggest-text';
    textSpan.appendChild(createHighlightedFragment(item.suggest, state.query));

    box.appendChild(textSpan);
    return [label, box];
  }

  function createContextRow(labelText, valueText, variant) {
    const ui = getActiveDict().ui;
    const label = document.createElement('span');
    label.className = 'detail-label';
    label.textContent = labelText;

    const wrap = document.createElement('div');
    wrap.className = 'context-row';

    const tag = document.createElement('span');
    tag.setAttribute('aria-hidden', 'true');
    if (variant === 'ok') {
      tag.className = 'context-tag context-tag--ok';
      tag.title = ui.detailOkTag;
      tag.appendChild(createSvgIcon('<path d="M20 6 9 17l-5-5"></path>'));
    } else {
      tag.className = 'context-tag context-tag--bad';
      tag.title = ui.detailBadTag;
      tag.appendChild(createSvgIcon('<path d="M18 6 6 18M6 6l12 12"></path>'));
    }

    const body = document.createElement('span');
    body.className = 'context-body';
    body.appendChild(createHighlightedFragment(valueText, state.query));

    wrap.append(tag, body);
    return [label, wrap];
  }

  function createPlainDetailPair(labelText, valueText) {
    const label = document.createElement('span');
    label.className = 'detail-label';
    label.textContent = labelText;

    const value = document.createElement('span');
    value.className = 'detail-value';
    value.appendChild(createHighlightedFragment(valueText, state.query));

    return [label, value];
  }

  function renderDictionary(renderOpt) {
    const opts = typeof renderOpt === 'string'
      ? { focusTerm: renderOpt }
      : (renderOpt && typeof renderOpt === 'object' ? renderOpt : {});
    const focusTermAfterRender = opts.focusTerm || null;
    const previousRowPositions = opts.flip ? captureRowPositions() : null;
    const dict = getActiveDict();
    const ui = dict.ui;
    const allGroups = getAllGroups();
    const sampleCount = getTotalSampleCount(allGroups);
    const openTerms = getActiveOpenTerms();
    const communityMap = getActiveCommunityMap();

    const queryGroups = getQueryMatchedGroups(allGroups);
    const counts = getLevelCounts(queryGroups);
    const groups = getFilteredGroups(queryGroups);
    const activeLetters = new Set(groups.map((g) => g.letter));

    renderHotTerms();
    renderLevelFilters(counts);
    moveLevelRing();
    renderBulkToggle(groups);
    renderAlphaNavs(activeLetters);
    heroEyebrow.textContent = ui.heroEyebrow(sampleCount, dict.totalCatalogSize);

    const trimmedQuery = state.query.trim();
    const hasQuery = trimmedQuery.length > 0;
    const hasLevel = state.levelFilter !== 'all';
    const hasAnyFilter = hasQuery || hasLevel;

    searchClear.hidden = !hasQuery;
    searchKbd.hidden = hasQuery;

    const totalVisible = groups.reduce((acc, g) => acc + g.items.length, 0);
    if (hasAnyFilter) {
      searchStatus.hidden = false;
      const parts = [];
      if (hasQuery) parts.push(ui.statusQueryPart(trimmedQuery));
      if (hasLevel) {
        const activeCard = ui.levelCards.find((card) => card.key === state.levelFilter);
        parts.push(ui.statusLevelPart(activeCard ? activeCard.label : ui.levels[Number(state.levelFilter)]));
      }
      searchStatusText.textContent = ui.statusText(parts, totalVisible);
    } else {
      searchStatus.hidden = true;
    }

    groupsContainer.replaceChildren();

    if (groups.length === 0) {
      groupsContainer.hidden = true;
      emptyState.hidden = false;
      emptyAddWordLabel.textContent = hasQuery ? ui.emptyAddWordQueryLabel(trimmedQuery) : ui.emptyAddWordLabel;
      if (hasQuery && hasLevel) {
        const lvlLabel = ui.levels[Number(state.levelFilter)];
        emptyTitle.textContent = ui.emptyBothTitle(trimmedQuery, lvlLabel);
        emptyDesc.textContent = ui.emptyBothDesc;
      } else if (hasLevel) {
        const lvlLabel = ui.levels[Number(state.levelFilter)];
        emptyTitle.textContent = ui.emptyLevelTitle(lvlLabel);
        emptyDesc.textContent = ui.emptyLevelDesc;
      } else {
        emptyTitle.textContent = ui.emptyQueryTitle(trimmedQuery);
        emptyDesc.textContent = ui.emptyQueryDesc;
      }
      state.currentLetter = null;
      syncCurrentLetterHighlight();
      footerMeta.textContent = ui.footerMetaEmpty(sampleCount, dict.totalCatalogSize);
      syncDockedSearchBar();
      updateHeaderScrollProgressFallback();
      return;
    }

    groupsContainer.hidden = false;
    emptyState.hidden = true;

    const displayGroups = state.sortByHot
      ? [{
          letter: ui.hotGroupLabel,
          items: sortItemsByHeat(groups.flatMap((g) => g.items))
        }]
      : groups;

    for (const group of displayGroups) {
      const section = document.createElement('section');
      section.className = 'letter-group';
      section.id = `group-${group.letter}`;
      section.dataset.letter = group.letter;
      section.setAttribute('aria-labelledby', `heading-${group.letter}`);

      const header = document.createElement('div');
      header.className = 'letter-header';

      const charEl = document.createElement('h2');
      charEl.className = 'letter-char';
      charEl.id = `heading-${group.letter}`;
      charEl.textContent = group.letter;

      const countEl = document.createElement('span');
      countEl.className = 'letter-count';
      countEl.textContent = ui.letterCount(group.items.length);

      header.append(charEl, countEl);
      section.appendChild(header);

      for (const item of group.items) {
        const isOpen = !!openTerms[item.term];
        const row = document.createElement('article');
        row.className = 'entry-row';
        row.setAttribute('data-term-row', item.term);

        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'entry-trigger';
        trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        trigger.setAttribute('data-term-toggle', item.term);

        const head = document.createElement('span');
        head.className = 'entry-head';

        const termEl = document.createElement('span');
        termEl.className = 'entry-term';
        termEl.appendChild(createHighlightedFragment(item.term, state.query));

        head.append(termEl);

        const whyEl = document.createElement('span');
        whyEl.className = 'entry-why od-truncate';
        whyEl.appendChild(createHighlightedFragment(item.why, state.query));

        const metaEnd = document.createElement('span');
        metaEnd.className = 'entry-meta-end';

        if (item.isCustom) {
          const localTag = document.createElement('span');
          localTag.className = 'local-badge';
          localTag.textContent = ui.localPreviewBadge;
          metaEnd.appendChild(localTag);
        }

        const heat = getTermHeat(item.term);
        if (heat > 0) {
          metaEnd.appendChild(createHeatBadge(heat));
        }

        const badge = document.createElement('span');
        badge.className = 'level-badge';
        badge.setAttribute('data-level', String(item.level));
        badge.textContent = ui.levels[item.level];

        const chevron = createSvgIcon('<path d="m6 9 6 6 6-6"></path>', 'entry-chevron');
        metaEnd.append(badge, chevron);

        trigger.append(head, whyEl, metaEnd);
        row.appendChild(trigger);

        const panel = document.createElement('div');
        panel.className = 'entry-panel';
        panel.hidden = isOpen ? false : COLLAPSED_PANEL_HIDDEN;

        trigger.addEventListener('click', () => {
          const nextOpen = !openTerms[item.term];
          openTerms[item.term] = nextOpen;
          animateEntryPanelToggle(panel, trigger, nextOpen);
          renderBulkToggle(getFilteredGroups());
        });

        if (item.suggest) panel.append(...createSuggestRow(item));
        if (item.ok) panel.append(...createContextRow(ui.detailOk, item.ok, 'ok'));
        if (item.bad) panel.append(...createContextRow(ui.detailBad, item.bad, 'bad'));
        if (item.alias) panel.append(...createPlainDetailPair(ui.detailAlias, item.alias));

        const communityList = communityMap[item.term] || [];
        if (communityList.length > 0) {
          const cLabel = document.createElement('span');
          cLabel.className = 'detail-label';
          cLabel.textContent = ui.detailCommunity;

          const cWrap = document.createElement('ul');
          cWrap.className = 'community-list';
          communityList.forEach((entry, idx) => {
            const li = document.createElement('li');
            li.className = 'community-item';

            const mainDiv = document.createElement('div');
            mainDiv.className = 'community-item-main';

            const tagSpan = document.createElement('span');
            tagSpan.className = 'community-item-tag';
            tagSpan.textContent = entry.mode === 'structured' ? ui.communityStructuredTag : ui.communityFreeformTag;
            mainDiv.appendChild(tagSpan);

            if (entry.mode === 'structured' && entry.structured) {
              const s = entry.structured;
              const structList = document.createElement('div');
              structList.className = 'community-structured-list';
              const rows = [
                [ui.modalFmtLevelLabel, ui.levels[s.level] || String(s.level)],
                [ui.modalFmtWhyLabel, s.why],
                [ui.detailSuggest, s.suggest],
                ...(s.ok ? [[ui.detailOk, s.ok]] : []),
                ...(s.bad ? [[ui.detailBad, s.bad]] : []),
                ...(s.alias ? [[ui.detailAlias, s.alias]] : [])
              ];
              for (const [kLabel, valText] of rows) {
                if (!valText) continue;
                const rowDiv = document.createElement('div');
                rowDiv.className = 'community-structured-row';
                const kEl = document.createElement('span');
                kEl.className = 'community-structured-key';
                kEl.textContent = `${kLabel}：`;
                const vEl = document.createElement('span');
                vEl.className = 'community-structured-val';
                vEl.appendChild(createHighlightedFragment(valText, state.query));
                rowDiv.append(kEl, vEl);
                structList.appendChild(rowDiv);
              }
              mainDiv.appendChild(structList);
            } else {
              const textDiv = document.createElement('div');
              textDiv.className = 'community-item-text';
              textDiv.appendChild(createHighlightedFragment(entry.text, state.query));
              mainDiv.appendChild(textDiv);

              if (entry.note) {
                const noteDiv = document.createElement('div');
                noteDiv.className = 'community-item-note';
                noteDiv.append(
                  document.createTextNode(ui.communityExamplePrefix),
                  createHighlightedFragment(entry.note, state.query)
                );
                mainDiv.appendChild(noteDiv);
              }
            }

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'local-remove-btn';
            removeBtn.textContent = ui.removeLocalNote;
            removeBtn.addEventListener('click', () => {
              const list = communityMap[item.term] || [];
              const nextList = list.filter((_, i) => i !== idx);
              if (nextList.length > 0) {
                communityMap[item.term] = nextList;
              } else {
                delete communityMap[item.term];
              }
              savePersistedCommunity();
              renderDictionary();
              showToast(ui.toastRemovedNote);
            });

            li.append(mainDiv, removeBtn);
            cWrap.appendChild(li);
          });
          panel.append(cLabel, cWrap);
        }

        const actionsCell = document.createElement('div');
        actionsCell.className = 'entry-actions-cell';

        const voteBtn = document.createElement('button');
        voteBtn.type = 'button';
        voteBtn.className = 'btn btn-secondary vote-btn';
        voteBtn.appendChild(
          createSvgIcon(
            '<path d="M12 19V5"></path><path d="m5 12 7-7 7 7"></path>',
            'vote-icon',
            '1.9'
          )
        );
        const voteLabel = document.createElement('span');
        voteLabel.className = 'vote-label';
        voteBtn.appendChild(voteLabel);
        syncVoteButton(voteBtn, item.term, false, heat);
        voteBtn.addEventListener('click', () => voteTerm(item.term));

        const suggestBtn = document.createElement('button');
        suggestBtn.type = 'button';
        suggestBtn.className = 'btn btn-secondary';
        suggestBtn.setAttribute('data-suggest-trigger', item.term);
        suggestBtn.textContent = ui.suggestBtn;
        suggestBtn.addEventListener('click', () => openSuggestModal(item.term));

        actionsCell.append(voteBtn, suggestBtn);

        if (item.isCustom) {
          const removeTermBtn = document.createElement('button');
          removeTermBtn.type = 'button';
          removeTermBtn.className = 'btn btn-secondary';
          removeTermBtn.textContent = ui.removeLocalTerm;
          removeTermBtn.addEventListener('click', () => {
            state.customTermsByLang[state.lang] = getActiveCustomTerms().filter((t) => t.term !== item.term);
            delete getActiveOpenTerms()[item.term];
            if (communityMap[item.term]) {
              delete communityMap[item.term];
              savePersistedCommunity();
            }
            savePersistedCustomTerms();
            renderDictionary();
            showToast(ui.toastRemovedTerm(item.term));
          });
          actionsCell.appendChild(removeTermBtn);
        }

        panel.appendChild(actionsCell);

        row.appendChild(panel);
        section.appendChild(row);
      }

      groupsContainer.appendChild(section);
    }

    footerMeta.textContent = hasAnyFilter
      ? ui.footerMetaFiltered(totalVisible, sampleCount, dict.totalCatalogSize)
      : ui.footerMetaDefault(sampleCount, dict.totalCatalogSize);

    syncDockedSearchBar();
    updateCurrentLetterFromScroll();
    updateHeaderScrollProgressFallback();

    playRowFlip(previousRowPositions);

    if (opts.animateGroups && !isReducedMotion()) {
      const groupNodes = Array.from(groupsContainer.querySelectorAll('.letter-group'));
      groupNodes.forEach((groupEl, idx) => {
        runElementAnimation(
          groupEl,
          { opacity: [0, 1], y: [10, 0] },
          {
            duration: 0.24,
            delay: Math.min(idx, 6) * 0.03,
            ease: MOTION_EASE_OUT,
            clearProps: ['opacity', 'transform']
          }
        );
      });
    }

    if (opts.highlightTerm && !isReducedMotion()) {
      const targetTrigger = groupsContainer.querySelector(`[data-term-toggle="${CSS.escape(opts.highlightTerm)}"]`);
      const targetRow = targetTrigger ? targetTrigger.closest('.entry-row') : null;
      if (targetRow) {
        const pulseBg = getCssTokenColor('--accent-soft', 'rgba(13, 148, 136, 0.14)');
        runElementAnimation(
          targetRow,
          { backgroundColor: [pulseBg, 'transparent'] },
          {
            duration: 0.95,
            ease: MOTION_EASE_OUT,
            clearProps: ['backgroundColor']
          }
        );
      }
    }

    if (opts.highlightCommunityTerm && !isReducedMotion()) {
      const targetTrigger = groupsContainer.querySelector(`[data-term-toggle="${CSS.escape(opts.highlightCommunityTerm)}"]`);
      const targetRow = targetTrigger ? targetTrigger.closest('.entry-row') : null;
      const items = targetRow ? targetRow.querySelectorAll('.community-item') : null;
      const latestItem = items && items.length > 0 ? items[items.length - 1] : null;
      if (latestItem) {
        const pulseBg = getCssTokenColor('--accent-soft', 'rgba(13, 148, 136, 0.14)');
        const baseBg = getCssTokenColor('--surface-subtle', 'transparent');
        runElementAnimation(
          latestItem,
          { opacity: [0, 1], y: [6, 0], backgroundColor: [pulseBg, baseBg] },
          {
            duration: 0.72,
            ease: MOTION_EASE_OUT,
            clearProps: ['opacity', 'transform', 'backgroundColor']
          }
        );
      }
    }

    if (focusTermAfterRender) {
      const targetBtn = groupsContainer.querySelector(`[data-term-toggle="${CSS.escape(focusTermAfterRender)}"]`);
      if (targetBtn) targetBtn.focus({ preventScroll: true });
    }
  }

  function showToast(message) {
    const token = (state.toastToken || 0) + 1;
    state.toastToken = token;
    if (state.toastTimer) clearTimeout(state.toastTimer);
    if (activeToastCtrl) {
      try { activeToastCtrl.cancel(); } catch (_) {}
      activeToastCtrl = null;
    }

    toastEl.textContent = message;
    toastEl.hidden = false;

    if (!isReducedMotion()) {
      activeToastCtrl = runElementAnimation(
        toastEl,
        { opacity: [0, 1], y: [10, 0], scale: [0.97, 1] },
        {
          spring: true,
          bounce: 0.15,
          duration: 0.26,
          clearProps: ['opacity', 'transform']
        }
      );
    } else {
      clearAnimationInlineProps(toastEl, ['opacity', 'transform']);
    }

    state.toastTimer = setTimeout(() => {
      if (state.toastToken !== token) return;
      if (isReducedMotion()) {
        toastEl.hidden = true;
        return;
      }
      activeToastCtrl = runElementAnimation(
        toastEl,
        { opacity: [1, 0], y: [0, 6] },
        { duration: 0.16, ease: MOTION_EASE_OUT }
      );
      activeToastCtrl.finished.then(() => {
        if (state.toastToken !== token) return;
        toastEl.hidden = true;
        clearAnimationInlineProps(toastEl, ['opacity', 'transform']);
      });
    }, 2600);
  }

  function captureRowPositions() {
    const map = new Map();
    if (!groupsContainer) return map;
    groupsContainer.querySelectorAll('.entry-row').forEach((row) => {
      const key = row.querySelector('[data-term-toggle]')?.getAttribute('data-term-toggle');
      if (key) map.set(key, row.getBoundingClientRect().top);
    });
    return map;
  }

  function playRowFlip(previous) {
    if (isReducedMotion() || !previous || previous.size === 0) return;
    const viewport = window.innerHeight;
    groupsContainer.querySelectorAll('.entry-row').forEach((row) => {
      const key = row.querySelector('[data-term-toggle]')?.getAttribute('data-term-toggle');
      const top = row.getBoundingClientRect().top;
      if (top > viewport + 200 || top < -200) return;
      const before = previous.get(key);
      const keyframes = before === undefined
        ? [{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }]
        : Math.abs(before - top) < 1
          ? null
          : [{ transform: `translateY(${before - top}px)` }, { transform: 'none' }];
      if (!keyframes) return;
      row.animate(keyframes, { duration: 300, easing: 'cubic-bezier(0.32, 0.72, 0, 1)' });
    });
  }

  function dialogOriginDelta(dialogEl, originEl) {
    if (!originEl || !originEl.isConnected) return null;
    const from = originEl.getBoundingClientRect();
    const to = dialogEl.getBoundingClientRect();
    if (!to.width || !to.height) return null;
    return {
      dx: from.left + from.width / 2 - (to.left + to.width / 2),
      dy: from.top + from.height / 2 - (to.top + to.height / 2),
      scale: Math.max(0.12, Math.min(0.4, from.width / to.width))
    };
  }

  function animateDialogOpen(dialogEl, originEl) {
    if (!dialogEl) return;
    dialogEl.classList.remove('is-closing');
    delete dialogEl.dataset.closing;
    if (isReducedMotion()) {
      clearAnimationInlineProps(dialogEl, ['opacity', 'transform']);
      return;
    }
    const delta = dialogOriginDelta(dialogEl, originEl);
    if (delta) {
      dialogEl.animate(
        [
          { opacity: 0, transform: `translate(${delta.dx}px, ${delta.dy}px) scale(${delta.scale})` },
          { opacity: 1, transform: 'none' }
        ],
        { duration: 420, easing: 'cubic-bezier(0.32, 0.72, 0, 1)' }
      );
      return;
    }
    runElementAnimation(
      dialogEl,
      { opacity: [0, 1], scale: [0.96, 1], y: [8, 0] },
      {
        spring: true,
        bounce: 0.15,
        duration: 0.28,
        clearProps: ['opacity', 'transform']
      }
    );
  }

  function animateDialogClose(dialogEl, fallbackFocusFn) {
    if (!dialogEl) return;
    const isOpen = Boolean(dialogEl.open || dialogEl.hasAttribute('open'));
    if (!isOpen || dialogEl.dataset.closing === '1') return;

    const finishClose = () => {
      dialogEl.classList.remove('is-closing');
      delete dialogEl.dataset.closing;
      clearAnimationInlineProps(dialogEl, ['opacity', 'transform']);
      if (typeof dialogEl.close === 'function' && dialogEl.open) {
        dialogEl.close();
      } else {
        dialogEl.removeAttribute('open');
        if (typeof fallbackFocusFn === 'function') fallbackFocusFn();
      }
    };

    if (isReducedMotion()) {
      finishClose();
      return;
    }

    dialogEl.dataset.closing = '1';
    dialogEl.classList.add('is-closing');
    const closeOrigin = dialogEl === addWordDialog && state.addWordLastTriggerSelector
      ? document.querySelector(state.addWordLastTriggerSelector)
      : null;
    const closeDelta = dialogOriginDelta(dialogEl, closeOrigin);
    if (closeDelta) {
      dialogEl.animate(
        [
          { opacity: 1, transform: 'none' },
          { opacity: 0, transform: `translate(${closeDelta.dx}px, ${closeDelta.dy}px) scale(${closeDelta.scale})` }
        ],
        { duration: 260, easing: 'cubic-bezier(0.32, 0.72, 0, 1)', fill: 'forwards' }
      ).finished.then(finishClose);
      return;
    }
    const ctrl = runElementAnimation(
      dialogEl,
      { opacity: [1, 0], scale: [1, 0.97], y: [0, 6] },
      { duration: 0.15, ease: MOTION_EASE_OUT }
    );
    ctrl.finished.then(finishClose);
  }

  function resetSuggestValidation() {
    setFieldError(suggestText, suggestTextError, '');
  }

  function validateSuggestInput() {
    const ui = getActiveDict().ui;
    const val = suggestText.value.trim();
    if (val.length < 2) {
      setFieldError(suggestText, suggestTextError, val.length === 0 ? ui.errEmpty : ui.errTooShort);
      suggestText.focus();
      return false;
    }
    setFieldError(suggestText, suggestTextError, '');
    return true;
  }

  function openSuggestModal(term) {
    const item = findItemByTerm(term);
    if (!item) return;
    const ui = getActiveDict().ui;

    state.activeModalTerm = term;
    state.lastTriggerSelector = `[data-suggest-trigger="${CSS.escape(term)}"]`;

    suggestDialogSub.textContent = ui.modalSub(item.term, item.suggest);
    suggestText.value = '';
    resetSuggestValidation();

    if (typeof suggestDialog.showModal === 'function') {
      suggestDialog.showModal();
    } else {
      suggestDialog.setAttribute('open', '');
    }
    animateDialogOpen(suggestDialog);
    requestAnimationFrame(() => suggestText.focus());
  }

  function closeSuggestModal() {
    animateDialogClose(suggestDialog, restoreModalFocus);
  }

  async function copyTextToClipboard(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {
        // 降级至 textarea 复制
      }
    }
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      ta.style.pointerEvents = 'none';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch (_) {
      return false;
    }
  }

  function dispatchIssueSubmission(payload, labels, openedToast, copiedToast) {
    const repo = getConfiguredRepo();
    if (repo) {
      const url = buildGithubIssueUrl(repo, payload.title, payload.body, labels);
      window.open(url, '_blank', 'noopener,noreferrer');
      showToast(openedToast);
      return;
    }
    copyTextToClipboard(payload.markdown).then(() => {
      showToast(copiedToast);
    });
  }

  function submitSuggestModal(openIssue) {
    if (!validateSuggestInput()) return;
    const term = state.activeModalTerm;
    if (!term) return;

    const ui = getActiveDict().ui;
    const item = findItemByTerm(term);
    const communityMap = getActiveCommunityMap();

    const entryRecord = {
      mode: 'freeform',
      text: suggestText.value.trim(),
      note: ''
    };

    const existing = communityMap[term] || [];
    communityMap[term] = [...existing, entryRecord];
    getActiveOpenTerms()[term] = true;
    savePersistedCommunity();

    closeSuggestModal();
    renderDictionary({ highlightCommunityTerm: term });

    if (openIssue) {
      const payload = buildSuggestIssuePayload(state.lang, ui, term, item, entryRecord);
      dispatchIssueSubmission(
        payload,
        'suggestion',
        ui.toastAddedIssueOpened(term),
        ui.toastAddedIssueCopied(term)
      );
    } else {
      showToast(ui.toastAdded(term));
    }
  }

  function inferLetterForTerm(term) {
    const dict = getActiveDict();
    const letters = dict.letters;
    const trimmed = (term || '').trim();
    if (!trimmed) return letters[0];

    const first = trimmed.charAt(0).toUpperCase();
    if (/^[A-Z]$/.test(first) && letters.includes(first)) {
      return first;
    }

    if (state.lang === 'zh' && typeof Intl !== 'undefined' && typeof Intl.Collator === 'function') {
      const zhBounds = [
        ['A', '阿'], ['B', '八'], ['C', '嚓'], ['D', '哒'], ['E', '鹅'],
        ['F', '发'], ['G', '噶'], ['H', '哈'], ['J', '击'], ['K', '喀'],
        ['L', '垃'], ['M', '妈'], ['N', '拿'], ['O', '哦'], ['P', '啪'],
        ['Q', '期'], ['R', '然'], ['S', '撒'], ['T', '塌'], ['W', '挖'],
        ['X', '昔'], ['Y', '压'], ['Z', '匝']
      ];
      const collator = new Intl.Collator('zh-Hans-CN');
      let matched = letters[0];
      for (const [letter, anchor] of zhBounds) {
        if (!letters.includes(letter)) continue;
        if (collator.compare(trimmed, anchor) >= 0) {
          matched = letter;
        }
      }
      return matched;
    }

    return letters[0];
  }

  function setFieldError(inputEl, errorEl, message) {
    const errorId = errorEl && errorEl.id;
    if (errorId) {
      const ids = (inputEl.getAttribute('aria-describedby') || '')
        .split(/\s+/)
        .filter((id) => id && id !== errorId);
      if (message) ids.push(errorId);
      if (ids.length > 0) inputEl.setAttribute('aria-describedby', ids.join(' '));
      else inputEl.removeAttribute('aria-describedby');
    }

    if (message) {
      inputEl.classList.add('is-invalid');
      inputEl.setAttribute('aria-invalid', 'true');
      errorEl.textContent = message;
      errorEl.hidden = false;
      return false;
    }
    inputEl.classList.remove('is-invalid');
    inputEl.setAttribute('aria-invalid', 'false');
    errorEl.textContent = '';
    errorEl.hidden = true;
    return true;
  }

  function resetAddWordValidation() {
    setFieldError(addWordTerm, addWordTermError, '');
    setFieldError(addWordWhy, addWordWhyError, '');
  }

  function validateAddWordTerm() {
    const ui = getActiveDict().ui;
    const val = addWordTerm.value.trim();
    if (!val) {
      return setFieldError(addWordTerm, addWordTermError, ui.errWordTermEmpty);
    }
    if (findItemByTerm(val)) {
      return setFieldError(addWordTerm, addWordTermError, ui.errWordTermDuplicate(val));
    }
    return setFieldError(addWordTerm, addWordTermError, '');
  }

  function validateAddWordWhy() {
    const ui = getActiveDict().ui;
    const val = addWordWhy.value.trim();
    if (val.length < 2) {
      return setFieldError(addWordWhy, addWordWhyError, ui.errWordWhyEmpty);
    }
    return setFieldError(addWordWhy, addWordWhyError, '');
  }

  function validateAddWordInputs() {
    const okTerm = validateAddWordTerm();
    const okWhy = validateAddWordWhy();
    if (!okTerm) {
      addWordTerm.focus();
      return false;
    }
    if (!okWhy) {
      addWordWhy.focus();
      return false;
    }
    return true;
  }

  function openAddWordModal(initialTerm, triggerSelector) {
    populateAddWordSelects();

    state.addWordLastTriggerSelector = triggerSelector || '#header-add-btn';

    const prefill = (initialTerm || '').trim();
    addWordTerm.value = prefill;
    addWordLevel.value = '1';
    addWordWhy.value = '';
    addWordAlias.value = '';
    resetAddWordValidation();

    if (typeof addWordDialog.showModal === 'function') {
      addWordDialog.showModal();
    } else {
      addWordDialog.setAttribute('open', '');
    }
    animateDialogOpen(addWordDialog, document.querySelector(state.addWordLastTriggerSelector));

    requestAnimationFrame(() => {
      if (prefill) {
        addWordWhy.focus();
      } else {
        addWordTerm.focus();
      }
    });
  }

  function restoreAddWordModalFocus() {
    if (!state.addWordLastTriggerSelector) return;
    const trigger = document.querySelector(state.addWordLastTriggerSelector);
    if (trigger) {
      trigger.focus({ preventScroll: true });
    } else {
      searchInput.focus({ preventScroll: true });
    }
    state.addWordLastTriggerSelector = null;
  }

  function closeAddWordModal() {
    animateDialogClose(addWordDialog, restoreAddWordModalFocus);
  }

  function submitAddWordModal(openIssue) {
    if (!validateAddWordInputs()) return;

    const dict = getActiveDict();
    const ui = dict.ui;
    const term = addWordTerm.value.trim();
    const letter = inferLetterForTerm(term);
    const levelNum = Number(addWordLevel.value);
    const level = levelNum === 1 || levelNum === 2 || levelNum === 3 ? levelNum : 1;
    const newEntry = {
      term,
      letter,
      level,
      why: addWordWhy.value.trim(),
      suggest: '',
      ok: '',
      bad: '',
      alias: addWordAlias.value.trim(),
      isCustom: true
    };

    state.customTermsByLang[state.lang] = [...getActiveCustomTerms(), newEntry];
    getActiveOpenTerms()[term] = true;
    savePersistedCustomTerms();

    // 若当前处于筛选/无结果状态，重置筛选以便立即看到新增词条
    if (state.query.trim() || state.levelFilter !== 'all') {
      state.query = '';
      state.levelFilter = 'all';
      searchInput.value = '';
    }

    state.addWordLastTriggerSelector = null;
    closeAddWordModal();
    renderDictionary({ focusTerm: term, highlightTerm: term });

    const targetBtn = groupsContainer.querySelector(`[data-term-toggle="${CSS.escape(term)}"]`);
    if (targetBtn) {
      targetBtn.scrollIntoView({
        behavior: reducedMotionMedia && reducedMotionMedia.matches ? 'auto' : 'smooth',
        block: 'center'
      });
    }

    if (openIssue) {
      const payload = buildAddWordIssuePayload(state.lang, ui, newEntry);
      dispatchIssueSubmission(
        payload,
        'new-term',
        ui.toastWordAddedIssueOpened(term),
        ui.toastWordAddedIssueCopied(term)
      );
    } else {
      showToast(ui.toastWordAddedLocal(term));
    }
  }

  function restoreModalFocus() {
    if (!state.lastTriggerSelector) return;
    const trigger = document.querySelector(state.lastTriggerSelector);
    if (trigger) {
      trigger.focus({ preventScroll: true });
    } else {
      searchInput.focus({ preventScroll: true });
    }
    state.lastTriggerSelector = null;
  }

  function resetSearchOnly(focusInput) {
    state.query = '';
    searchInput.value = '';
    renderDictionary();
    if (focusInput) searchInput.focus();
  }

  function resetFilters(focusInput) {
    state.query = '';
    state.levelFilter = 'all';
    searchInput.value = '';
    renderDictionary({ animateGroups: true });
    if (focusInput) searchInput.focus();
  }

  function switchLanguage(nextLang) {
    if (!DICTIONARIES[nextLang] || nextLang === state.lang) return;
    state.lang = nextLang;
    state.query = '';
    state.levelFilter = 'all';
    state.currentLetter = null;
    searchInput.value = '';
    writeStorage(LANG_STORAGE_KEY, nextLang);
    applyStaticLocaleCopy();
    renderDictionary({ animateGroups: true });
    fetchHotCounts(nextLang);
    showToast(getActiveDict().ui.toastLangSwitched);
  }

  // Event bindings
  for (const btn of langButtons) {
    btn.addEventListener('click', () => switchLanguage(btn.dataset.lang));
  }

  function syncThumbsSide() {
    const side = state.thumbsSide === 'left' ? 'left' : 'right';
    rootEl.dataset.thumbsSide = side;
    if (thumbsNav) thumbsNav.dataset.side = side;
    if (thumbsSideToggle) {
      const ui = getActiveDict().ui;
      const label = side === 'left' ? ui.thumbsMoveRight : ui.thumbsMoveLeft;
      thumbsSideToggle.setAttribute('aria-label', label);
      thumbsSideToggle.title = label;
    }
  }

  if (thumbsSideToggle) {
    thumbsSideToggle.addEventListener('click', () => {
      state.thumbsSide = state.thumbsSide === 'left' ? 'right' : 'left';
      writeStorage(THUMBS_SIDE_STORAGE_KEY, state.thumbsSide);
      resetDockMagnification();
      invalidateDockMetrics();
      syncThumbsSide();
    });
  }

  thumbsTrack.addEventListener('pointermove', (e) => {
    if (e.pointerType === 'touch') return;
    scheduleDockMagnification(e.clientY);
  });

  thumbsTrack.addEventListener('pointerleave', () => {
    resetDockMagnification();
  });

  thumbsNav.addEventListener('scroll', () => {
    invalidateDockMetrics();
    if (dockState.pointerY !== null) {
      scheduleDockMagnification(dockState.pointerY);
    }
  }, { passive: true });

  themeToggle.addEventListener('click', () => {
    const nextDark = !state.dark;
    const systemDark = Boolean(colorSchemeMedia && colorSchemeMedia.matches);
    state.dark = nextDark;
    if (nextDark === systemDark) {
      state.userThemeOverride = false;
      removeStorage(THEME_STORAGE_KEY);
    } else {
      state.userThemeOverride = true;
      writeStorage(THEME_STORAGE_KEY, nextDark ? 'dark' : 'light');
    }
    renderThemeToggle(true);
  });

  window.addEventListener('storage', (e) => {
    invalidateStorageCache(e.key);
    if (e.key !== THEME_STORAGE_KEY) return;
    if (e.newValue === 'dark' || e.newValue === 'light') {
      state.userThemeOverride = true;
      state.dark = e.newValue === 'dark';
    } else {
      state.userThemeOverride = false;
      state.dark = Boolean(colorSchemeMedia && colorSchemeMedia.matches);
    }
    renderThemeToggle();
  });

  if (colorSchemeMedia && typeof colorSchemeMedia.addEventListener === 'function') {
    colorSchemeMedia.addEventListener('change', (e) => {
      if (state.userThemeOverride) return;
      state.dark = e.matches;
      renderThemeToggle();
    });
  }

  if (reducedMotionMedia && typeof reducedMotionMedia.addEventListener === 'function') {
    reducedMotionMedia.addEventListener('change', () => {
      moveLevelRing(false);
      syncHeaderScrollProgressDriver();
    });
  }

  function isSearchSlotVisible() {
    if (!searchBarSlot) return true;
    const rect = searchBarSlot.getBoundingClientRect();
    const headerBar = document.querySelector('.site-header-bar');
    const headerBottom = headerBar ? headerBar.getBoundingClientRect().bottom : 64;
    return rect.top >= headerBottom;
  }

  function dockSearchBar() {
    if (!searchBar || !searchBarSlot || searchBar.classList.contains('is-docked')) return;
    searchBarSlot.style.height = `${searchBar.offsetHeight}px`;
    searchBar.classList.add('is-docked');
    headerSearchBtn?.setAttribute('aria-expanded', 'true');
    if (!isReducedMotion()) {
      runElementAnimation(searchBar, { opacity: [0.6, 1], y: [-8, 0] }, {
        duration: 0.18,
        ease: MOTION_EASE_OUT,
        clearProps: ['opacity', 'transform']
      });
    }
  }

  function undockSearchBar() {
    if (!searchBar || !searchBarSlot || !searchBar.classList.contains('is-docked')) return;
    searchBar.classList.remove('is-docked');
    searchBarSlot.style.height = '';
    headerSearchBtn?.setAttribute('aria-expanded', 'false');
  }

  function syncDockedSearchBar() {
    if (!searchBar || !searchBar.classList.contains('is-docked')) return;
    if (isSearchSlotVisible()) {
      undockSearchBar();
    }
  }

  function focusSearchInPlace() {
    if (isSearchSlotVisible()) {
      undockSearchBar();
    } else {
      dockSearchBar();
    }
    searchInput.focus({ preventScroll: true });
    searchInput.select();
  }

  headerSearchBtn.addEventListener('click', () => {
    if (searchBar && searchBar.classList.contains('is-docked')) {
      undockSearchBar();
      searchInput.blur();
      return;
    }
    focusSearchInPlace();
  });

  headerAddBtn.addEventListener('click', () => {
    openAddWordModal('', '#header-add-btn');
  });

  emptyAddWordBtn.addEventListener('click', () => {
    openAddWordModal(state.query.trim(), '#empty-add-word');
  });

  let searchRenderFrame = 0;
  searchInput.addEventListener('input', () => {
    state.query = searchInput.value;
    if (searchRenderFrame) return;
    searchRenderFrame = requestAnimationFrame(() => {
      searchRenderFrame = 0;
      renderDictionary();
    });
  });

  searchInput.addEventListener('keydown', (e) => {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === 'Escape') {
      if (searchInput.value) {
        e.preventDefault();
        resetSearchOnly(true);
      } else {
        undockSearchBar();
        searchInput.blur();
      }
    }
  });

  groupsContainer.addEventListener('beforematch', (e) => {
    const panel = e.target && typeof e.target.closest === 'function' ? e.target.closest('.entry-panel') : null;
    if (!panel) return;
    const row = panel.closest('.entry-row');
    const trigger = row ? row.querySelector('.entry-trigger[data-term-toggle]') : null;
    const term = trigger ? trigger.getAttribute('data-term-toggle') : null;
    if (!term) return;
    getActiveOpenTerms()[term] = true;
    trigger.setAttribute('aria-expanded', 'true');
    panel.classList.remove('is-animating');
    clearAnimationInlineProps(panel, ['height', 'opacity', 'transform']);
    renderBulkToggle(getFilteredGroups());
  });

  searchClear.addEventListener('click', () => resetSearchOnly(true));
  searchStatusReset.addEventListener('click', () => resetFilters(true));
  emptyReset.addEventListener('click', () => resetFilters(true));

  levelAllBtn.addEventListener('click', () => {
    if (state.levelFilter === 'all') return;
    state.levelFilter = 'all';
    renderDictionary({ animateGroups: true });
  });

  if (sortHotBtn) {
    sortHotBtn.addEventListener('click', () => {
      state.sortByHot = !state.sortByHot;
      sortHotBtn.setAttribute('aria-pressed', state.sortByHot ? 'true' : 'false');
      renderDictionary({ animateGroups: true });
    });
  }

  toggleAllBtn.addEventListener('click', () => {
    const groups = getFilteredGroups();
    const visibleItems = groups.flatMap((g) => g.items);
    if (visibleItems.length === 0) return;
    const openTerms = getActiveOpenTerms();
    const allOpen = visibleItems.every((item) => !!openTerms[item.term]);
    const nextOpen = !allOpen;
    for (const item of visibleItems) {
      openTerms[item.term] = nextOpen;
    }

    const triggers = Array.from(groupsContainer.querySelectorAll('.entry-trigger[data-term-toggle]'));
    triggers.forEach((trigger, idx) => {
      const row = trigger.closest('.entry-row');
      const panel = row ? row.querySelector('.entry-panel') : null;
      if (!panel) return;
      const delaySec = Math.min(idx, 8) * 0.022;
      animateEntryPanelToggle(panel, trigger, nextOpen, delaySec);
    });
    renderBulkToggle(groups);
    updateHeaderScrollProgressFallback();
  });

  window.addEventListener('scroll', () => {
    if (state.scrollRaf) return;
    state.scrollRaf = requestAnimationFrame(() => {
      state.scrollRaf = null;
      syncDockedSearchBar();
      updateCurrentLetterFromScroll();
      updateHeaderScrollProgressFallback();
    });
  }, { passive: true });

  window.addEventListener('resize', () => {
    moveLevelRing(false);
    invalidateDockMetrics();
    if (state.scrollRaf) return;
    state.scrollRaf = requestAnimationFrame(() => {
      state.scrollRaf = null;
      syncDockedSearchBar();
      updateCurrentLetterFromScroll();
      updateHeaderScrollProgressFallback();
    });
  }, { passive: true });

  document.addEventListener('pointerdown', (e) => {
    if (!searchBar || !searchBar.classList.contains('is-docked')) return;
    if (searchInput.value.trim()) return;
    if (searchBar.contains(e.target) || headerSearchBtn.contains(e.target)) return;
    undockSearchBar();
  });

  document.addEventListener('keydown', (e) => {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
    if (suggestDialog.open || addWordDialog.open) return;
    const active = document.activeElement;
    const tag = active ? active.tagName : '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (active && active.isContentEditable)) return;
    e.preventDefault();
    focusSearchInPlace();
  });

  suggestText.addEventListener('blur', () => {
    if (suggestText.value.trim().length > 0 || suggestText.classList.contains('is-invalid')) {
      setFieldError(
        suggestText,
        suggestTextError,
        suggestText.value.trim().length < 2
          ? (suggestText.value.trim().length === 0 ? getActiveDict().ui.errEmpty : getActiveDict().ui.errTooShort)
          : ''
      );
    }
  });

  function installLightDismissFallback(dialogEl, closeFn) {
    if (!dialogEl || (typeof HTMLDialogElement !== 'undefined' && 'closedBy' in HTMLDialogElement.prototype)) {
      return;
    }
    const isOutside = (e) => {
      const r = dialogEl.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    let pressedOutside = false;
    dialogEl.addEventListener('pointerdown', (e) => {
      pressedOutside = isOutside(e);
    });
    dialogEl.addEventListener('pointerup', (e) => {
      if (pressedOutside && isOutside(e)) closeFn();
      pressedOutside = false;
    });
  }

  if (suggestForm) {
    suggestForm.addEventListener('submit', (e) => {
      e.preventDefault();
      submitSuggestModal(true);
    });
  } else {
    suggestSubmit.addEventListener('click', () => submitSuggestModal(true));
  }
  suggestClose.addEventListener('click', closeSuggestModal);
  suggestCancel.addEventListener('click', closeSuggestModal);
  suggestDialog.addEventListener('cancel', (e) => {
    e.preventDefault();
    closeSuggestModal();
  });
  suggestDialog.addEventListener('close', restoreModalFocus);
  installLightDismissFallback(suggestDialog, closeSuggestModal);

  addWordTerm.addEventListener('input', () => {
    if (addWordTerm.classList.contains('is-invalid')) {
      validateAddWordTerm();
    }
  });
  addWordTerm.addEventListener('blur', () => {
    if (addWordTerm.value.trim().length > 0 || addWordTerm.classList.contains('is-invalid')) {
      validateAddWordTerm();
    }
  });
  addWordWhy.addEventListener('blur', () => {
    if (addWordWhy.value.trim().length > 0 || addWordWhy.classList.contains('is-invalid')) {
      validateAddWordWhy();
    }
  });

  if (addWordForm) {
    addWordForm.addEventListener('submit', (e) => {
      e.preventDefault();
      submitAddWordModal(true);
    });
  } else {
    addWordSubmit.addEventListener('click', () => submitAddWordModal(true));
  }
  addWordClose.addEventListener('click', closeAddWordModal);
  addWordCancel.addEventListener('click', closeAddWordModal);
  addWordDialog.addEventListener('cancel', (e) => {
    e.preventDefault();
    closeAddWordModal();
  });
  addWordDialog.addEventListener('close', restoreAddWordModalFocus);
  installLightDismissFallback(addWordDialog, closeAddWordModal);

  if (hookInstallToggle && hookInstallPanel) {
    hookInstallToggle.addEventListener('click', () => {
      const nextOpen = hookInstallToggle.getAttribute('aria-expanded') !== 'true';
      hookInstallToggle.setAttribute('aria-expanded', String(nextOpen));
      if (nextOpen) {
        hookInstallPanel.hidden = false;
        hookInstallPanel.classList.remove('is-open');
        void hookInstallPanel.offsetHeight;
        hookInstallPanel.classList.add('is-open');
      } else {
        hookInstallPanel.classList.remove('is-open');
        const transitions = typeof hookInstallPanel.getAnimations === 'function'
          ? hookInstallPanel.getAnimations().filter((a) => typeof CSSTransition !== 'undefined' && a instanceof CSSTransition)
          : [];
        if (transitions.length === 0) {
          hookInstallPanel.hidden = true;
        } else {
          Promise.allSettled(transitions.map((t) => t.finished)).then(() => {
            if (!hookInstallPanel.classList.contains('is-open')) {
              hookInstallPanel.hidden = true;
            }
          });
        }
      }
    });
  }

  const copyTimers = new WeakMap();
  let lastCopyAnnouncement = '';

  function reportCopyOutcome(button, ok) {
    const tip = button.nextElementSibling;
    clearTimeout(copyTimers.get(button));
    button.removeAttribute('data-copied');
    button.removeAttribute('data-failed');
    const ui = getActiveDict().ui;
    let message = ok ? (ui.copySuccess || 'Copied') : (ui.copyFailed || 'Copy failed');
    if (message === lastCopyAnnouncement) message += '\u00A0';
    lastCopyAnnouncement = message;
    if (tip) tip.textContent = '';
    void button.offsetWidth;
    button.setAttribute(ok ? 'data-copied' : 'data-failed', '');
    if (tip) {
      requestAnimationFrame(() => {
        tip.textContent = message;
      });
    }
    copyTimers.set(button, setTimeout(() => {
      button.removeAttribute('data-copied');
      button.removeAttribute('data-failed');
      if (tip) tip.textContent = '';
    }, 2000));
  }

  async function runCopyAction(button, target) {
    if (!button || !target) return;
    const text = target.matches('input, textarea')
      ? target.value
      : (target.innerText || target.textContent || '').trim();
    if (!text) return;
    const ok = await copyTextToClipboard(text);
    reportCopyOutcome(button, ok);
  }

  const appRoot = document.getElementById('app-shell') || document;
  if ('CommandEvent' in window) {
    appRoot.addEventListener('command', (event) => {
      if (event.command && event.command.startsWith('--copy')) {
        runCopyAction(event.source, event.target);
      }
    }, true);
  } else {
    appRoot.addEventListener('click', (event) => {
      const button = event.target && typeof event.target.closest === 'function'
        ? event.target.closest('button[command^="--copy"]')
        : null;
      if (!button) return;
      const targetId = button.getAttribute('commandfor');
      const target = targetId ? document.getElementById(targetId) : null;
      if (target) runCopyAction(button, target);
    });
  }

  if (paramQuery) {
    searchInput.value = paramQuery;
  }
  applyStaticLocaleCopy();
  renderDictionary();
  fetchHotCounts(state.lang);
  syncHeaderScrollProgressDriver();
  requestAnimationFrame(() => {
    langSwitch.classList.add('is-ready');
  });
}
