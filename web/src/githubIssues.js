export function buildGithubIssueUrl(repo, title, body, labels) {
  const params = new URLSearchParams();
  params.set('title', title);
  params.set('body', body);
  if (labels) params.set('labels', labels);
  return `https://github.com/${repo}/issues/new?${params.toString()}`;
}

export function buildSuggestIssuePayload(lang, ui, term, item, submission) {
  const isEn = lang === 'en';

  if (submission.mode === 'structured' && submission.structured) {
    const s = submission.structured;
    const levelLabel = ui.levels[s.level] || String(s.level);
    const title = isEn
      ? `[Suggest · Structured] Update entry "${term}"`
      : `[补充词条 · 有格式] 完善「${term}」的词条内容`;
    const jsonSnippet = JSON.stringify(
      {
        term,
        level: s.level,
        why: s.why,
        suggest: s.suggest,
        ...(s.ok ? { ok: s.ok } : {}),
        ...(s.bad ? { bad: s.bad } : {}),
        ...(s.alias ? { alias: s.alias } : {})
      },
      null,
      2
    );
    const lines = isEn
      ? [
          '### Term',
          `- **Term**: ${term}`,
          '- **Language**: English',
          '- **Mode**: Structured format',
          '',
          '### Proposed dictionary entry',
          `- **Level**: ${levelLabel}`,
          `- **Why it is vague**: ${s.why}`,
          `- **Use instead**: ${s.suggest}`,
          ...(s.ok ? [`- **Keep when**: ${s.ok}`] : []),
          ...(s.bad ? [`- **Rewrite when**: ${s.bad}`] : []),
          ...(s.alias ? [`- **Aliases**: ${s.alias}`] : []),
          '',
          '```json',
          jsonSnippet,
          '```'
        ]
      : [
          '### 词条信息',
          `- **词条**：${term}`,
          '- **语言**：中文',
          '- **投稿模式**：有格式模式（按词典词条结构修改）',
          '',
          '### 建议更新后的词条字段',
          `- **建议级别**：${levelLabel}`,
          `- **为什么含糊**：${s.why}`,
          `- **建议改成**：${s.suggest}`,
          ...(s.ok ? [`- **可以保留**：${s.ok}`] : []),
          ...(s.bad ? [`- **需要改写**：${s.bad}`] : []),
          ...(s.alias ? [`- **别名**：${s.alias}`] : []),
          '',
          '```json',
          jsonSnippet,
          '```'
        ];
    const body = lines.join('\n');
    return { title, body, markdown: `# ${title}\n\n${body}` };
  }

  const title = isEn
    ? `[Suggest · Freeform] Better explanation for "${term}"`
    : `[补充说明 · 自由模式] 为「${term}」提供更好的解释与例子`;
  const lines = isEn
    ? [
        '### Term',
        `- **Term**: ${term}`,
        '- **Language**: English',
        '- **Mode**: Freeform (reason & examples)',
        `- **Current suggestion**: ${item ? item.suggest : ''}`,
        '',
        '### Better explanation & reasoning',
        submission.text,
        ...(submission.note ? ['', '### Concrete examples / context', submission.note] : [])
      ]
    : [
        '### 词条信息',
        `- **词条**：${term}`,
        '- **语言**：中文',
        '- **投稿模式**：无强格式模式（自由原因与例子）',
        `- **当前建议**：${item ? item.suggest : ''}`,
        '',
        '### 更好的解释与原因',
        submission.text,
        ...(submission.note ? ['', '### 具体例子 / 适用语境', submission.note] : [])
      ];
  const body = lines.join('\n');
  return { title, body, markdown: `# ${title}\n\n${body}` };
}

export function buildAddWordIssuePayload(lang, ui, entry) {
  const isEn = lang === 'en';
  const levelLabel = ui.levels[entry.level] || String(entry.level);
  const title = isEn
    ? `[New Term] ${entry.term}`
    : `[新增词条] ${entry.term}`;
  const jsonSnippet = JSON.stringify(
    {
      term: entry.term,
      level: entry.level,
      why: entry.why,
      ...(entry.suggest ? { suggest: entry.suggest } : {}),
      ...(entry.alias ? { alias: entry.alias } : {})
    },
    null,
    2
  );
  const lines = isEn
    ? [
        '### Proposed dictionary entry',
        '- **Language**: English',
        `- **Term**: ${entry.term}`,
        `- **Level**: ${levelLabel}`,
        `- **Reason**: ${entry.why}`,
        ...(entry.suggest ? [`- **Use instead**: ${entry.suggest}`] : []),
        ...(entry.alias ? [`- **Aliases**: ${entry.alias}`] : []),
        '',
        '```json',
        jsonSnippet,
        '```'
      ]
    : [
        '### 新词信息',
        '- **语言**：中文',
        `- **词语**：${entry.term}`,
        `- **建议级别**：${levelLabel}`,
        `- **理由**：${entry.why}`,
        ...(entry.suggest ? [`- **建议改成**：${entry.suggest}`] : []),
        ...(entry.alias ? [`- **别名**：${entry.alias}`] : []),
        '',
        '```json',
        jsonSnippet,
        '```'
      ];
  const body = lines.join('\n');
  return { title, body, markdown: `# ${title}\n\n${body}` };
}
