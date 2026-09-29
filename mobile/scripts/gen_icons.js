/* MedAgent 图标生成 —— 智联星芒定稿版（2026-09-29 施工单落地，按勘察改双工程直落模式）
 * 勘察结论：mobile（rep，com.medagent.mobile）与 mobile-doctor（doctor，com.medagent.doctor）
 * 是两个独立 RN 工程，双包天然共存，无需 productFlavors；本脚本按「单端 + 目标 res 根」运行，
 * 资源直落各工程 android/app/src/main/res（替代施工单附录的 src/{end}/res flavor 路径）。
 * 用法: node scripts/gen_icons.js <rep|doc> <resRoot> [brandRoot]
 *   mobile:        node scripts/gen_icons.js rep android/app/src/main/res
 *   mobile-doctor: node ../mobile/scripts/gen_icons.js doc android/app/src/main/res ..
 * 依赖: mobile 项目 npm i -D @resvg/resvg-js（依赖自脚本所在目录向上解析，mobile-doctor 侧共用）
 */
const fs = require('fs');
const path = require('path');
const { Resvg } = require('@resvg/resvg-js');

const END = process.argv[2];
const RES = path.resolve(process.argv[3]);
const BRAND = path.resolve(process.argv[4] || '.');
if (!['rep', 'doc'].includes(END)) throw new Error('用法: node gen_icons.js <rep|doc> <resRoot> [brandRoot]');

const PAL = {
  rep: { bg: ['#1E40AF', '#2563EB', '#06B6D4'], stroke: ['#2563EB', '#22D3EE'], name: '医智代表' },
  doc: { bg: ['#065F46', '#10B981', '#34D399'], stroke: ['#059669', '#6EE7B7'], name: '医智医生' },
};
const SPARK = 'M0 -11 C1 -3.5 3.5 -1 11 0 C3.5 1 1 3.5 0 11 C-1 3.5 -3.5 1 -11 0 C-3.5 -1 -1 -3.5 0 -11 Z';

function defs(p) {
  return `<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${p.bg[0]}"/><stop offset=".5" stop-color="${p.bg[1]}"/><stop offset="1" stop-color="${p.bg[2]}"/></linearGradient>
<linearGradient id="st" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="${p.stroke[0]}"/><stop offset="1" stop-color="${p.stroke[1]}"/></linearGradient>
<linearGradient id="wh" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EAF2FB"/></linearGradient>
<linearGradient id="sh" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".2"/><stop offset=".55" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient></defs>`;
}
function glyph(end, p) {
  const inner = end === 'rep'
    ? `<path d="M40 57 L52 44 L60 51 L79 32" fill="none" stroke="url(#st)" stroke-width="7.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M66 32 H79 V45" fill="none" stroke="url(#st)" stroke-width="7.5" stroke-linecap="round" stroke-linejoin="round"/>`
    : `<path d="M60 33 v32 M44 49 h32" fill="none" stroke="url(#st)" stroke-width="10.5" stroke-linecap="round"/>`;
  return `<rect x="29" y="26" width="62" height="46" rx="15" fill="url(#wh)"/><path d="M38 66 L38 84 Q38 88 42 85.5 L58 73 Z" fill="url(#wh)"/>${inner}<g transform="translate(94 22)"><path d="${SPARK}" fill="#FFFFFF"/></g><path d="${SPARK}" fill="#FFFFFF" opacity=".8" transform="translate(74 13) scale(.38)"/>`;
}
const full = end => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">${defs(PAL[end])}<rect x="4" y="4" width="112" height="112" rx="27" fill="url(#bg)"/><rect x="4" y="4" width="112" height="112" rx="27" fill="url(#sh)"/>${glyph(end, PAL[end])}</svg>`;
const fg = end => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108">${defs(PAL[end])}<g transform="translate(54 54) scale(0.8) translate(-68 -48.5)">${glyph(end, PAL[end])}</g></svg>`;

function render(svg, size, file) {
  const png = new Resvg(svg, { fitTo: { mode: 'width', value: size } }).render().asPng();
  fs.writeFileSync(file, png);
}
/* 双工程模式下 strings.xml 是各工程 main 里唯一资源文件，仍按「替换 app_name、保留其余」合并以防后续加串 */
function mergeAppName(name) {
  const f = path.join(RES, 'values', 'strings.xml');
  let s = fs.existsSync(f) ? fs.readFileSync(f, 'utf8') : '<resources>\n</resources>\n';
  if (/<string name="app_name">.*?<\/string>/.test(s)) {
    s = s.replace(/<string name="app_name">.*?<\/string>/, `<string name="app_name">${name}</string>`);
  } else {
    s = s.replace(/<\/resources>/, `    <string name="app_name">${name}</string>\n</resources>`);
  }
  fs.writeFileSync(f, s);
}

const DENS = [['mdpi', 1], ['hdpi', 1.5], ['xhdpi', 2], ['xxhdpi', 3], ['xxxhdpi', 4]];
const ADAPTIVE = `<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>`;

const p = PAL[END];
for (const [d, f] of DENS) {
  const dir = path.join(RES, 'mipmap-' + d);
  fs.mkdirSync(dir, { recursive: true });
  render(fg(END), Math.round(108 * f), path.join(dir, 'ic_launcher_foreground.png'));
  render(full(END), Math.round(48 * f), path.join(dir, 'ic_launcher.png'));
  render(full(END), Math.round(48 * f), path.join(dir, 'ic_launcher_round.png'));
}
fs.mkdirSync(path.join(RES, 'mipmap-anydpi-v26'), { recursive: true });
fs.writeFileSync(path.join(RES, 'mipmap-anydpi-v26', 'ic_launcher.xml'), ADAPTIVE);
fs.writeFileSync(path.join(RES, 'mipmap-anydpi-v26', 'ic_launcher_round.xml'), ADAPTIVE);
fs.mkdirSync(path.join(RES, 'drawable'), { recursive: true });
fs.writeFileSync(path.join(RES, 'drawable', 'ic_launcher_background.xml'),
`<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <gradient android:type="linear" android:angle="315"
        android:startColor="${p.bg[0]}" android:centerColor="${p.bg[1]}" android:endColor="${p.bg[2]}"/>
</shape>`);
mergeAppName(p.name);
fs.mkdirSync(BRAND, { recursive: true });
render(full(END), 1024, path.join(BRAND, `medagent_${END}_master_1024.png`));
console.log(`[${END}] 图标资源已生成 → ${RES}，app_name=${p.name}，母版 → ${BRAND}`);
