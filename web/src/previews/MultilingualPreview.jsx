import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import './multilingualPreview.css';

const languages = [
  { code: 'zh', native: '中文', name: '中文', aliases: 'zh-cn chinese mandarin zhongwen hanyu 汉语', title: '图灵高阶硅碳词典', search: '搜索词语、拼音、别名或说明' },
  { code: 'en', native: 'English', name: '英语', aliases: 'english yingyu 英文', title: 'Turing Silicon–Carbon Dictionary', search: 'Search terms, aliases or descriptions' },
  { code: 'ja', native: '日本語', name: '日语', aliases: 'japanese nihongo riyu 日文', title: 'チューリング シリコン・カーボン辞典', search: '用語・別名・説明を検索' },
  { code: 'ko', native: '한국어', name: '韩语', aliases: 'korean hangul hangugeo hanyu 韩文', title: '튜링 실리콘–카본 사전', search: '용어, 별칭 또는 설명 검색' },
  { code: 'fr', native: 'Français', name: '法语', aliases: 'french francais fayu 法文', title: 'Dictionnaire silicium–carbone de Turing', search: 'Rechercher un terme, un alias ou une description' },
  { code: 'de', native: 'Deutsch', name: '德语', aliases: 'german deyu 德文', title: 'Turings Silizium–Kohlenstoff-Wörterbuch', search: 'Begriffe, Aliasse oder Beschreibungen suchen' },
  { code: 'es', native: 'Español', name: '西班牙语', aliases: 'spanish espanol xibanyayu 西语', title: 'Diccionario silicio–carbono de Turing', search: 'Buscar términos, alias o descripciones' },
  { code: 'pt', native: 'Português', name: '葡萄牙语', aliases: 'portuguese portugues putaoyayu 葡语', title: 'Dicionário silício–carbono de Turing', search: 'Pesquisar termos, nomes alternativos ou descrições' },
  { code: 'ru', native: 'Русский', name: '俄语', aliases: 'russian russkiy eyu 俄文', title: 'Кремний–углеродный словарь Тьюринга', search: 'Поиск терминов, синонимов и описаний' },
  { code: 'ar', native: 'العربية', name: '阿拉伯语', aliases: 'arabic al arabiyah alaboyu', title: 'قاموس تورينغ للسيليكون والكربون', search: 'ابحث عن المصطلحات أو الأسماء البديلة أو الأوصاف', direction: 'rtl' },
];

function normalizeSearch(value) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function Chevron() {
  return <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m5 8 5 5 5-5" /></svg>;
}

function stopAnimations(animations) {
  for (const { animation, element, properties } of animations.current) {
    const computed = getComputedStyle(element);
    const values = Object.fromEntries(properties.map(property => [property, computed[property]]));
    animation.cancel();
    Object.assign(element.style, values);
  }
  animations.current = [];
}

function animateElement(animations, element, keyframes, options) {
  const animation = element.animate(keyframes, options);
  animations.current.push({ animation, element, properties: Object.keys(keyframes[0]) });
  return animation;
}

