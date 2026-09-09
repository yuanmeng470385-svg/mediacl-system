/**
 * 新人引导轮播配置形状测试（A 档 2026-09-09）：
 * 无组件渲染测试基建（不引入新 devDep），锁定文案结构——首屏价值叙事、末屏操作说明含重看路径。
 */
import { REP_ONBOARDING_KEY, REP_ONBOARDING_SLIDES } from '../repSlides';

describe('代表端新人引导 slides', () => {
  it('共 4 屏，每屏有 icon/title/至少 2 条 bullets', () => {
    expect(REP_ONBOARDING_SLIDES).toHaveLength(4);
    for (const s of REP_ONBOARDING_SLIDES) {
      expect(s.icon.length).toBeGreaterThan(0);
      expect(s.title.length).toBeGreaterThan(0);
      expect(s.bullets.length).toBeGreaterThanOrEqual(2);
      for (const b of s.bullets) expect(b.length).toBeGreaterThan(3);
    }
  });

  it('首屏价值叙事（提数字员工），末屏操作说明（含合规培训深藏路径与重看路径）', () => {
    const first = REP_ONBOARDING_SLIDES[0];
    const last = REP_ONBOARDING_SLIDES[REP_ONBOARDING_SLIDES.length - 1];
    expect(first.title).toContain('数字员工');
    const lastText = last.bullets.join('\n');
    expect(lastText).toContain('备案与资质');
    expect(lastText).toContain('功能引导'); // 重看入口路径必须出现
  });

  it('存储 key 版本化（onboarding.rep.v1）', () => {
    expect(REP_ONBOARDING_KEY).toBe('onboarding.rep.v1');
  });
});
