"""把 results/*.json 汇总成 result.html：按 harness + 模型分列，可切换查看每条用例的改写。"""
import argparse, base64, json, pathlib, re, sys
HERE = pathlib.Path(__file__).resolve().parent
REPO = str(HERE.parent)
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
import scan
from replay import BACKENDS

KEEP_PREFIXES = ("【措辞已确认",) + tuple(
    loc["keep_mark"] for loc in scan.LOCALES.values() if loc.get("keep_mark")
)
REMOVED_TERMS = {"spine"}


def terms(reason):
    text = reason or ""
    found = re.findall(r"■ 「(.+?)」（(.+?)）", text)
    if found:
        return [(t, lv) for t, lv in found if t not in REMOVED_TERMS]
    return [(t, lv) for t, lv in re.findall(r'^■ "(.+?)" \((.+?)\)', text, flags=re.M) if t not in REMOVED_TERMS]


def facts(text):
    """原文里的可核对事实：数字、反引号标识符、「」里的文案。"""
    return set(re.findall(r"`[^`]+`|\d+(?:\.\d+)?|「[^」]+」", text))


def summarize(case, r):
    rs = r["rounds"]
    final = rs[-1]["text"]
    kept = final.startswith(KEEP_PREFIXES)
    eff = case["reply"] if kept else final
    f0 = facts(case["reply"])
    lost = sorted(f for f in f0 if f.strip("`「」") not in eff)
    hit0 = [t for t, _ in terms(rs[0]["reason"])]
    if not rs[0]["blocked"]:
        status = "pass0"
    elif rs[-1]["blocked"]:
        status = "fail"
    elif kept:
        status = "kept"
    else:
        status = "fixed"
    residual = [t for t in hit0 if t in eff] if not kept else []
    return {"status": status, "rounds": len(rs) - 1, "lost": lost, "nfacts": len(f0),
            "residual": residual, "hits": hit0}


