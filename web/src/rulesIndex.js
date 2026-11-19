import rulesData from './rules.json';

const ZH_BOUNDS = [
  ['A', '阿'], ['B', '八'], ['C', '嚓'], ['D', '哒'], ['E', '鹅'],
  ['F', '发'], ['G', '噶'], ['H', '哈'], ['J', '击'], ['K', '喀'],
  ['L', '垃'], ['M', '妈'], ['N', '拿'], ['O', '哦'], ['P', '啪'],
  ['Q', '期'], ['R', '然'], ['S', '撒'], ['T', '塌'], ['W', '挖'],
  ['X', '昔'], ['Y', '压'], ['Z', '匝']
];
const ZH_COLLATOR = new Intl.Collator('zh-Hans-CN');

export function letterFor(langKey, term, letters) {
  const first = term.trim().charAt(0).toUpperCase();
  if (/^[A-Z]$/.test(first) && letters.includes(first)) return first;
  if (langKey !== 'zh') return letters[0];
  let matched = letters[0];
  for (const [letter, anchor] of ZH_BOUNDS) {
    if (letters.includes(letter) && ZH_COLLATOR.compare(term.trim(), anchor) >= 0) matched = letter;
  }
  return matched;
}

export function buildGroups(langKey, letters) {
  const buckets = new Map();
  for (const rule of rulesData.rules) {
    if (rule.lang !== langKey || ![1, 2, 3].includes(rule.level)) continue;
    const item = { term: rule.term, level: rule.level, why: rule.why || '', suggest: rule.suggest || '' };
    if (rule.ok_when) item.ok = rule.ok_when;
    if (rule.bad_when) item.bad = rule.bad_when;
    if (rule.aliases && rule.aliases.length) item.alias = rule.aliases.join(langKey === 'zh' ? '、' : ', ');
    const letter = letterFor(langKey, rule.term, letters);
    if (!buckets.has(letter)) buckets.set(letter, []);
    buckets.get(letter).push(item);
  }
  return letters.filter((letter) => buckets.has(letter)).map((letter) => ({ letter, items: buckets.get(letter) }));
}

export function countRules(langKey) {
  return rulesData.rules.filter((rule) => rule.lang === langKey && [1, 2, 3].includes(rule.level)).length;
}
