/** WAAPI helpers shared by dictionaryApp and replay result page. */

export const MOTION_EASE_OUT = [0.22, 1, 0.36, 1];
export const MOTION_EASE_OUT_CSS = 'cubic-bezier(0.22, 1, 0.36, 1)';
export const MOTION_SPRING_CSS = 'cubic-bezier(0.2, 1.12, 0.32, 1)';
export const SUPPORTS_SCROLL_TIMELINE =
  typeof CSS !== 'undefined' && typeof CSS.supports === 'function' && CSS.supports('animation-timeline', 'scroll()');
export const COLLAPSED_PANEL_HIDDEN =
  typeof HTMLElement !== 'undefined' && 'onbeforematch' in HTMLElement.prototype ? 'until-found' : true;

export function panelHiddenAttr(isOpen) {
  if (isOpen) return '';
  return COLLAPSED_PANEL_HIDDEN === 'until-found' ? ' hidden="until-found"' : ' hidden';
}

export function createRafBatcher(fn) {
  let frameId = 0;
  return () => {
    if (frameId) return;
    frameId = requestAnimationFrame(() => {
      frameId = 0;
      fn();
    });
  };
}

export function createMotion({
  reducedMotionMedia = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null,
  headerScrollProgress = null
} = {}) {
  const activeElementAnimations = new WeakMap();
  const panelAnimationTokens = new WeakMap();

  function isReducedMotion() {
    return Boolean(reducedMotionMedia && reducedMotionMedia.matches);
  }

  function cancelElementAnimation(el) {
    if (!el) return;
    const prev = activeElementAnimations.get(el);
    if (prev) {
      try {
        prev.cancel();
      } catch (_) {}
      activeElementAnimations.delete(el);
    }
  }

  function clearAnimationInlineProps(el, propNames) {
    if (!el) return;
    for (const name of propNames) {
      el.style[name] = '';
    }
  }

  function buildWaapiKeyframes(props) {
    const fromFrame = {};
    const toFrame = {};
    const fromParts = [];
    const toParts = [];
    const transformKeys = ['x', 'y', 'scale', 'rotate'];

    for (const [key, rawVal] of Object.entries(props)) {
      const pair = Array.isArray(rawVal) ? rawVal : [null, rawVal];
      const startVal = pair[0];
      const endVal = pair[1];
      if (transformKeys.includes(key)) {
        if (key === 'x') {
          if (startVal !== null && startVal !== undefined) {
            fromParts.push(`translateX(${typeof startVal === 'number' ? `${startVal}px` : startVal})`);
          }
          if (endVal !== null && endVal !== undefined) {
            toParts.push(`translateX(${typeof endVal === 'number' ? `${endVal}px` : endVal})`);
          }
        } else if (key === 'y') {
          if (startVal !== null && startVal !== undefined) {
            fromParts.push(`translateY(${typeof startVal === 'number' ? `${startVal}px` : startVal})`);
          }
          if (endVal !== null && endVal !== undefined) {
            toParts.push(`translateY(${typeof endVal === 'number' ? `${endVal}px` : endVal})`);
          }
        } else if (key === 'scale') {
          if (startVal !== null && startVal !== undefined) fromParts.push(`scale(${startVal})`);
          if (endVal !== null && endVal !== undefined) toParts.push(`scale(${endVal})`);
        } else if (key === 'rotate') {
          if (startVal !== null && startVal !== undefined) {
            fromParts.push(`rotate(${typeof startVal === 'number' ? `${startVal}deg` : startVal})`);
          }
          if (endVal !== null && endVal !== undefined) {
            toParts.push(`rotate(${typeof endVal === 'number' ? `${endVal}deg` : endVal})`);
          }
        }
      } else {
        if (startVal !== null && startVal !== undefined) fromFrame[key] = startVal;
        if (endVal !== null && endVal !== undefined) toFrame[key] = endVal;
      }
    }

    if (fromParts.length > 0) fromFrame.transform = fromParts.join(' ');
    if (toParts.length > 0) toFrame.transform = toParts.join(' ');
    return [fromFrame, toFrame];
  }

  function runElementAnimation(el, props, opts = {}) {
    if (!el || isReducedMotion()) {
      return { finished: Promise.resolve(), cancel() {} };
    }

    cancelElementAnimation(el);

    let cancelled = false;
    let rawCtrl = null;
    const duration = typeof opts.duration === 'number' ? opts.duration : 0.22;
    const delay = typeof opts.delay === 'number' ? opts.delay : 0;

    let finished;
    if (typeof el.animate === 'function') {
      const frames = buildWaapiKeyframes(props);
      rawCtrl = el.animate(frames, {
        duration: Math.max(1, duration * 1000),
        delay: Math.max(0, delay * 1000),
        easing: opts.spring ? MOTION_SPRING_CSS : MOTION_EASE_OUT_CSS,
        fill: opts.fill || 'both'
      });
      finished = rawCtrl.finished ? rawCtrl.finished.catch(() => {}) : Promise.resolve();
    } else {
      finished = Promise.resolve();
    }

    const handle = {
      cancel() {
        cancelled = true;
        if (rawCtrl) {
          try {
            if (typeof rawCtrl.stop === 'function') rawCtrl.stop();
            if (typeof rawCtrl.cancel === 'function') rawCtrl.cancel();
          } catch (_) {}
        }
      },
      finished: finished.then(() => {
        if (activeElementAnimations.get(el) === handle) {
          activeElementAnimations.delete(el);
        }
        if (!cancelled && Array.isArray(opts.clearProps) && opts.clearProps.length > 0) {
          clearAnimationInlineProps(el, opts.clearProps);
        }
      })
    };

    activeElementAnimations.set(el, handle);
    return handle;
  }

  function updateHeaderScrollProgressFallback() {
    if (!headerScrollProgress || SUPPORTS_SCROLL_TIMELINE) return;
    if (isReducedMotion()) {
      headerScrollProgress.style.transform = 'scaleX(0)';
      return;
    }
    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    const ratio = maxScroll > 0 ? Math.min(1, Math.max(0, window.scrollY / maxScroll)) : 0;
    headerScrollProgress.style.transform = `scaleX(${ratio.toFixed(4)})`;
  }

  function syncHeaderScrollProgressDriver() {
    if (!headerScrollProgress) return;
    if (isReducedMotion()) {
      headerScrollProgress.hidden = true;
      headerScrollProgress.style.transform = 'scaleX(0)';
      return;
    }
    headerScrollProgress.hidden = false;
    if (!SUPPORTS_SCROLL_TIMELINE) {
      updateHeaderScrollProgressFallback();
    } else {
      headerScrollProgress.style.transform = '';
    }
  }

  function animateEntryPanelToggle(panel, trigger, shouldOpen, delaySec = 0) {
    if (!panel || !trigger) return;
    trigger.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');

    const token = (panelAnimationTokens.get(panel) || 0) + 1;
    panelAnimationTokens.set(panel, token);
    cancelElementAnimation(panel);

    const animProps = ['height', 'paddingTop', 'paddingBottom', 'opacity', 'transform'];

    if (isReducedMotion()) {
      panel.classList.remove('is-animating');
      panel.hidden = shouldOpen ? false : COLLAPSED_PANEL_HIDDEN;
      clearAnimationInlineProps(panel, animProps);
      return;
    }

    if (shouldOpen) {
      if (!panel.hidden && !panel.classList.contains('is-animating')) return;
      panel.hidden = false;
      panel.classList.add('is-animating');
      clearAnimationInlineProps(panel, animProps);
      const cs = getComputedStyle(panel);
      const padTop = cs.paddingTop || '0px';
      const padBottom = cs.paddingBottom || '0px';
      const targetHeight = panel.scrollHeight;
      const ctrl = runElementAnimation(
        panel,
        {
          height: ['0px', `${targetHeight}px`],
          paddingTop: ['0px', padTop],
          paddingBottom: ['0px', padBottom],
          opacity: [0, 1]
        },
        { duration: 0.22, delay: delaySec }
      );
      ctrl.finished.then(() => {
        if (panelAnimationTokens.get(panel) !== token) return;
        panel.classList.remove('is-animating');
        clearAnimationInlineProps(panel, animProps);
        updateHeaderScrollProgressFallback();
      });
      return;
    }

    if (panel.hidden) return;
    const cs = getComputedStyle(panel);
    const padTop = cs.paddingTop || '0px';
    const padBottom = cs.paddingBottom || '0px';
    const currentHeight = panel.getBoundingClientRect().height || panel.scrollHeight;
    panel.classList.add('is-animating');
    const ctrl = runElementAnimation(
      panel,
      {
        height: [`${currentHeight}px`, '0px'],
        paddingTop: [padTop, '0px'],
        paddingBottom: [padBottom, '0px'],
        opacity: [1, 0]
      },
      { duration: 0.2, delay: delaySec }
    );
    ctrl.finished.then(() => {
      if (panelAnimationTokens.get(panel) !== token) return;
      panel.hidden = COLLAPSED_PANEL_HIDDEN;
      panel.classList.remove('is-animating');
      clearAnimationInlineProps(panel, animProps);
      updateHeaderScrollProgressFallback();
    });
  }

  function bindPressFeedback() {
    // Press scale feedback is handled declaratively in CSS via :active:not(:disabled).
  }

  let scrollRaf = 0;

  function bindHeaderScrollProgressFallbackScroll() {
    window.addEventListener(
      'scroll',
      () => {
        if (scrollRaf) return;
        scrollRaf = requestAnimationFrame(() => {
          scrollRaf = 0;
          updateHeaderScrollProgressFallback();
        });
      },
      { passive: true }
    );
  }

  function bindReducedMotionHeaderSync() {
    if (reducedMotionMedia && typeof reducedMotionMedia.addEventListener === 'function') {
      reducedMotionMedia.addEventListener('change', syncHeaderScrollProgressDriver);
    }
  }

  /** Fade / slide out → swap DOM → fade / slide in. */
  function animateContentSwap(el, swapFn, opts = {}) {
    if (!el) {
      swapFn?.();
      return Promise.resolve();
    }
    if (isReducedMotion()) {
      swapFn?.();
      return Promise.resolve();
    }
    cancelElementAnimation(el);
    const axis = opts.axis === 'x' ? 'x' : 'y';
    const direction = typeof opts.direction === 'number' && opts.direction !== 0 ? Math.sign(opts.direction) : 1;
    const slidePx = typeof opts.slidePx === 'number' ? opts.slidePx : (axis === 'x' ? 24 : 6);
    const outOffset = axis === 'x' ? -direction * slidePx : (typeof opts.outY === 'number' ? opts.outY : -4);
    const inOffset = axis === 'x' ? direction * slidePx : (typeof opts.inY === 'number' ? opts.inY : 6);
    const outDuration = typeof opts.outDuration === 'number' ? opts.outDuration : (axis === 'x' ? 0.16 : 0.14);
    const inDuration = typeof opts.inDuration === 'number' ? opts.inDuration : (axis === 'x' ? 0.24 : 0.22);
    const swappingClass = opts.swappingClass || '';
    if (swappingClass) el.classList.add(swappingClass);

    const outProps = { opacity: [1, 0], [axis]: [0, outOffset] };
    const inProps = { opacity: [0, 1], [axis]: [inOffset, 0] };

    const finishSwap = () => {
      if (swappingClass) {
        el.classList.remove(swappingClass);
      }
    };

    return runElementAnimation(el, outProps, { duration: outDuration }).finished.then(() => {
      const nextEl = swapFn?.();
      const target = nextEl && typeof nextEl.animate === 'function' ? nextEl : el;
      if (!target || (target !== el && !target.isConnected)) {
        finishSwap();
        return Promise.resolve();
      }
      if (swappingClass && target !== el) {
        target.classList.add(swappingClass);
      }
      return runElementAnimation(target, inProps, {
        duration: inDuration,
        clearProps: ['opacity', 'transform']
      }).finished.finally(() => {
        if (swappingClass) {
          target.classList.remove(swappingClass);
          el.classList.remove(swappingClass);
        }
      });
    });
  }

  /** Whole card pushed off-screen, next chapter slides in from the opposite side. */
  function animateChapterPush(el, swapFn, direction = 1, opts = {}) {
    if (!el) {
      swapFn?.();
      return Promise.resolve();
    }
    if (isReducedMotion()) {
      swapFn?.();
      return Promise.resolve();
    }
    cancelElementAnimation(el);
    const dir = typeof direction === 'number' && direction !== 0 ? Math.sign(direction) : 1;
    const outTo = dir > 0 ? '-100%' : '100%';
    const inFrom = dir > 0 ? '100%' : '-100%';
    const outDuration = typeof opts.outDuration === 'number' ? opts.outDuration : 0.24;
    const inDuration = typeof opts.inDuration === 'number' ? opts.inDuration : 0.28;
    const swappingClass = opts.swappingClass || '';
    const viewport = opts.viewport || null;

    const markSwapping = () => {
      if (!swappingClass) return;
      if (viewport) viewport.classList.add(swappingClass);
      else el.classList.add(swappingClass);
    };
    markSwapping();

    const cleanup = () => {
      if (!swappingClass) return;
      if (viewport) viewport.classList.remove(swappingClass);
      el.classList.remove(swappingClass);
    };

    return runElementAnimation(
      el,
      { x: [0, outTo] },
      { duration: outDuration, fill: 'forwards' }
    ).finished.then(() => {
      const nextEl = swapFn?.();
      const target = nextEl && typeof nextEl.animate === 'function' ? nextEl : el;
      if (!target || (target !== el && !target.isConnected)) {
        cleanup();
        return Promise.resolve();
      }
      target.style.transform = `translateX(${inFrom})`;
      return runElementAnimation(
        target,
        { x: [inFrom, 0] },
        { duration: inDuration, fill: 'both' }
      ).finished.finally(() => {
        clearAnimationInlineProps(target, ['transform']);
        cleanup();
      });
    });
  }

  return {
    isReducedMotion,
    runElementAnimation,
    cancelElementAnimation,
    clearAnimationInlineProps,
    updateHeaderScrollProgressFallback,
    syncHeaderScrollProgressDriver,
    animateEntryPanelToggle,
    animateContentSwap,
    animateChapterPush,
    bindPressFeedback,
    bindHeaderScrollProgressFallbackScroll,
    bindReducedMotionHeaderSync
  };
}