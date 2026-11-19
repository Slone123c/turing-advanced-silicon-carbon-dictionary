import { useState } from 'react';
import './languagePreview.css';

const options = [
  { key: 'current', name: '当前滑块', label: '首页现状', description: '黑色滑块明确标出当前语言，圆角与页面现有按钮一致。' },
  { key: 'tabs', name: '词典页签', label: '推荐方向', description: '收起外框，用蓝色短线标记当前词典，呼应字母索引与像素引号。' },
  { key: 'refined', name: '轻框滑块', label: '保留熟悉的操作', description: '减淡外框和底色，保留黑色滑块，增大点击区域，让控件更舒展。' },
  { key: 'minimal', name: '排印切换', label: '最轻的表达', description: '以字重与颜色区分当前语言，去掉容器，让标题和搜索更突出。' },
];

function LanguageSwitch({ variant, language, onChange, name }) {
  return (
    <div className={`language-style-${variant}`}>
      <div className="lang-switch is-ready" data-active={language} role="group" aria-label={`${name}：切换词典语言`}>
        <span className="lang-switch-thumb" aria-hidden="true" />
        <button type="button" className="lang-btn" aria-pressed={language === 'zh'} onClick={() => onChange('zh')}>中文</button>
        <button type="button" className="lang-btn" aria-pressed={language === 'en'} onClick={() => onChange('en')}>English</button>
      </div>
    </div>
  );
}

export default function LanguagePreview() {
  const [language, setLanguage] = useState('zh');
  const [dark, setDark] = useState(false);
  const english = language === 'en';

  return (
    <main className="language-study" data-theme={dark ? 'dark' : 'light'}>
      <div className="language-study-shell">
        <nav className="language-study-nav" aria-label="语言切换设计预览">
          <a href="?">返回词典</a>
          <button type="button" aria-pressed={dark} onClick={() => setDark(!dark)}>{dark ? '切换浅色' : '切换深色'}</button>
        </nav>
        <h1>选语言，也像翻开一本词典。</h1>
        <p className="language-study-intro">当前样式与三个新方向并排比较。点击任一语言按钮，四版同步切换；也可以放进完整词典，查看实际效果。</p>
        <a className="language-study-preview-link" href="?preview=multilingual">如果有十种语言？查看可搜索的选择器 <span aria-hidden="true">↗</span></a>
        <div className="language-study-grid">
          {options.map(option => (
            <section className="language-study-option" key={option.key}>
              <div className="language-study-option-heading"><h2>{option.name}</h2><span>{option.label}</span></div>
              <div className="language-study-sample">
                <LanguageSwitch variant={option.key} language={language} onChange={setLanguage} name={option.name} />
                <h3 lang={english ? 'en' : 'zh-CN'}>{english ? 'Turing Silicon–Carbon Dictionary' : '图灵高阶硅碳词典'}</h3>
                <div className="language-study-search" lang={english ? 'en' : 'zh-CN'}>
                  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
                  <span>{english ? 'Search terms, aliases or descriptions' : '搜索词语、拼音、别名或说明'}</span>
                </div>
              </div>
              <p className="language-study-description">{option.description}</p>
              <a className="language-study-preview-link" href={option.key === 'current' ? '?' : `?lang-style=${option.key}`}>在完整词典中预览 <span aria-hidden="true">↗</span></a>
            </section>
          ))}
        </div>
        <p className="language-study-note" role="status">当前预览：{english ? 'English' : '中文'}。首页样式保持原样。新方案暂不显示尚未提供语言列表的“＋更多”。</p>
      </div>
    </main>
  );
}