function LanguagePicker({ selected, onSelect }) {
  const [open, setOpen] = useState(false);
  const [present, setPresent] = useState(false);
  const [query, setQuery] = useState('');
  const [panelPosition, setPanelPosition] = useState({});
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 640px)').matches);
  const triggerRef = useRef(null);
  const labelRef = useRef(null);
  const searchRef = useRef(null);
  const closeRef = useRef(null);
  const panelRef = useRef(null);
  const surfaceRef = useRef(null);
  const contentRef = useRef(null);
  const backdropRef = useRef(null);
  const resultsRef = useRef(null);
  const exitsRef = useRef(null);
  const panelAnimations = useRef([]);
  const resultAnimations = useRef([]);
  const previousResults = useRef(null);
  const previousSurface = useRef(null);
  const previousSelection = useRef(selected.code);
  const keyboardInput = useRef(false);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const panelId = useId();
  const titleId = useId();
  const normalizedQuery = normalizeSearch(query);
  const exactCode = languages.find(language => language.code === normalizedQuery);
  const filtered = exactCode ? [exactCode] : languages.filter(language => normalizeSearch(`${language.native} ${language.name} ${language.code} ${language.aliases}`).includes(normalizedQuery));

  useLayoutEffect(() => {
    if (previousSelection.current === selected.code) return;
    previousSelection.current = selected.code;
    const animation = labelRef.current.animate?.([{ opacity: .45 }, { opacity: 1 }], { duration: 150, easing: 'ease-out' });
    return () => animation?.cancel();
  }, [selected.code]);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 640px)');
    const motionMedia = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setMobile(media.matches);
    const updateMotion = () => setReducedMotion(motionMedia.matches);
    media.addEventListener('change', update);
    motionMedia.addEventListener('change', updateMotion);
    return () => {
      media.removeEventListener('change', update);
      motionMedia.removeEventListener('change', updateMotion);
    };
  }, []);

  function measurePosition() {
    const bounds = triggerRef.current.getBoundingClientRect();
    const below = window.innerHeight - bounds.bottom - 26;
    const above = bounds.top - 26;
    const placeAbove = below < 300 && above > below;
    const maxHeight = Math.min(580, Math.max(180, placeAbove ? above : below));
    return {
      left: Math.max(16, Math.min(bounds.left, window.innerWidth - 376)),
      top: placeAbove ? Math.max(16, bounds.top - maxHeight - 10) : bounds.bottom + 10,
      maxHeight,
    };
  }

  useLayoutEffect(() => {
    if (!present || mobile) return;
    const updatePosition = () => setPanelPosition(measurePosition());
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [present, mobile]);

  useLayoutEffect(() => {
    if (!present) return;
    if (!surfaceRef.current.animate) {
      if (!open) { setPresent(false); setQuery(''); }
      return;
    }
    const surface = surfaceRef.current;
    const content = contentRef.current;
    const backdrop = backdropRef.current;
    const bounds = panelRef.current.getBoundingClientRect();
    const origin = triggerRef.current.getBoundingClientRect();
    const scaleX = origin.width / bounds.width;
    const scaleY = origin.height / bounds.height;
    const collapsed = `translate(${origin.left - bounds.left}px, ${origin.top - bounds.top}px) scale(${scaleX}, ${scaleY})`;
    const smallRadius = `${6 / scaleX}px / ${6 / scaleY}px`;
    const radius = getComputedStyle(panelRef.current).borderRadius;
    const duration = reducedMotion ? 150 : keyboardInput.current ? 180 : mobile ? 400 : 260;
    const options = { duration, easing: 'cubic-bezier(.32, .72, 0, 1)', fill: 'both' };
    if (reducedMotion) surface.style.transform = 'none';
    const shell = animateElement(panelAnimations, surface, [
      { transform: reducedMotion ? 'none' : surface.style.transform || collapsed, borderRadius: reducedMotion ? radius : surface.style.borderRadius || smallRadius, opacity: reducedMotion ? surface.style.opacity || (open ? 0 : 1) : 1 },
      { transform: reducedMotion || open ? 'none' : collapsed, borderRadius: reducedMotion || open ? radius : smallRadius, opacity: reducedMotion && !open ? 0 : 1 },
    ], options);
    animateElement(panelAnimations, content, [
      { opacity: content.style.opacity || (open ? 0 : 1) },
      { opacity: open ? 1 : 0 },
    ], { ...options, duration: reducedMotion ? 150 : open ? duration * .55 : duration * .3, delay: open && !reducedMotion ? duration * .45 : 0 });
    animateElement(panelAnimations, backdrop, [
      { opacity: backdrop.style.opacity || (open ? 0 : 1) },
      { opacity: open ? 1 : 0 },
    ], options);
    let active = true;
    shell.finished.then(() => {
      if (active && !open) { setPresent(false); setQuery(''); }
    }).catch(() => {});
    return () => {
      active = false;
      stopAnimations(panelAnimations);
    };
  }, [open, present, mobile, reducedMotion]);

  function changeQuery(value) {
    if (value === query) return;
    previousSurface.current = surfaceRef.current.getBoundingClientRect();
    previousResults.current = new Map([...resultsRef.current.querySelectorAll('[data-language]')].map(element => [element.dataset.language, { bounds: element.getBoundingClientRect(), clone: element.cloneNode(true) }]));
    for (const { animation } of resultAnimations.current) animation.cancel();
    resultAnimations.current = [];
    exitsRef.current.replaceChildren();
    setQuery(value);
  }

  useLayoutEffect(() => {
    const previous = previousResults.current;
    previousResults.current = null;
    if (!present || !previous || !resultsRef.current.animate) return;
    const results = resultsRef.current;
    const bounds = results.getBoundingClientRect();
    const current = [...results.querySelectorAll('[data-language]')];
    const options = { duration: reducedMotion ? 150 : 200, easing: 'ease-in-out' };
    const oldSurface = previousSurface.current;
    const nextSurface = panelRef.current.getBoundingClientRect();
    const panelMoving = panelAnimations.current.some(({ animation }) => animation.playState === 'running');
    if (!reducedMotion && !panelMoving && oldSurface && Math.abs(oldSurface.height - nextSurface.height) > 1) {
      animateElement(resultAnimations, surfaceRef.current, [
        { transform: `scaleY(${oldSurface.height / nextSurface.height})` },
        { transform: 'none' },
      ], options);
    }
    for (const element of current) {
      const old = previous.get(element.dataset.language);
      const next = element.getBoundingClientRect();
      animateElement(resultAnimations, element, [
        { transform: !reducedMotion && old ? `translate(${old.bounds.left - next.left}px, ${old.bounds.top - next.top}px)` : 'none', opacity: old ? 1 : 0 },
        { transform: 'none', opacity: 1 },
      ], options);
      previous.delete(element.dataset.language);
    }
    exitsRef.current.style.top = `${results.scrollTop}px`;
    exitsRef.current.style.height = `${results.clientHeight}px`;
    for (const { clone, bounds: old } of previous.values()) {
      clone.removeAttribute('data-language');
      clone.disabled = true;
      clone.tabIndex = -1;
      Object.assign(clone.style, { position: 'absolute', top: `${old.top - bounds.top}px`, left: `${old.left - bounds.left}px`, width: `${old.width}px`, height: `${old.height}px`, margin: 0 });
      exitsRef.current.append(clone);
      const animation = animateElement(resultAnimations, clone, [{ opacity: 1 }, { opacity: 0 }], { duration: 150 });
      animation.finished.then(() => clone.remove()).catch(() => {});
    }
  }, [query, present, reducedMotion]);

  useEffect(() => {
    if (present) return;
    for (const { animation } of resultAnimations.current) animation.cancel();
    resultAnimations.current = [];
    previousResults.current = null;
    previousSurface.current = null;
  }, [present]);

  useEffect(() => () => {
    for (const { animation } of resultAnimations.current) animation.cancel();
  }, []);

  useEffect(() => {
    if (!open) return;
    (mobile ? closeRef.current : searchRef.current)?.focus({ preventScroll: true });
  }, [open, mobile]);

  useEffect(() => {
    if (!present || !mobile) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previousOverflow; };
  }, [present, mobile]);

  function show(event) {
    keyboardInput.current = event.detail === 0;
    if (open) { dismiss(event); return; }
    if (!mobile) setPanelPosition(measurePosition());
    setPresent(true);
    setOpen(true);
  }

  function dismiss(event) {
    if (event) keyboardInput.current = event.type === 'keydown' || event.detail === 0;
    setOpen(false);
    triggerRef.current?.focus({ preventScroll: true });
  }

  function choose(language, event) {
    onSelect(language);
    dismiss(event);
  }

  function handleKeys(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      dismiss(event);
      return;
    }
    const controls = [...panelRef.current.querySelectorAll('button:not([disabled]), input')];
    if (event.key === 'Tab') {
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      const choices = [...panelRef.current.querySelectorAll('[data-language]')];
      if (!choices.length) return;
      event.preventDefault();
      const currentIndex = choices.indexOf(document.activeElement);
      const nextIndex = event.key === 'ArrowDown' ? (currentIndex + 1) % choices.length : (currentIndex <= 0 ? choices.length : currentIndex) - 1;
      choices[nextIndex].focus();
    }
    if (event.key === 'Enter' && event.target === searchRef.current && filtered.length === 1) {
      event.preventDefault();
      choose(filtered[0], event);
    }
  }

  return (
    <div className="multi-picker">
      <span className="multi-picker-label">词典语言</span>
      <button ref={triggerRef} className="multi-picker-trigger" type="button" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? panelId : undefined} aria-label={`选择词典语言，当前为${selected.name}`} onClick={show}>
        <span ref={labelRef} lang={selected.code} dir="auto">{selected.native}</span><Chevron />
      </button>
      {present && <>
        <div ref={backdropRef} className="multi-picker-backdrop" data-closing={!open} onClick={dismiss} aria-hidden="true" />
        <div ref={panelRef} className="multi-picker-panel" data-closing={!open} inert={!open ? '' : undefined} aria-hidden={!open || undefined} style={mobile ? undefined : panelPosition} id={panelId} role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={handleKeys}>
          <div ref={surfaceRef} className="multi-picker-surface" aria-hidden="true" />
          <div ref={contentRef} className="multi-picker-content">
          <div className="multi-picker-heading">
            <div><h3 id={titleId}>选择词典语言</h3><p>10 种示例语言</p></div>
            <button ref={closeRef} className="multi-picker-close" type="button" onClick={dismiss} aria-label="关闭语言选择">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>
          </div>
          <div className="multi-picker-search">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
            <input ref={searchRef} value={query} onChange={event => changeQuery(event.target.value)} placeholder="搜索语言名称或代码" aria-label="搜索语言名称或代码" autoComplete="off" spellCheck="false" />
            {query && <button type="button" onClick={() => { changeQuery(''); searchRef.current?.focus(); }} aria-label="清空语言搜索">清空</button>}
          </div>
          <div ref={resultsRef} className="multi-picker-results" role="group" aria-label="词典语言列表">
            {filtered.map(language => <button className="multi-language-option" data-language={language.code} key={language.code} type="button" aria-pressed={selected.code === language.code} onClick={event => choose(language, event)}>
              <span className="multi-language-check" aria-hidden="true">{selected.code === language.code && <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2"><path d="m4 10 4 4 8-8" /></svg>}</span>
              <span className="multi-language-native" lang={language.code} dir="auto">{language.native}</span>
              {language.name !== language.native && <span className="multi-language-name">{language.name}</span>}
              <span className="multi-language-code">{language.code.toUpperCase()}</span>
            </button>)}
            {!filtered.length && <div className="multi-picker-empty"><p>没有找到“{query}”</p><span>试试“日语”、Japanese 或 ja。</span><button type="button" onClick={() => { changeQuery(''); searchRef.current?.focus(); }}>显示全部语言</button></div>}
            <div ref={exitsRef} className="multi-picker-result-exits" aria-hidden="true" inert="" />
          </div>
          <p className="multi-picker-footer" role="status">{normalizedQuery ? `${filtered.length} 个匹配结果` : '支持本名、中文名称和语言代码搜索'}</p>
          </div>
        </div>
      </>}
    </div>
  );
}

