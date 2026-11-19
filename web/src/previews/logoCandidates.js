import flowLogo from './logo-flow.svg?raw';

function createLogo(title, content) {
  return flowLogo
    .replace('人类语言与 AI 语言，流动互译', title)
    .replace(/<g class="brand-flow-ai">[\s\S]*?<\/g>/, `<g class="brand-flow-ai">${content}</g>`);
}

const orbit = '<path class="brand-flow-loop" d="M25 26c3 7 11 9 16.5 5S47 19 41 15c-4-2.5-9-2-13 1l-3 3" /><path class="brand-flow-loop" d="M30.5 19H25v-5.5" />';

export const logoCandidates = [
  {
    key: 'binary',
    name: '二进制引号',
    label: '新尝试 · 引号里藏着 01',
    description: '左侧是自然语言的圆润引号，右侧把像素引号写成隐约可辨的 0 和 1。沿用双向回旋的线，连接人类表达与数字语言。',
    detail: '中空方块暗示 0，折角竖条暗示 1；两者底部都保留引号的小尾巴。',
    logo: createLogo('人类引号与暗含零一的像素引号相互转译', `${orbit}<path class="brand-candidate-solid" fill-rule="evenodd" d="M30 18h6v8h-3v2h-3Zm2 2v4h2v-4Z" /><path class="brand-candidate-solid" d="M37 18h4v8l-2 2h-2v-4h2v-4h-2Z" />`),
  },
  {
    key: 'pixel',
    name: '像素引号',
    label: '最终版 · 首页使用',
    description: '人类侧的圆润引号，在 AI 侧变成离散的像素。用同一个语言符号，表达两种理解方式。',
    detail: '方形引号保留向内收拢的笔势，与左侧圆润引号形成对应。',
    logo: createLogo('人类的自然表达与 AI 的像素语言相互转译', `${orbit}<path class="brand-candidate-solid" d="M30 20h4v4h-2v3h-2Zm7 0h4v4h-2v3h-2Z" />`),
  },
  {
    key: 'tokens',
    name: '语义分词',
    label: '表达 → 拆解 → 理解',
    description: '一句连续的表达，转化成几段有序的语言单元。长短不同的词块，让 AI 的语言处理更具体。',
    detail: '三段词块与一枚独立小方块，暗示语言被拆分、编码和重新组织。',
    logo: createLogo('人类语言与 AI 语言单元相互转译', `${orbit}<g class="brand-candidate-solid"><rect x="30" y="18" width="7" height="3" rx=".8" /><rect x="39" y="18" width="3" height="3" rx=".5" /><rect x="30" y="23" width="4" height="3" rx=".6" /><rect x="36" y="23" width="6" height="3" rx=".8" /></g>`),
  },
  {
    key: 'nodes',
    name: '思考节点',
    label: '对话 · 连接 · 推理',
    description: '用彼此相连的节点表示关联与推理。相比代码括号，更偏向“一个正在理解你的智能体”。',
    detail: '三个节点形成开放的连接关系，让外圈的对话循环与内侧的思考网络呼应。',
    logo: createLogo('人类表达与智能体的关联推理相互转译', `${orbit}<path class="brand-candidate-network" d="m32 18 8 5-7 5-1-10" /><g class="brand-candidate-nodes"><circle cx="32" cy="18" r="2" /><circle cx="40" cy="23" r="2" /><circle cx="33" cy="28" r="2" /></g>`),
  },
  {
    key: 'agent',
    name: '编码对话',
    label: '<> 增强版 · 更明确的 Agent',
    description: '保留熟悉的代码括号，同时加入对话尾部、感知触点和三枚语言点，让它更像在回应的智能体。',
    detail: '折角轮廓表示硅基结构，顶部触点表示感知，底部点阵表示持续生成的语言。',
    logo: createLogo('人类语言与能够感知回应的 AI 智能体相互转译', '<path class="brand-flow-loop" d="M29 14h12l4 4v10h-7l-5 4v-4h-4l-4-4v-6Z" /><path class="brand-candidate-network" d="M35 14v-4h3" /><circle class="brand-candidate-solid" cx="40" cy="10" r="1.7" /><path class="brand-candidate-brackets" d="m32 18-2.5 2.5L32 23m6-5 2.5 2.5L38 23" /><g class="brand-candidate-solid"><circle cx="32" cy="25.5" r=".8" /><circle cx="35" cy="25.5" r=".8" /><circle cx="38" cy="25.5" r=".8" /></g>'),
  },
];