page = """<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>改写结果对比</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{color-scheme:light dark;--bg:#fff;--header-bg:rgba(255,255,255,.92);--surface-subtle:#f5f5f7;--surface-hover:#ededf0;--ink:#111;--muted:#525252;--faint:#666;--line:#e9e9ec;--line-strong:#d0d0d5;--accent:#2f54eb;--accent-ink:#fff;--accent-soft:rgba(47,84,235,.08);--hit-bg:rgba(245,158,11,.28);--hit-ink:#7c2d12;--hit-border:rgba(217,119,6,.55);--rewrite-bg:rgba(16,185,129,.22);--rewrite-ink:#065f46;--rewrite-border:rgba(5,150,105,.5);--lv1:#b4371f;--lv1-soft:rgba(180,55,31,.08);--lv2:#855c00;--lv2-soft:rgba(133,92,0,.08);--lv3:#1b654d;--lv3-soft:rgba(27,101,77,.08);--font-sans:'Inter','Noto Sans SC',-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;--font-mono:ui-monospace,SFMono-Regular,Menlo,monospace;--radius-sm:4px;--radius-md:6px;--radius-lg:10px;--radius-pill:999px;--ease-out:cubic-bezier(.22,1,.36,1)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0e0e0f;--header-bg:rgba(14,14,15,.92);--surface-subtle:#18181b;--surface-hover:#222226;--ink:#efefef;--muted:#b0b0b5;--faint:#96969c;--line:#27272a;--line-strong:#3f3f46;--accent:#7aa2ff;--accent-ink:#0e0e0f;--accent-soft:rgba(122,162,255,.14);--hit-bg:rgba(251,191,36,.24);--hit-ink:#fde68a;--hit-border:rgba(251,191,36,.6);--rewrite-bg:rgba(52,211,153,.20);--rewrite-ink:#a7f3d0;--rewrite-border:rgba(52,211,153,.55);--lv1:#f29b82;--lv1-soft:rgba(242,155,130,.12);--lv2:#e5c56b;--lv2-soft:rgba(229,197,107,.12);--lv3:#7fc9ab;--lv3-soft:rgba(127,201,171,.12)}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#0e0e0f;--header-bg:rgba(14,14,15,.92);--surface-subtle:#18181b;--surface-hover:#222226;--ink:#efefef;--muted:#b0b0b5;--faint:#96969c;--line:#27272a;--line-strong:#3f3f46;--accent:#7aa2ff;--accent-ink:#0e0e0f;--accent-soft:rgba(122,162,255,.14);--hit-bg:rgba(251,191,36,.24);--hit-ink:#fde68a;--hit-border:rgba(251,191,36,.6);--rewrite-bg:rgba(52,211,153,.20);--rewrite-ink:#a7f3d0;--rewrite-border:rgba(52,211,153,.55);--lv1:#f29b82;--lv1-soft:rgba(242,155,130,.12);--lv2:#e5c56b;--lv2-soft:rgba(229,197,107,.12);--lv3:#7fc9ab;--lv3-soft:rgba(127,201,171,.12)}
:root[data-theme="light"]{color-scheme:light}
/* 以下组件样式取自 web/src/styles.css，保持与词典页一致 */
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--ink);font-family:var(--font-sans);font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased;transition:background-color 200ms var(--ease-out),color 200ms var(--ease-out)}
button{font:inherit}a{color:inherit;text-decoration:none}
.od-icon{display:inline-block;inline-size:var(--od-icon-size,1em);block-size:var(--od-icon-size,1em);flex:none}
.page-shell{max-width:1040px;margin:0 auto;padding:0 24px}
.site-header-bar{position:sticky;top:0;z-index:30;background:var(--header-bg);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.header-scroll-progress{position:absolute;left:0;right:0;top:0;height:2px;background:var(--accent);transform-origin:left center;transform:scaleX(0);pointer-events:none;opacity:.9;will-change:transform}
@media (prefers-reduced-motion:no-preference){@supports (animation-timeline:scroll()){@keyframes header-scroll-grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}.header-scroll-progress{animation:header-scroll-grow auto linear both;animation-timeline:scroll(root block)}}:is(.header-search-btn,.theme-toggle,.filter-pill,.entry-trigger,.effort-tab):active:not(:disabled){transform:scale(.97)}}
@media (prefers-reduced-motion:reduce){.header-scroll-progress{display:none}}
.site-header{display:flex;justify-content:space-between;align-items:center;height:64px;gap:16px}
.brand{display:inline-flex;align-items:center;gap:10px;min-width:0}.brand-mark{display:block;width:40px;height:34px;flex:none}
.brand-mark-flow{width:44px;height:35px;overflow:visible}
.brand-flow-human,.brand-flow-ai{fill:none;stroke-linecap:round;stroke-linejoin:round}
.brand-flow-human{stroke:var(--ink)}.brand-flow-ai{stroke:var(--accent)}
.brand-flow-loop{stroke-width:2.3}.brand-flow-quote{stroke-width:2.7}
.brand-candidate-solid{fill:var(--accent);stroke:none}
.brand-wordmark{display:inline-flex;align-items:baseline;font-size:14px;font-weight:700;letter-spacing:.06em;white-space:nowrap}
.brand-wordmark-si{color:var(--accent)}.brand-wordmark-en{margin:0 .04em;font-weight:500;color:var(--muted);letter-spacing:0}.brand-wordmark-c{color:var(--ink)}
.header-actions{display:flex;align-items:center;gap:12px;font-size:13px;color:var(--muted)}
.header-search-btn{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:0 12px;border:1px solid var(--line-strong);border-radius:var(--radius-pill);background:transparent;color:var(--ink);font-size:13px;font-weight:500;cursor:pointer;transition:border-color 160ms var(--ease-out),background-color 160ms var(--ease-out)}
.header-search-btn .od-icon{--od-icon-size:14px}
.theme-toggle{width:44px;height:44px;border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:22px;cursor:pointer;display:grid;place-items:center;transition:border-color 160ms var(--ease-out),background-color 160ms var(--ease-out)}
.theme-toggle .od-icon{--od-icon-size:16px}
@media (hover:hover){.header-search-btn:hover,.theme-toggle:hover{border-color:var(--ink);background:var(--surface-subtle)}}
.hero{padding:40px 0 28px}.hero-eyebrow{margin:0 0 14px;font-size:13px;color:var(--faint);letter-spacing:.03em}
.hero-title{margin:0;font-size:clamp(30px,5.5vw,48px);line-height:1.16;font-weight:700;letter-spacing:-.015em;text-wrap:balance}
.hero-lede{margin:14px 0 0;font-size:15px;color:var(--muted);max-width:680px;text-wrap:pretty}
.search-bar{display:flex;align-items:center;gap:14px;min-height:56px;border-bottom:1.5px solid var(--ink)}
.search-bar:focus-within{border-bottom-color:var(--accent)}.search-icon{--od-icon-size:18px;color:var(--ink)}
.search-input{flex:1 1 0;min-width:0;height:44px;border:0;outline:none;background:transparent;color:var(--ink);font-size:17px}
.search-input::placeholder{color:var(--faint)}
.level-toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px 16px;padding:14px 0 4px}
.filter-row{display:flex;flex-wrap:wrap;gap:8px}
.filter-pill{display:inline-flex;align-items:center;gap:6px;min-height:32px;padding:0 11px;border:1px solid var(--line-strong);border-radius:var(--radius-pill);background:var(--bg);color:var(--muted);font-size:12.5px;font-weight:500;cursor:pointer;transition:border-color 150ms var(--ease-out),background-color 150ms var(--ease-out),color 150ms var(--ease-out)}
.filter-count{font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums}
.filter-pill[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}.filter-pill[aria-pressed="true"] .filter-count{color:var(--bg);opacity:.78}
@media (hover:hover){.filter-pill:not([aria-pressed="true"]):hover{border-color:var(--ink);color:var(--ink)}}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--faint)}.legend span{display:inline-flex;align-items:center;gap:5px}
.dict-main{padding-bottom:88px}
.letter-group{padding-top:32px;scroll-margin-top:84px}
.letter-header{display:flex;align-items:baseline;gap:12px;padding-bottom:10px;border-bottom:2px solid var(--ink)}
.letter-char{margin:0;font-size:30px;font-weight:700;line-height:1}.letter-sub{font-size:15px;font-weight:600}.letter-count{font-size:12px;color:var(--faint)}
.entry-row{border-bottom:1px solid var(--line)}
.entry-trigger{display:flex;align-items:center;gap:16px;padding:18px 8px;margin:0 -8px;width:calc(100% + 16px);border-radius:var(--radius-md);background:transparent;border:0;color:var(--ink);text-align:left;cursor:pointer;transition:background-color 160ms var(--ease-out)}
@media (hover:hover){.entry-trigger:hover{background:var(--surface-subtle)}.entry-trigger:hover .entry-term{text-decoration:underline;text-underline-offset:4px;text-decoration-thickness:1.5px}}
.entry-head{min-width:168px;display:flex;align-items:baseline;gap:8px;flex:none}
.entry-term{font-size:21px;font-weight:600;line-height:1.3}
.entry-why{flex:1 1 0;min-width:0;font-size:14px;color:var(--muted)}
.entry-meta-end{display:inline-flex;align-items:center;gap:10px;flex:none}
.level-badge{font-size:12px;font-weight:500;padding:2px 10px;border-radius:var(--radius-pill);border:1px solid currentColor;white-space:nowrap;flex:none}
.level-badge[data-level="1"]{color:var(--lv1)}.level-badge[data-level="2"]{color:var(--lv2)}.level-badge[data-level="3"]{color:var(--lv3)}
.entry-chevron{--od-icon-size:16px;color:var(--faint);transition:transform 200ms var(--ease-out),color 160ms var(--ease-out)}
.entry-trigger[aria-expanded="true"] .entry-chevron{transform:rotate(180deg);color:var(--ink)}
.entry-panel{font-size:15px;line-height:1.7;transform-origin:top center}
.entry-panel:not([hidden]){display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:16px 24px;padding:4px 0 28px}
.entry-panel[hidden="until-found"]{padding:0}
.entry-panel.is-animating{overflow:hidden;will-change:height,opacity,transform}
.detail-label{font-size:13px;color:var(--faint);margin-bottom:8px}
.suggest-box{padding:12px 14px;border-radius:var(--radius-md);background:var(--surface-subtle);border:1px solid var(--line)}
.orig-col{align-self:start;position:sticky;top:76px}
.reply-text{white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink);text-wrap:pretty}
.hit-badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.search-hit{background:var(--hit-bg);color:var(--hit-ink);border-bottom:1.5px solid var(--hit-border);border-radius:3px;padding:0 3px;font-weight:500}
.rewrite-hit{background:var(--rewrite-bg);color:var(--rewrite-ink);border-bottom:1.5px solid var(--rewrite-border);border-radius:3px;padding:0 3px;font-weight:500}
.entry-panel .models-col{min-width:0;overflow:hidden}
.community-list{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:8px}
.community-item{width:100%;min-width:0;box-sizing:border-box;padding:10px 12px;background:var(--surface-subtle);border:1px solid var(--line);border-radius:var(--radius-md)}
.community-item-main{min-width:0}
.community-item-chapter-viewport{overflow:hidden;width:100%;min-width:0;margin-top:2px}
.community-item-chapter-viewport.is-chapter-push{overflow:hidden}
.community-item-chapter-layer{will-change:auto}
.community-item-chapter-viewport.is-chapter-push .community-item-chapter-layer{will-change:transform}
.community-item-slide-meta{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:4px 8px;margin-bottom:6px;font-size:12px;color:var(--faint)}
.model-meta--stable{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.harness-cell{display:inline-flex;align-items:center;gap:7px;white-space:nowrap}
.harness-icon{width:14px;height:14px;flex:none;display:inline-block;color:var(--ink)}
.row-summary{font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums;white-space:nowrap}
.row-summary--ok{color:var(--lv3)}
.row-summary--warn{color:var(--lv2)}
.row-summary--fail{color:var(--lv1)}
.model-tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.model-tab{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border:1px solid var(--line);border-radius:var(--radius-md);background:var(--bg);color:var(--muted);font-size:12px;font-weight:500;cursor:pointer;line-height:1.35;transition:border-color 150ms var(--ease-out),background-color 150ms var(--ease-out),color 150ms var(--ease-out)}
.model-tab .harness-icon{width:13px;height:13px}
.model-tab[aria-pressed="true"]{border-color:var(--ink);background:var(--surface-subtle);color:var(--ink);font-weight:600}
@media (hover:hover){.model-tab:not([aria-pressed="true"]):hover{border-color:var(--line-strong);color:var(--ink)}}
.model-tab-dot{width:6px;height:6px;border-radius:50%;flex:none}
.model-tab-dot.fail{background:var(--lv1)}
.model-tab-dot.lost{background:var(--lv2)}
.model-line{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 10px;margin-bottom:4px}
.model-name{font-size:14px;font-weight:600;color:var(--ink)}.model-meta{font-size:12px;color:var(--faint)}
.status-text{font-weight:600}.status-text--fixed{color:var(--lv3)}.status-text--kept{color:var(--accent)}.status-text--fail{color:var(--lv1)}.status-text--pass0{color:var(--faint)}
.model-head{display:inline-flex;flex-wrap:wrap;align-items:center;gap:8px}
.effort-tabs{display:inline-flex;align-items:center;gap:4px}
.effort-tab{display:inline-flex;align-items:center;gap:5px;padding:1px 8px;border:1px solid var(--line-strong);border-radius:var(--radius-pill);background:var(--bg);color:var(--muted);font-size:11.5px;font-weight:500;cursor:pointer;line-height:1.5;transition:border-color 150ms var(--ease-out),background-color 150ms var(--ease-out),color 150ms var(--ease-out)}
.effort-tab[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
span.effort-tab{cursor:default}
@media (hover:hover){.effort-tab:not([aria-pressed="true"]):hover{border-color:var(--ink);color:var(--ink)}}
.community-item-text{color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere}.community-item-text.is-same{color:var(--muted)}
.community-item-note{margin-top:6px;font-size:13px;color:var(--lv2)}
.context-tag{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;margin-top:2px;border-radius:var(--radius-sm);flex:none;font-size:12px;font-weight:700}
.context-tag--fixed{color:var(--lv3);background:var(--lv3-soft)}.context-tag--fail{color:var(--lv1);background:var(--lv1-soft)}
.context-tag--kept{color:var(--accent);background:var(--accent-soft)}.context-tag--pass0{color:var(--faint);background:var(--bg);border:1px solid var(--line)}
.local-badge{display:inline-flex;align-items:center;font-size:11px;font-weight:500;padding:1px 8px;border-radius:var(--radius-pill);border:1px solid var(--lv2);color:var(--lv2);background:var(--lv2-soft);white-space:nowrap}
.dots{display:inline-flex;gap:4px}.dot{width:8px;height:8px;border-radius:50%;flex:none}
.dot.fixed{background:var(--lv3)}.dot.kept{background:var(--accent)}.dot.fail{background:var(--lv1)}.dot.pass0{background:var(--line-strong)}.dot.lost{background:var(--lv2)}
details{margin-top:8px;font-size:13px}summary{cursor:pointer;color:var(--faint)}summary:hover{color:var(--ink)}
pre{white-space:pre-wrap;font-family:var(--font-mono);font-size:12px;line-height:1.6;background:var(--bg);border:1px solid var(--line);padding:10px;border-radius:var(--radius-md);max-height:320px;overflow:auto;color:var(--muted)}
.sum-wrap{overflow-x:auto;margin-top:4px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top}
th{font-weight:500;color:var(--faint);white-space:nowrap;font-size:12px}td.num{text-align:right;font-variant-numeric:tabular-nums}
td b{font-weight:600}.c-fixed{color:var(--lv3)}.c-kept{color:var(--accent)}.c-fail{color:var(--lv1)}
.empty-state{padding:48px 0;text-align:center;color:var(--faint)}
.empty-state h2{margin:0 0 8px;font-size:18px;font-weight:600;color:var(--ink)}
.empty-state p{margin:0 auto 20px;max-width:48ch;font-size:14px;line-height:1.65;color:var(--muted)}
.empty-actions{display:flex;flex-wrap:wrap;justify-content:center;gap:10px}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:38px;padding:0 16px;border-radius:var(--radius-pill);font-size:13px;font-weight:500;cursor:pointer;border:1px solid var(--line-strong);background:transparent;color:var(--ink)}
.btn-primary{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.hero-top-row{display:flex;flex-wrap:wrap;align-items:center;gap:12px 16px;margin-bottom:14px}
.lang-switch{position:relative;display:inline-grid;grid-auto-flow:column;grid-auto-columns:1fr;align-items:center;padding:3px;border:1px solid var(--line-strong);border-radius:var(--radius-pill);background:var(--surface-subtle)}
.lang-switch-thumb{position:absolute;top:3px;bottom:3px;left:3px;width:calc(50% - 3px);border-radius:var(--radius-pill);background:var(--ink);pointer-events:none;z-index:0;transform:translate3d(0,0,0);transition:transform 220ms var(--ease-out)}
.lang-switch[data-active="en"] .lang-switch-thumb{transform:translate3d(100%,0,0)}
.lang-btn{position:relative;z-index:1;min-height:30px;padding:0 13px;border:0;border-radius:var(--radius-pill);background:transparent;color:var(--muted);font-size:12.5px;font-weight:500;cursor:pointer;white-space:nowrap}
.lang-btn[aria-pressed="true"]{color:var(--bg)}
.site-footer{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;padding:28px 0 48px;border-top:1px solid var(--line);font-size:12px;color:var(--faint)}
@media (max-width:760px){.page-shell{padding:0 16px}.entry-panel:not([hidden]){grid-template-columns:1fr}.orig-col{position:static}.entry-head{min-width:0}.entry-why{display:none}.brand-wordmark{display:none}}
</style>
<div class="site-header-bar"><div class="header-scroll-progress" id="header-scroll-progress" aria-hidden="true"></div><header class="site-header page-shell">
<a class="brand" id="brand-home-link" href="../" aria-label="返回词典首页">__BRAND_MARK__
<span class="brand-wordmark"><span class="brand-wordmark-si">Si</span><span class="brand-wordmark-en">–</span><span class="brand-wordmark-c">C</span></span></a>
<div class="header-actions">
<a class="header-search-btn" id="back-home-btn" href="../"><svg class="od-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg><span id="back-home-label">返回词典</span></a>
<a class="header-search-btn" id="summary-nav-btn" href="#summary"><svg class="od-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg><span id="summary-nav-label">按模型汇总</span></a>
<button type="button" class="theme-toggle" id="theme-toggle" aria-label="切换深浅色"><svg class="od-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16Z" fill="currentColor"/></svg></button>
</div></header></div>
<div class="page-shell">
<section class="hero">
  <div class="hero-top-row">
    <div class="lang-switch" id="lang-switch" data-active="zh" role="group" aria-label="切换语言">
      <span class="lang-switch-thumb" aria-hidden="true"></span>
      <button type="button" class="lang-btn" data-lang="zh" aria-pressed="true">中文</button>
      <button type="button" class="lang-btn" data-lang="en" aria-pressed="false">English</button>
    </div>
    <p class="hero-eyebrow" id="eyebrow"></p>
  </div>
  <h1 class="hero-title" id="hero-title">改写结果对比</h1>
</section>
<div class="search-bar" id="search-bar"><svg class="od-icon search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
<input class="search-input" id="q" placeholder="搜索用例、命中词或回复内容" autocomplete="off"></div>
<div class="level-toolbar" id="level-toolbar"><div class="filter-row" id="filters"></div></div>
<main class="dict-main" id="groups"></main>
<section class="letter-group" id="summary"><div class="letter-header"><h2 class="letter-char" id="summary-title">汇总</h2><span class="letter-count" id="summary-sub">按 harness 与模型</span></div>
<div class="sum-wrap"><table id="sumtab"></table></div></section>
<footer class="site-footer"><span id="foot-src">由 replay/render.py 生成</span><span id="foot-meta"></span></footer>
</div>
<script type="module">
import { createMotion, createRafBatcher, panelHiddenAttr } from "./motion.js";
const D = __DATA__;
const esc = s => (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const hl = (t, ws) => { let h = esc(t); [...new Set(ws)].sort((a,b)=>b.length-a.length).forEach(w => h = h.split(esc(w)).join(`<mark class="search-hit">${esc(w)}</mark>`)); return h; };
function lcsPairs(a, b) {
  const n = a.length, m = b.length;
  if (!n || !m || n * m > 250000) return [];
  const dp = new Int32Array((n + 1) * (m + 1));
  for (let i = n - 1; i >= 0; i--) {
    const row = i * (m + 1), next = (i + 1) * (m + 1);
    for (let j = m - 1; j >= 0; j--) {
      dp[row + j] = a[i] === b[j] ? dp[next + j + 1] + 1 : Math.max(dp[next + j], dp[row + j + 1]);
    }
  }
  const pairs = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { pairs.push([i, j]); i++; j++; }
    else if (dp[(i + 1) * (m + 1) + j] >= dp[i * (m + 1) + j + 1]) i++;
    else j++;
  }
  return pairs;
}
function markWords(chars, ws) {
  const hit = new Uint8Array(chars.length), str = chars.join("");
  const uniq = [...new Set(ws)].filter(Boolean).sort((a, b) => b.length - a.length);
  uniq.forEach(w => {
    const wChars = Array.from(w);
    let pos = 0;
    while ((pos = str.indexOf(w, pos)) !== -1) {
      const ci = Array.from(str.slice(0, pos)).length;
      for (let k = 0; k < wChars.length; k++) hit[ci + k] = 1;
      pos += w.length;
    }
  });
  return hit;
}
function formatRewriteSpan(buf) {
  const punctEdge = /^([，。！？；：、（）()【】\\[\\]「」『』《》“”‘’"'`—–\\-·….,!?;:\\s]*)([\\s\\S]*?)([，。！？；：、（）()【】\\[\\]「」『』《》“”‘’"'`—–\\-·….,!?;:\\s]*)$/;
  return buf.split(/([。！？；\\n]+)/).map(part => {
    if (!part || /^[。！？；\\n]+$/.test(part)) return esc(part);
    const m = part.match(punctEdge);
    if (!m || !m[2]) return esc(part);
    return esc(m[1]) + `<mark class="rewrite-hit">${esc(m[2])}</mark>` + esc(m[3]);
  }).join("");
}
const wordSegmenter = typeof Intl !== "undefined" && Intl.Segmenter ? new Intl.Segmenter("zh-CN", { granularity: "word" }) : null;
function expandToWordUnits(rChunk, rChars, rGreen, rHit) {
  // 1. Merge 1-char non-punct gap sandwiched between two green spans
  const punctChar = /^[，。！？；：、（）()【】\\[\\]「」『』《》“”‘’"'`—–\\-·….,!?;:\\s]$/;
  for (let k = 1; k < rChars.length - 1; k++) {
    if (!rGreen[k] && !rHit[k] && rGreen[k - 1] && rGreen[k + 1] && !punctChar.test(rChars[k])) {
      rGreen[k] = 1;
    }
  }
  // 2. Expand partial word highlights to complete word units via Intl.Segmenter
  if (!wordSegmenter) return;
  let ci = 0;
  for (const seg of wordSegmenter.segment(rChunk)) {
    const len = Array.from(seg.segment).length;
    if (seg.isWordLike && len > 1) {
      let anyGreen = false, anyHit = false;
      for (let k = ci; k < ci + len; k++) {
        if (rGreen[k]) anyGreen = true;
        if (rHit[k]) anyHit = true;
      }
      if (anyGreen && !anyHit) {
        for (let k = ci; k < ci + len; k++) rGreen[k] = 1;
      }
    }
    ci += len;
  }
}
function hlRewrite(orig, rewritten, ws) {
  if (!orig || !ws || !ws.length) return hl(rewritten, ws);
  const oLines = orig.split("\\n"), rLines = rewritten.split("\\n");
  const linePairs = lcsPairs(oLines, rLines);
  const anchors = [[-1, -1], ...linePairs, [oLines.length, rLines.length]];
  const outLines = [];
  for (let a = 0; a < anchors.length - 1; a++) {
    const [oi0, ri0] = anchors[a], [oi1, ri1] = anchors[a + 1];
    if (a > 0) outLines.push(hl(rLines[ri0], ws));
    const oChunk = oLines.slice(oi0 + 1, oi1).join("\\n");
    const rChunk = rLines.slice(ri0 + 1, ri1).join("\\n");
    if (ri1 - ri0 <= 1) continue;
    if (!oChunk) { outLines.push(hl(rChunk, ws)); continue; }
    const oChars = Array.from(oChunk), rChars = Array.from(rChunk);
    const oHit = markWords(oChars, ws);
    if (!oHit.some(Boolean)) { outLines.push(hl(rChunk, ws)); continue; }
    const rHit = markWords(rChars, ws);
    const rGreen = new Uint8Array(rChars.length);
    const charPairs = lcsPairs(oChars, rChars);
    const cAnchors = [[-1, -1], ...charPairs, [oChars.length, rChars.length]];
    for (let c = 0; c < cAnchors.length - 1; c++) {
      const [oci0, rci0] = cAnchors[c], [oci1, rci1] = cAnchors[c + 1];
      let hasHit = false;
      for (let k = oci0 + 1; k < oci1; k++) if (oHit[k]) { hasHit = true; break; }
      if (hasHit) for (let k = rci0 + 1; k < rci1; k++) if (!rHit[k]) rGreen[k] = 1;
    }
    expandToWordUnits(rChunk, rChars, rGreen, rHit);
    let html = "", cur = -1, buf = "";
    const flush = () => {
      if (!buf) return;
      html += cur === 1 ? `<mark class="search-hit">${esc(buf)}</mark>` : cur === 2 ? formatRewriteSpan(buf) : esc(buf);
      buf = "";
    };
    for (let k = 0; k < rChars.length; k++) {
      const st = rHit[k] ? 1 : rGreen[k] ? 2 : 0;
      if (st !== cur) { flush(); cur = st; }
      buf += rChars[k];
    }
    flush();
    outLines.push(html);
  }
  return outLines.join("\\n");
}
const LV = {"最好修改":1,"看语境":2,"补充说明":3};
const TAG = {fixed:"✓", kept:"◎", fail:"✗", pass0:"–"};
const I18N = {
  zh: {
    htmlLang: "zh-CN",
    docTitle: "改写结果对比 · 图灵高阶硅碳词典",
    brandAria: "返回词典首页",
    backHome: "返回词典",
    summaryNav: "按模型汇总",
    heroTitle: "改写结果对比",
    heroLede: "把同一批真实 AI 回复交给装了 Hook 的不同模型重写，逐条对比改写结果，并核对原文里的事实有没有丢。",
    searchPlaceholder: "搜索用例、命中词或回复内容",
    summaryTitle: "汇总",
    summarySub: "按 harness 与模型",
    footSrc: "由 replay/render.py 生成",
    themeLight: "切换浅色模式",
    themeDark: "切换深色模式",
    stxt: {fixed:"改写通过", kept:"保留原文", fail:"3 轮仍未通过", pass0:"未命中"},
    filters: [["all","全部"], ["typical","典型"], ["frequent","高频"], ["valid","正当"]],
    legend: [["fixed","改写通过"],["kept","保留原文"],["fail","未通过"],["lost","丢失事实"],["pass0","未命中"]],
    origLabel: "原始回复",
    modelsLabel: "各模型改写后",
    hookRaw: "hook 反馈原文",
    pass0Text: "未命中，不需要改写",
    keptText: "判定保留原文",
    noHit: "未命中",
    hitsCount: n => `${n} 处命中`,
    caseCount: n => `${n} 条`,
    roundBlocked: n => `第 ${n} 轮（仍被拦）`,
    roundsCount: n => `${n} 轮`,
    lostBadge: n => `丢 ${n} 项事实`,
    lostNote: "丢失：",
    emptySearch: "没有符合条件的用例",
    emptyLangTitle: "暂无中文改写对比用例",
    eyebrow: (mCount, vCount, cCount) => `${mCount} 个模型${vCount > mCount ? `（${vCount} 组推理）` : ""} · ${cCount} 条用例`,
    footExtra: " · 事实保留率按原文中的数字、反引号标识符、「」文案计算",
    sumHeaders: ["Harness","模型","推理","被拦 / 用例","改写通过","保留原文","未通过","平均轮数","事实保留率","丢事实的用例"],
  },
  en: {
    htmlLang: "en",
    docTitle: "Rewrite Comparison · Turing Advanced Silicon–Carbon Dictionary",
    brandAria: "Back to dictionary home",
    backHome: "Dictionary",
    summaryNav: "Summary",
    heroTitle: "Rewrite Comparison",
    heroLede: "The same real AI replies, rewritten by different models with the hook installed, compared case by case — including whether facts in the original survived.",
    searchPlaceholder: "Search cases, matched terms, or reply text",
    summaryTitle: "Summary",
    summarySub: "By harness & model",
    footSrc: "Generated by replay/render.py",
    themeLight: "Switch to light mode",
    themeDark: "Switch to dark mode",
    stxt: {fixed:"Rewritten", kept:"Kept original", fail:"Failed after 3 rounds", pass0:"No hits"},
    filters: [["all","All"], ["typical","Typical"], ["frequent","Frequent"], ["valid","Valid"]],
    legend: [["fixed","Rewritten"],["kept","Kept original"],["fail","Failed"],["lost","Fact loss"],["pass0","No hits"]],
    origLabel: "Original reply",
    modelsLabel: "Model rewrites",
    hookRaw: "Raw hook feedback",
    pass0Text: "No hits, no rewrite needed",
    keptText: "Confirmed to keep original",
    noHit: "No hits",
    hitsCount: n => `${n} ${n===1?"hit":"hits"}`,
    caseCount: n => `${n} ${n===1?"case":"cases"}`,
    roundBlocked: n => `Round ${n} (still blocked)`,
    roundsCount: n => `${n} rounds`,
    lostBadge: n => `Lost ${n} fact${n===1?"":"s"}`,
    lostNote: "Lost: ",
    emptySearch: "No matching cases",
    emptyLangTitle: "No English rewrite comparison cases yet",
    eyebrow: (mCount, vCount, cCount) => `${mCount} models${vCount > mCount ? ` (${vCount} reasoning configs)` : ""} · ${cCount} ${cCount===1?"case":"cases"}`,
    footExtra: " · Fact retention checks numbers, backtick code spans, and quoted phrases",
    sumHeaders: ["Harness","Model","Effort","Blocked / Cases","Rewritten","Kept","Failed","Avg rounds","Fact retention","Cases w/ loss"],
  }
};
const urlLang = new URLSearchParams(location.search).get("lang");
let storedLang = null;
try { storedLang = localStorage.getItem("la-dictionary-lang"); } catch (e) {}
let lang = (urlLang === "en" || urlLang === "zh") ? urlLang : ((storedLang === "en" || storedLang === "zh") ? storedLang : "zh");
const ui = () => I18N[lang] || I18N.zh;
const langCases = () => D.cases.filter(c => (c.lang || "zh") === lang);
const hitTerms = id => {
  const r = firstRound(id);
  if (!r || !r.reason) return [];
  const zh = [...r.reason.matchAll(/■ 「(.+?)」（(.+?)）/g)].map(x => [x[1], x[2]]);
  const items = zh.length ? zh : [...r.reason.matchAll(/^■ "(.+?)" \((.+?)\)/gm)].map(x => [x[1], x[2]]);
  return items.filter(([w]) => w !== "spine");
};
const firstRound = id => { const m = D.models.find(m => m.rows[id]); return m ? m.rows[id].rounds[0] : null; };
const title = c => c.id.replace(/^[cd]\d+-/, "").replace(/-正当$/, "");
const GROUPS = [["典型","语料典型回复","Typical Corpus"],["高频","开发高频词","Frequent Dev Terms"],["正当","正当用法（应保留）","Valid Usage (Keep)"]];
const groupOf = c => c.id.includes("正当") || c.id.includes("应保留") ? "正当" : c.id.startsWith("c") ? "典型" : "高频";
const dotOf = (m, id) => { const r = m.rows[id]; if (!r) return "pass0"; return r.s.lost.length ? "lost" : r.s.status; };
const sts = c => D.models.map(m => m.rows[c.id] && m.rows[c.id].s).filter(Boolean);
const FILTERS = [
  ["all", ()=>true],
  ["typical", c=>groupOf(c)==="典型"],
  ["frequent", c=>groupOf(c)==="高频"],
  ["valid", c=>groupOf(c)==="正当"]
];
const sortCases = cs => [...cs].sort((a, b) => title(a).localeCompare(title(b), lang === "en" ? "en" : "zh-Hans-CN"));
let filter = "all"; const open = new Set();
const root = document.documentElement;
const reducedMotionMedia = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
const headerScrollProgress = document.getElementById("header-scroll-progress");
const motion = createMotion({ reducedMotionMedia, headerScrollProgress });
motion.bindHeaderScrollProgressFallbackScroll();
motion.bindReducedMotionHeaderSync();
const {
  runElementAnimation,
  clearAnimationInlineProps,
  updateHeaderScrollProgressFallback,
  syncHeaderScrollProgressDriver,
  animateEntryPanelToggle,
  animateChapterPush
} = motion;
const caseById = id => D.cases.find(c => c.id === id);
const scheduleRender = createRafBatcher(() => render());
const effortRank = e => ({minimal:0,low:1,medium:2,high:3,xhigh:4}[e] ?? 9);
const MGROUPS = [];
{
  const mMap = new Map();
  D.models.forEach(m => {
    const key = `${m.harness}::${m.model}`;
    if (!mMap.has(key)) { const g = { key, harness: m.harness, model: m.model, variants: [] }; mMap.set(key, g); MGROUPS.push(g); }
    mMap.get(key).variants.push(m);
  });
  MGROUPS.forEach(g => g.variants.sort((a,b) => effortRank(a.effort) - effortRank(b.effort)));
}
const selectedEffort = new Map();
const selectedModel = new Map();
const HARNESS_ICONS = __HARNESS_ICONS__;
const hIcon = h => HARNESS_ICONS[h] || "";
function activeModelGroups(c) {
  return MGROUPS.filter(g => {
    const m = getVariant(g, c.id);
    return m && m.rows[c.id];
  });
}
function getSelectedModelGroup(c) {
  const groups = activeModelGroups(c);
  if (!groups.length) return null;
  const saved = selectedModel.get(c.id);
  return groups.find(g => g.key === saved) || groups[0];
}
function buildModelTabs(c, activeKey) {
  const groups = activeModelGroups(c);
  return `<div class="model-tabs" role="tablist" aria-label="Models">${groups.map(g => {
    const m = getVariant(g, c.id);
    const d = dotOf(m, c.id);
    const warnDot = (d === "fail" || d === "lost") ? `<i class="model-tab-dot ${d}" aria-hidden="true"></i>` : "";
    return `<button type="button" class="model-tab" data-case="${esc(c.id)}" data-mkey="${esc(g.key)}" aria-pressed="${g.key === activeKey}" title="${esc(g.harness)} · ${esc(g.model)}">${hIcon(g.harness)}<span>${esc(g.model)}</span>${warnDot}</button>`;
  }).join("")}</div>`;
}
function rowSummaryHtml(c) {
  let ok = 0, fail = 0, lost = 0, total = 0;
  MGROUPS.forEach(g => {
    const m = getVariant(g, c.id);
    const r = m && m.rows[c.id];
    if (!r) return;
    total++;
    const s = r.s;
    if (s.lost.length) lost++;
    if (s.status === "fail") fail++;
    else if (!s.lost.length) ok++;
  });
  const isEn = lang === "en";
  if (fail > 0) {
    return `<span class="row-summary row-summary--fail">${ok}/${total} ${isEn ? "pass" : "通过"} · ${fail} ${isEn ? "fail" : "未过"}</span>`;
  }
  if (lost > 0) {
    return `<span class="row-summary row-summary--warn">${ok}/${total} ${isEn ? "pass" : "通过"} · ${lost} ${isEn ? "fact loss" : "丢事实"}</span>`;
  }
  return `<span class="row-summary row-summary--ok">${ok}/${total} ${isEn ? "pass" : "通过"}</span>`;
}
const getVariant = (g, caseId) => {
  if (g.variants.length === 1) return g.variants[0];
  const def = (g.variants.find(v => v.effort === "medium") || g.variants[g.variants.length - 1]).effort;
  const eff = selectedEffort.get(`${caseId}::${g.key}`) || def;
  return g.variants.find(v => v.effort === eff) || g.variants[0];
};

function modelResult(c, g){
  const m = getVariant(g, c.id);
  return { m, r: m.rows[c.id] };
}
function buildEffortTabs(c, g, activeEffort){
  return `<div class="effort-tabs"${g.variants.length>1?` role="group" aria-label="推理强度"`:""}>${g.variants.map(x => g.variants.length > 1
    ? `<button type="button" class="effort-tab" data-case="${esc(c.id)}" data-mkey="${esc(g.key)}" data-eff="${esc(x.effort)}" aria-pressed="${x.effort===activeEffort}"><i class="dot ${dotOf(x,c.id)}"></i>${esc(x.effort)}</button>`
    : `<span class="effort-tab"><i class="dot ${dotOf(x,c.id)}"></i>${esc(x.effort)}</span>`).join("")}</div>`;
}
function buildCommunityItemChrome(c, g){
  const { m } = modelResult(c, g);
  if (!m.rows[c.id]) return "";
  return `<div class="model-line model-line--chrome"><span class="model-head"><span class="model-name">${esc(m.model)}</span>${buildEffortTabs(c, g, m.effort)}</span><span class="model-meta model-meta--stable">${hIcon(m.harness)}<span>${esc(m.harness)}</span></span></div>`;
}
function buildCommunityItemSlide(c, g){
  const t = ui(), hits = hitTerms(c.id), words = hits.map(h=>h[0]);
  const { m, r } = modelResult(c, g);
  if (!r) return "";
  const s = r.s, last = r.rounds[r.rounds.length-1];
  const same = s.status === "kept" || s.status === "pass0";
  const body = s.status === "pass0" ? t.pass0Text : s.status === "kept" ? t.keptText : s.status === "fixed" ? hlRewrite(c.reply, last.text, words) : hl(last.text, words);
  const mid = r.rounds.slice(1,-1).map(x=>`<details><summary>${t.roundBlocked(x.round)}</summary><pre>${esc(x.text)}\n\n—— hook ——\n${esc(x.reason)}</pre></details>`).join("");
  const statusEl = s.lost.length ? `<span class="local-badge">${t.lostBadge(s.lost.length)}</span>` : `<span class="status-text status-text--${s.status}">${t.stxt[s.status]}</span>`;
  const roundEl = s.rounds > 1 ? `<span>${t.roundsCount(s.rounds)}</span>` : "";
  return `<div class="community-item-slide-meta">${roundEl}${statusEl}</div>
    <div class="community-item-text${same?" is-same":""}">${body}</div>${s.lost.length?`<div class="community-item-note">${t.lostNote}${esc(s.lost.join("  "))}</div>`:""}${mid}`;
}
function buildCommunityItem(c, g){
  const chrome = buildCommunityItemChrome(c, g);
  const slide = buildCommunityItemSlide(c, g);
  if (!chrome || !slide) return "";
  return `<li class="community-item" data-mkey="${esc(g.key)}"><div class="community-item-main">${chrome}<div class="community-item-chapter-viewport"><div class="community-item-chapter-layer">${slide}</div></div></div></li>`;
}
function patchCommunityItemChrome(item, c, g){
  const { m } = modelResult(c, g);
  if (!m.rows[c.id]) return;
  const tabs = item.querySelector(".effort-tabs");
  if (tabs) tabs.outerHTML = buildEffortTabs(c, g, m.effort);
}
function buildEntryPanel(c){
  const t = ui(), hits = hitTerms(c.id), words = hits.map(h=>h[0]), r0 = firstRound(c.id);
  let h = `<div class="orig-col"><div class="detail-label">${t.origLabel}</div><div class="suggest-box"><div class="reply-text">${hl(c.reply, words)}</div>
    ${hits.length?`<div class="hit-badges">${hits.map(([w,l])=>`<span class="level-badge" data-level="${LV[l]||2}">${esc(w)} · ${esc(l)}</span>`).join("")}</div>`:""}</div>
    ${r0&&r0.reason?`<details><summary>${t.hookRaw}</summary><pre>${esc(r0.reason)}</pre></details>`:""}</div>
    <div class="models-col"><div class="detail-label">${t.modelsLabel}</div>`;
  const selG = getSelectedModelGroup(c);
  if (selG) {
    h += buildModelTabs(c, selG.key) + `<ul class="community-list">${buildCommunityItem(c, selG)}</ul>`;
  }
  return h + "</div>";
}
function applyLocaleChrome() {
  const t = ui(), activeCases = langCases(), hasCases = activeCases.length > 0;
  root.setAttribute("lang", t.htmlLang);
  document.title = t.docTitle;
  const homeHref = `../?lang=${encodeURIComponent(lang)}`;
  const brandLink = document.getElementById("brand-home-link");
  const backBtn = document.getElementById("back-home-btn");
  if (brandLink) { brandLink.href = homeHref; brandLink.setAttribute("aria-label", t.brandAria); }
  if (backBtn) backBtn.href = homeHref;
  document.getElementById("back-home-label").textContent = t.backHome;
  document.getElementById("summary-nav-label").textContent = t.summaryNav;
  document.getElementById("summary-nav-btn").hidden = !hasCases;
  document.getElementById("hero-title").textContent = t.heroTitle;
  document.getElementById("q").placeholder = t.searchPlaceholder;
  document.getElementById("search-bar").hidden = !hasCases;
  document.getElementById("level-toolbar").hidden = !hasCases;
  document.getElementById("summary").hidden = !hasCases;
  document.getElementById("summary-title").textContent = t.summaryTitle;
  document.getElementById("summary-sub").textContent = t.summarySub;
  document.getElementById("foot-src").textContent = t.footSrc;
  const sw = document.getElementById("lang-switch");
  if (sw) {
    sw.dataset.active = lang;
    sw.querySelectorAll(".lang-btn").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  }
  const meta = t.eyebrow(MGROUPS.length, D.models.length, activeCases.length);
  document.getElementById("eyebrow").textContent = meta;
  document.getElementById("foot-meta").textContent = meta + (hasCases ? t.footExtra : "");
  renderSummary(activeCases);
}
function render(){
  const t = ui(), activeCases = langCases();
  if (!activeCases.length) {
    document.getElementById("groups").innerHTML = `<div class="empty-state"><h2>${t.emptyLangTitle}</h2><div class="empty-actions"><a class="btn" href="../?lang=${encodeURIComponent(lang)}">${t.backHome}</a></div></div>`;
    updateHeaderScrollProgressFallback();
    return;
  }
  const q = document.getElementById("q").value.trim(), f = FILTERS.find(x=>x[0]===filter)[1];
  const shown = activeCases.filter(c => f(c) && (!q || c.id.includes(q) || c.reply.includes(q) || c.user.includes(q)));
  let html = "";
  GROUPS.forEach(([g, zhName, enName]) => { const cs = sortCases(shown.filter(c => groupOf(c) === g)); if (!cs.length) return;
    const name = lang === "en" ? enName : zhName;
    html += `<section class="letter-group"><div class="letter-header"><h2 class="letter-char">${lang==="en"?enName:g}</h2>${lang==="en"?"":`<span class="letter-sub">${name}</span>`}<span class="letter-count">${t.caseCount(cs.length)}</span></div>`;
    cs.forEach(c => { const isOpen = open.has(c.id), hits = hitTerms(c.id);
      const lv = hits.length ? Math.min(...hits.map(h=>LV[h[1]]||2)) : 0;
      html += `<div class="entry-row" id="${esc(c.id)}"><button type="button" class="entry-trigger" data-id="${esc(c.id)}" aria-expanded="${isOpen}">
        <span class="entry-head"><span class="entry-term">${esc(title(c))}</span></span><span class="entry-why">${esc(c.user)}</span>
        <span class="entry-meta-end">${rowSummaryHtml(c)}
        ${lv?`<span class="level-badge" data-level="${lv}">${t.hitsCount(hits.length)}</span>`:`<span class="level-badge" data-level="3">${t.noHit}</span>`}
        <svg class="od-icon entry-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></span></button>
        <div class="entry-panel"${panelHiddenAttr(isOpen)}>${buildEntryPanel(c)}</div></div>`; });
    html += "</section>"; });
  document.getElementById("groups").innerHTML = html || `<div class="empty-state">${t.emptySearch}</div>`;
  document.getElementById("filters").innerHTML = FILTERS.map(([k,fn], idx) => `<button type="button" class="filter-pill" data-f="${k}" aria-pressed="${k===filter}"><span>${t.filters[idx][1]}</span><span class="filter-count">${activeCases.filter(fn).length}</span></button>`).join("");
  updateHeaderScrollProgressFallback();
}
function refreshRowDots(caseId) {
  const c = caseById(caseId);
  const row = document.getElementById(caseId);
  if (!c || !row) return;
  const sumEl = row.querySelector(".row-summary");
  if (!sumEl) return;
  sumEl.outerHTML = rowSummaryHtml(c);
}
function refreshEffortVariant(caseId, mkey, prevEff, nextEff) {
  const c = caseById(caseId);
  const row = document.getElementById(caseId);
  if (!c || !row) return;
  refreshRowDots(caseId);
  const item = row.querySelector(`.community-item[data-mkey="${CSS.escape(mkey)}"]`);
  if (!item) return;
  const g = MGROUPS.find(x => x.key === mkey);
  if (!g) return;
  const nextSlide = buildCommunityItemSlide(c, g);
  if (!nextSlide) return;
  const layer = item.querySelector(".community-item-chapter-layer");
  const viewport = item.querySelector(".community-item-chapter-viewport");
  if (!layer || !viewport) return;
  patchCommunityItemChrome(item, c, g);
  const mTabs = row.querySelector(".model-tabs");
  if (mTabs) mTabs.outerHTML = buildModelTabs(c, mkey);
  let direction = 1;
  if (prevEff && nextEff && prevEff !== nextEff) {
    const delta = effortRank(nextEff) - effortRank(prevEff);
    if (delta !== 0) direction = delta > 0 ? 1 : -1;
  }
  animateChapterPush(layer, () => {
    layer.innerHTML = nextSlide;
    return layer;
  }, direction, { swappingClass: "is-chapter-push", viewport });
}
function toggleEntry(id, trigger) {
  const row = trigger.closest(".entry-row");
  const panel = row?.querySelector(".entry-panel");
  const c = caseById(id);
  if (!panel || !c) return;
  const nextOpen = !open.has(id);
  if (nextOpen) open.add(id); else open.delete(id);
  try { history.replaceState(null, "", nextOpen ? "#" + encodeURIComponent(id) : location.pathname); } catch (err) {}
  if (nextOpen) {
    if (!panel.innerHTML.trim()) panel.innerHTML = buildEntryPanel(c);
    animateEntryPanelToggle(panel, trigger, true);
  } else {
    animateEntryPanelToggle(panel, trigger, false);
  }
}
document.getElementById("groups").addEventListener("click", e => {
  const b = e.target.closest(".entry-trigger");
  if (b) { e.preventDefault(); toggleEntry(b.dataset.id, b); return; }
  const mt = e.target.closest("button.model-tab");
  if (mt && mt.dataset.case && mt.dataset.mkey) {
    const cid = mt.dataset.case, nextKey = mt.dataset.mkey;
    const c = caseById(cid);
    const row = document.getElementById(cid);
    if (!c || !row) return;
    selectedModel.set(cid, nextKey);
    const g = MGROUPS.find(x => x.key === nextKey);
    if (!g) return;
    const mCol = row.querySelector(".models-col");
    if (mCol) {
      const tEl = mCol.querySelector(".model-tabs");
      if (tEl) tEl.outerHTML = buildModelTabs(c, nextKey);
      const list = mCol.querySelector(".community-list");
      if (list) list.innerHTML = buildCommunityItem(c, g);
    }
    return;
  }
  const t = e.target.closest("button.effort-tab");
  if (!t || !t.dataset.case) return;
  const effortGroup = MGROUPS.find(x => x.key === t.dataset.mkey);
  const prevEff = effortGroup ? getVariant(effortGroup, t.dataset.case).effort : t.dataset.eff;
  const nextEff = t.dataset.eff;
  if (prevEff === nextEff) return;
  selectedEffort.set(`${t.dataset.case}::${t.dataset.mkey}`, nextEff);
  refreshEffortVariant(t.dataset.case, t.dataset.mkey, prevEff, nextEff);
});
document.getElementById("groups").addEventListener("beforematch", e => {
  const panel = e.target?.closest?.(".entry-panel");
  if (!panel) return;
  const row = panel.closest(".entry-row");
  const trigger = row?.querySelector(".entry-trigger");
  const id = trigger?.dataset?.id;
  if (!id) return;
  open.add(id);
  trigger.setAttribute("aria-expanded", "true");
  panel.classList.remove("is-animating");
  clearAnimationInlineProps(panel, ["height", "opacity", "transform"]);
  if (!panel.innerHTML.trim()) {
    const c = caseById(id);
    if (c) panel.innerHTML = buildEntryPanel(c);
  }
});
document.getElementById("filters").addEventListener("click", e => { const b = e.target.closest("[data-f]"); if (b) { filter = b.dataset.f; render(); } });
document.getElementById("q").addEventListener("input", scheduleRender);
function sumRow(m, idx, span, allowedIds){
  const rows = Object.entries(m.rows).filter(([id]) => allowedIds.has(id)).map(([,r]) => r);
  const hit = rows.filter(r => r.s.status !== "pass0"), c = k => hit.filter(r => r.s.status === k).length;
  const nf = hit.reduce((a,r)=>a+r.s.nfacts,0), nl = hit.reduce((a,r)=>a+r.s.lost.length,0);
  const avg = hit.length ? (hit.reduce((a,r)=>a+r.s.rounds,0)/hit.length).toFixed(2) : "-";
  const head = idx === 0 ? `<td rowspan="${span}"><span class="harness-cell">${hIcon(m.harness)}<span>${esc(m.harness)}</span></span></td><td rowspan="${span}"><b>${esc(m.model)}</b></td>` : "";
  return `<tr>${head}<td>${m.effort}</td><td class="num">${hit.length}/${rows.length}</td>
  <td class="num c-fixed">${c("fixed")}</td><td class="num c-kept">${c("kept")}</td><td class="num c-fail">${c("fail")}</td><td class="num">${avg}</td>
  <td class="num">${nf?((1-nl/nf)*100).toFixed(1)+"%":"-"}</td><td class="num">${hit.filter(r=>r.s.lost.length).length}</td></tr>`;
}
function renderSummary(activeCases) {
  const allowedIds = new Set(activeCases.map(c => c.id));
  const hdrs = ui().sumHeaders.map(h => `<th>${h}</th>`).join("");
  document.getElementById("sumtab").innerHTML = `<tr>${hdrs}</tr>` + MGROUPS.flatMap(g => g.variants.map((m, i) => sumRow(m, i, g.variants.length, allowedIds))).join("");
}
function switchLang(nextLang) {
  if (!I18N[nextLang] || nextLang === lang) return;
  lang = nextLang;
  filter = "all";
  try { localStorage.setItem("la-dictionary-lang", lang); } catch (e) {}
  try {
    const u = new URL(location.href);
    u.searchParams.set("lang", lang);
    history.replaceState(null, "", u.pathname + u.search + u.hash);
  } catch (e) {}
  applyLocaleChrome();
  render();
}
document.getElementById("lang-switch").addEventListener("click", e => {
  const b = e.target.closest(".lang-btn");
  if (b && b.dataset.lang) switchLang(b.dataset.lang);
});
const themeToggle = document.getElementById("theme-toggle");
const themeIcon = themeToggle.querySelector("svg");
const renderThemeToggle = (animateIcon = false) => {
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  themeToggle.setAttribute("aria-pressed", dark ? "true" : "false");
  themeToggle.setAttribute("aria-label", dark ? ui().themeLight : ui().themeDark);
  if (animateIcon && themeIcon) {
    runElementAnimation(themeIcon, { rotate: [-28, 0], scale: [0.82, 1], opacity: [0.45, 1] }, { spring: true, duration: 0.32, clearProps: ["opacity", "transform"] });
  }
};
try { const t = localStorage.getItem("replay-theme") || localStorage.getItem("la-dictionary-theme"); if (t) root.dataset.theme = t; } catch (e) {}
renderThemeToggle();
themeToggle.addEventListener("click", () => {
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("replay-theme", root.dataset.theme); } catch (e) {}
  renderThemeToggle(true);
});
const fromHash = decodeURIComponent(location.hash.slice(1));
const initCases = langCases();
if (initCases.length) {
  const firstOrdered = GROUPS.flatMap(([g]) => sortCases(initCases.filter(c => groupOf(c) === g)))[0] || initCases[0];
  open.add(initCases.some(c => c.id === fromHash) ? fromHash : firstOrdered.id);
}
syncHeaderScrollProgressDriver();
applyLocaleChrome();
render();
if (fromHash) document.getElementById(fromHash)?.scrollIntoView({block:"start"});
</script></html>"""
def visible_term_counts(rules):
    """介绍页和词典共用的词条数：只数 level 1、2、3。level 0 是放行词，不计入。"""
    counts = {}
    for rule in rules:
        if rule["level"] not in (1, 2, 3):
            continue
        lang = rule["lang"]
        counts[lang] = counts.get(lang, 0) + 1
    return counts