export default function MultilingualPreview() {
  const [selected, setSelected] = useState(languages[0]);
  const [dark, setDark] = useState(false);

  return (
    <main className="language-study multi-language-study" data-theme={dark ? 'dark' : 'light'}>
      <div className="language-study-shell">
        <nav className="multi-study-nav" aria-label="多语言设计预览导航">
          <a href="?">返回词典</a>
          <div><a href="?preview=language">查看两种语言方案</a><button type="button" aria-pressed={dark} onClick={() => setDark(!dark)}>{dark ? '切换浅色' : '切换深色'}</button></div>
        </nav>
        <h1>十种语言，一个入口。</h1>
        <p className="multi-study-intro">页面只展示当前语言。完整列表在需要时展开，让语言数量增加，也不挤占阅读空间。</p>
        <section className="multi-study-stage" aria-label="词典语言选择器交互演示">
          <div className="multi-study-stage-top"><LanguagePicker selected={selected} onSelect={setSelected} /><span className="multi-study-status" role="status">当前：{selected.name}</span></div>
          <h2 lang={selected.code} dir={selected.direction || 'ltr'}>{selected.title}</h2>
          <div className="multi-study-search-example" lang={selected.code} dir={selected.direction || 'ltr'}>
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg><span>{selected.search}</span>
          </div>
          <p className="multi-study-example-note">词典标题与搜索提示为版式示例，十种语言不代表对应词表已上线。</p>
        </section>
        <div className="multi-study-explanation">
          <section><h2>在电脑上，随用随展开。</h2><p>列表紧跟语言按钮，按名称或代码快速查找。选中后收起，页面始终只留一个入口。</p></section>
          <section><h2>在手机上，留出选择空间。</h2><p>点击后从底部展开面板，搜索框固定在列表上方。语言多时在面板内滚动，背景页面保持原位。</p></section>
        </div>
        <p className="multi-study-note">试试输入“日语”、Japanese 或 ja；也可以选择 العربية，查看从右向左的标题排版。键盘支持方向键选择、Enter 确认和 Esc 关闭。</p>
      </div>
    </main>
  );
}
