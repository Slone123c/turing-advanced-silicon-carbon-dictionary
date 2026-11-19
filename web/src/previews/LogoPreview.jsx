import { useState } from 'react';
import flowLogo from './logo-flow.svg?raw';
import { logoCandidates } from './logoCandidates.js';

function logoInstance(logo, instance) {
  return logo.replaceAll('brand-flow-title', `brand-${instance}-title`).replaceAll('brand-mark-title', `brand-${instance}-title`);
}

function LogoOption({ option }) {
  return (
    <article className="logo-study-option">
      <div className="logo-study-label"><h2>{option.name}</h2><span>{option.label}</span></div>
      <div className="logo-study-art" dangerouslySetInnerHTML={{ __html: logoInstance(option.logo, `${option.key}-large`) }} />
      <p>{option.description}</p>
      {option.detail && <p className="logo-study-detail">{option.detail}</p>}
      <div className="logo-study-lockup">
        <div className="brand"><span dangerouslySetInnerHTML={{ __html: logoInstance(option.logo, `${option.key}-small`) }} /><span className="brand-title">Turing</span></div>
        <span>页面实际尺寸</span>
      </div>
      <a className="logo-study-link" href={option.key === 'pixel' ? '?' : `?logo=${option.key}`}>放进词典看看 <span aria-hidden="true">↗</span></a>
    </article>
  );
}

export default function LogoPreview({ classicLogo }) {
  const [dark, setDark] = useState(false);

  return (
    <main className="logo-study" data-theme={dark ? 'dark' : 'light'}>
      <div className="logo-study-shell">
        <nav className="logo-study-nav" aria-label="标识预览导航">
          <a href="?">返回词典</a>
          <button type="button" onClick={() => setDark(!dark)} aria-pressed={dark}>
            {dark ? '切换浅色' : '切换深色'}
          </button>
        </nav>
        <h1>像素引号，定稿。</h1>
        <p className="logo-study-intro">首页已采用“像素引号”：以圆润与离散的两组引号，表达人类语言与 AI 语言的双向转译。其他设计保留在这里，作为探索记录。</p>
        <div className="logo-study-grid">
          {logoCandidates.map(option => <LogoOption key={option.key} option={option} />)}
        </div>
        <h2 className="logo-study-saved-title">之前的两个版本，也都保留。</h2>
        <div className="logo-study-grid">
          <LogoOption option={{ key: 'classic', name: '交叠对话', label: '早期版本', logo: classicLogo, description: '圆润的引号与利落的代码气泡，交叠成语言之间的桥。' }} />
          <LogoOption option={{ key: 'flow', name: '流动互译', label: '上一版', logo: flowLogo, description: '两道相向的回旋箭头，让自然语言与 AI 语言彼此接续。' }} />
        </div>
        <p className="logo-study-note">每版都展示放大图与页面实际尺寸，支持深浅色预览。系统开启减少动态效果时，标识自动静止。</p>
      </div>
    </main>
  );
}
