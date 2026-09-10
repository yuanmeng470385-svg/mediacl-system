/**
 * 代表端陪玩式引导配置形状测试（v3 2026-09-10）：
 * 无组件渲染测试基建（不引入新 devDep），锁定结构——11 步、首末纯讲解、中段 9 个体验步
 * （v3 增补夜间简报/学术卡片/AI 陪练/Skill 广场/Skill 发布五步）。
 * tryRoute 路由名真实性由 tsc 编译期锁定（GuideRoute = keyof ParamList，见 repGuideSteps.ts）。
 */
import { REP_GUIDE_DONE_KEY, REP_GUIDE_PROGRESS_KEY, REP_GUIDE_STEPS } from '../repGuideSteps';

describe('代表端陪玩式引导步骤', () => {
  it('共 11 步，每步有 icon/title/≥2 条 bullets', () => {
    expect(REP_GUIDE_STEPS).toHaveLength(11);
    for (const s of REP_GUIDE_STEPS) {
      expect(s.icon.length).toBeGreaterThan(0);
      expect(s.title.length).toBeGreaterThan(0);
      expect(s.bullets.length).toBeGreaterThanOrEqual(2);
      for (const b of s.bullets) expect(b.length).toBeGreaterThan(3);
    }
  });

  it('首步价值叙事纯讲解、末步操作说明纯讲解；中段 9 步带 tryRoute 体验目标（含 v3 新增五步）', () => {
    const steps = REP_GUIDE_STEPS;
    expect(steps[0].tryRoute).toBeUndefined();
    expect(steps[0].title).toContain('数字员工');
    expect(steps[steps.length - 1].tryRoute).toBeUndefined();
    const lastText = steps[steps.length - 1].bullets.join('\n');
    expect(lastText).toContain('功能引导'); // 重看入口路径必须出现
    const tryRoutes = steps.filter((s) => s.tryRoute).map((s) => s.tryRoute);
    expect(tryRoutes).toHaveLength(9);
    // v3 新增的「我的」页五步必须在列（防后续误删）
    for (const route of ['BriefingList', 'AcademicCardCreate', 'PracticeList', 'Plaza', 'SkillRelease']) {
      expect(tryRoutes).toContain(route);
    }
  });

  it('每个体验步 tryRoute/tryName/tryHint 必填（导航+召回卡依赖）', () => {
    for (const s of REP_GUIDE_STEPS) {
      if (!s.tryRoute) continue;
      expect(s.tryRoute.length).toBeGreaterThan(0);
      expect(!!s.tryName?.trim()).toBe(true);
      expect(!!s.tryHint?.trim()).toBe(true);
    }
  });

  it('存储 key：done bump 到 v3（看过 v2 的用户重弹），progress 独立键', () => {
    expect(REP_GUIDE_DONE_KEY).toBe('onboarding.rep.v3');
    expect(REP_GUIDE_PROGRESS_KEY).toBe('onboarding.rep.progress');
    expect(REP_GUIDE_DONE_KEY).not.toBe(REP_GUIDE_PROGRESS_KEY);
  });
});