def case_snippet(case, limit=18):
    first = next((line.strip() for line in (case.get("reply") or "").splitlines() if line.strip()), "")
    plain = first.replace("`", "")
    if len(plain) > limit:
        return plain[:limit - 1] + "…"
    return plain or case.get("id", "")


def intro_data(data, lang="zh"):
    """发布页 /intro/ 用的测试数据：词条数、用例数和全量回放统计。"""
    cases = [c for c in data["cases"] if (c.get("lang") or "zh") == lang]
    by_cid = {c["id"]: c for c in cases}
    hit_pairs = [
        (by_cid[cid], r)
        for m in data["models"]
        for cid, r in m["rows"].items()
        if cid in by_cid and r["s"]["status"] != "pass0"
    ]
    total_hits = 0
    cleared_hits = 0
    len_deltas = []
    neg_deltas = []
    pos_deltas = []
    len_diffs = []
    shorter_count = 0
    for case, row in hit_pairs:
        if case.get("keep"):
            continue
        summary = row["s"]
        total_hits += len(summary["hits"])
        cleared_hits += len(summary["hits"]) - len(summary["residual"])
        rounds = row.get("rounds") or []
        orig_len = len(case.get("reply") or "")
        if summary["status"] == "fixed" and orig_len > 0 and rounds:
            after_len = len(rounds[-1].get("text") or "")
            diff = after_len - orig_len
            delta = diff / orig_len
            len_deltas.append(delta)
            len_diffs.append(diff)
            if diff < 0:
                shorter_count += 1
                neg_deltas.append(delta)
            elif diff > 0:
                pos_deltas.append(delta)
    len_deltas.sort()
    neg_deltas.sort()
    pos_deltas.sort()
    len_diffs.sort()

    def quantile(vals, q):
        if not vals:
            return None
        return vals[min(len(vals) - 1, int(q * (len(vals) - 1)))]

    model_names = []
    seen_models = set()
    harness_names = []
    seen_harnesses = set()
    for m in data["models"]:
        harness = m.get("harness")
        model = m.get("model") or m.get("key")
        pair = (harness, model)
        if pair not in seen_models:
            seen_models.add(pair)
            model_names.append(model)
        if harness and harness not in seen_harnesses:
            seen_harnesses.add(harness)
            harness_names.append(harness)
    model_names.sort(key=str.lower)
    harness_names.sort(key=str.lower)
    return {
        "terms": data["termCounts"].get(lang, 0),
        "cases": len(cases),
        "keepCases": sum(1 for c in cases if c.get("keep")),
        "models": len(model_names),
        "harnesses": len(harness_names),
        "modelNames": model_names,
        "harnessNames": harness_names,
        "caseSnippets": [case_snippet(c) for c in cases],
        "clearRate": cleared_hits / total_hits if total_hits else None,
        "lenDeltaNegP50": round(quantile(neg_deltas, 0.50), 4) if neg_deltas else None,
        "lenDeltaP50": round(quantile(len_deltas, 0.50), 4) if len_deltas else None,
        "lenDeltaPosP50": round(quantile(pos_deltas, 0.50), 4) if pos_deltas else None,
        "lenDiffP50": quantile(len_diffs, 0.50) if len_diffs else None,
        "shorterRate": round(shorter_count / len(len_deltas), 4) if len_deltas else None,
    }

