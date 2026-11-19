import { Suspense, lazy, useEffect, useState } from 'react';
import markup from './markup.html?raw';
import { initDictionaryApp } from './dictionaryApp.js';
import defaultBrandMark from './brand-mark-default.svg?raw';

const LogoPreview = lazy(() => import('./previews/LogoPreview.jsx'));
const LanguagePreview = lazy(() => import('./previews/LanguagePreview.jsx'));
const MultilingualPreview = lazy(() => import('./previews/MultilingualPreview.jsx'));

const searchParams = new URLSearchParams(window.location.search);
const logoVariant = searchParams.get('logo');
const languagePreview = searchParams.get('preview') === 'language';
const languageStyle = searchParams.get('lang-style');
const multilingualPreview = searchParams.get('preview') === 'multilingual';
const finalLogo = defaultBrandMark.trim();

async function resolveBrandMark(variant) {
  if (!variant || variant === 'default') return finalLogo;
  if (variant === 'classic') {
    const mod = await import('./previews/classicLogo.svg?raw');
    return mod.default.trim();
  }
  if (variant === 'flow') {
    const mod = await import('./previews/logo-flow.svg?raw');
    return mod.default.trim();
  }
  const { logoCandidates } = await import('./previews/logoCandidates.js');
  return logoCandidates.find((candidate) => candidate.key === variant)?.logo ?? finalLogo;
}

export default function App() {
  const [selectedLogo, setSelectedLogo] = useState(
    !logoVariant || logoVariant === 'default' ? finalLogo : ''
  );
  const [classicLogo, setClassicLogo] = useState('');

  useEffect(() => {
    if (logoVariant === 'compare') {
      import('./previews/classicLogo.svg?raw').then((mod) => setClassicLogo(mod.default.trim()));
      return;
    }
    if (logoVariant && logoVariant !== 'default') {
      resolveBrandMark(logoVariant).then(setSelectedLogo);
    }
  }, []);

  useEffect(() => {
    if (logoVariant !== 'compare' && !languagePreview && !multilingualPreview && selectedLogo) {
      initDictionaryApp();
    }
  }, [selectedLogo]);

  if (multilingualPreview) {
    return (
      <Suspense fallback={null}>
        <MultilingualPreview />
      </Suspense>
    );
  }
  if (languagePreview) {
    return (
      <Suspense fallback={null}>
        <LanguagePreview />
      </Suspense>
    );
  }
  if (logoVariant === 'compare') {
    return (
      <Suspense fallback={null}>
        {classicLogo ? <LogoPreview classicLogo={classicLogo} /> : null}
      </Suspense>
    );
  }

  const pageMarkup = markup.replace('<!--BRAND_MARK-->', selectedLogo || finalLogo);

  return (
    <div
      id="app-shell"
      data-language-style={languageStyle}
      style={{ display: 'contents' }}
      dangerouslySetInnerHTML={{ __html: pageMarkup }}
    />
  );
}
