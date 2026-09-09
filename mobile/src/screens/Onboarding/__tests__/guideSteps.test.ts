/**
 * 代表端陪玩式引导配置形状测试（v2 2026-09-09）：
 * 无组件渲染测试基建（不引入新 devDep），锁定结构——6 步、首末纯讲解、中段 4 个体验步。
 * tryRoute 路由名真实性由 tsc 编译期锁定（GuideRoute = keyof ParamList，见 repGuideSteps.ts）。
 */
import { REP_GUIDE_DONE_KEY, REP_GUIDE_PROGRESS_KEY, REP_GUIDE_STEPS } from '../repGuideSteps';

describe('代表端陪玩式引导步骤', () => {
  it('共 6 步，每步有 icon/title/≥2 条 bullets', () => {
    expect(REP_GUIDE_STEPS).toHaveLength(6);
    for (const s of REP_GUIDE_STEPS) {
      expect(s.icon.length).toBeGreaterThan(0);
      expect(s.title.length).toBeGreaterThan(0);
      expect(s.bullets.length).toBeGreaterThanOrEqual(2);
      for (const b of s.bullets) expect(b.length).toBeGreaterThan(3);
    }
  });

  it('首步价值叙事纯讲解、末步操作说明纯讲解；中段 4 步带 tryRoute 体验目标', () => {
    const steps = REP_GUIDE_STEPS;
    expect(steps[0].tryRoute).toBeUndefined();
    expect(steps[0].title).toContain('数字员工');
    expect(steps[steps.length - 1].tryRoute).toBeUndefined();
    const lastText = steps[steps.length - 1].bullets.join('\n');
    expect(lastText).toContain('功能引导'); // 重看入口路径必须出现
    const trySteps = steps.filter((s) => s.tryRoute);
    expect(trySteps).toHaveLength(4);
  });

  it('每个体验步 tryRoute/tryName/tryHint 必填（导航+召回卡依赖）', () => {
    for (const s of REP_GUIDE_STEPS) {
      if (!s.tryRoute) continue;
      expect(s.tryRoute.length).toBeGreaterThan(0);
      expect(!!s.tryName?.trim()).toBe(true);
      expect(!!s.tryHint?.trim()).toBe(true);
    }
  });

  it('存储 key：done bump 到 v2（看过 v1 轮播的用户重弹），progress 独立键', () => {
    expect(REP_GUIDE_DONE_KEY).toBe('onboarding.rep.v2');
    expect(REP_GUIDE_PROGRESS_KEY).toBe('onboarding.rep.progress');
    expect(REP_GUIDE_DONE_KEY).not.toBe(REP_GUIDE_PROGRESS_KEY);
  });
});