def load_harness_icons():
    icon_map = {
        "Antigravity CLI": ("antigravity.svg", "img"),
        "Claude Code": ("claude.svg", "img"),
        "Codex CLI": ("openai.svg", "inline"),
        "Cursor Agent": ("cursor.svg", "inline"),
        "DeepSeek Harness": ("deepseek.svg", "img"),
        "Grok CLI": ("grok.svg", "inline"),
    }
    out = {}
    icons_dir = HERE / "icons"
    for harness, (fname, mode) in icon_map.items():
        p = icons_dir / fname
        if not p.exists():
            continue
        raw = p.read_text(encoding="utf-8").strip()
        if mode == "img":
            b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
            out[harness] = f'<img class="harness-icon" src="data:image/svg+xml;base64,{b64}" alt="" aria-hidden="true">'
        else:
            cleaned = re.sub(r"<title>.*?</title>", "", raw, flags=re.S)
            cleaned = cleaned.replace("<svg ", '<svg class="harness-icon" aria-hidden="true" ', 1)
            out[harness] = cleaned
    return out


def main(cases_path=HERE / "cases.json", out_dir=HERE.parent / "docs" / "replay"):
    cases = json.load(open(cases_path))
    term_counts = visible_term_counts(scan.load_rules())
    data = {"cases": cases, "models": [], "termCounts": term_counts}
    for key, (harness, model, effort, _) in BACKENDS.items():
        p = HERE / "results" / f"{key}.json"
        if not p.exists():
            continue
        res = {r["id"]: r for r in json.load(open(p))}
        rows = {c["id"]: {**res[c["id"]], "s": summarize(c, res[c["id"]])} for c in cases if c["id"] in res}
        data["models"].append({"key": key, "harness": harness, "model": model, "effort": effort, "rows": rows})

    brand_mark_path = HERE.parent / "web" / "src" / "brand-mark-default.svg"
    brand_mark_html = brand_mark_path.read_text(encoding="utf-8").strip().replace("\n", " ")
    brand_mark_html = re.sub(r"<title[^>]*>.*?</title>", "", brand_mark_html, flags=re.I | re.S)
    brand_mark_html = re.sub(r'\s+(?:role|aria-labelledby)="[^"]*"', "", brand_mark_html)
    if 'aria-hidden=' not in brand_mark_html:
        brand_mark_html = brand_mark_html.replace("<svg ", '<svg aria-hidden="true" ', 1)
    html = (
        page.replace("__BRAND_MARK__", brand_mark_html)
        .replace("__HARNESS_ICONS__", json.dumps(load_harness_icons(), ensure_ascii=False).replace("</", "<\\/"))
        .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    )
    site_dir = pathlib.Path(out_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    motion_src = HERE.parent / "web" / "src" / "motion.js"
    motion_text = motion_src.read_text(encoding="utf-8")
    (site_dir / "result.html").write_text(html, encoding="utf-8")
    (site_dir / "motion.js").write_text(motion_text, encoding="utf-8")
    (site_dir / "intro.json").write_text(
        json.dumps(intro_data(data), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("models:", [m["key"] for m in data["models"]])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=pathlib.Path, default=HERE / "cases.json", help="用例文件路径")
    ap.add_argument("--out", type=pathlib.Path, default=HERE.parent / "docs" / "replay", help="输出目录")
    args = ap.parse_args()
    main(cases_path=args.cases, out_dir=args.out)
