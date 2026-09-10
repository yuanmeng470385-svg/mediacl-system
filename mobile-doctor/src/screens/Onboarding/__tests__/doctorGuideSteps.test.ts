/**
 * 医生端陪玩式引导配置形状测试（v3 2026-09-10）：
 * 无组件渲染测试基建（不引入新 devDep），锁定结构——7 步、首末纯讲解、中段 5 个体验步
 * （v3 增补患教工具步）。
 * tryRoute 路由名真实性由 tsc 编译期锁定（GuideRoute = keyof ParamList，见 doctorGuideSteps.ts）。
 */
import { DOCTOR_GUIDE_DONE_KEY, DOCTOR_GUIDE_PROGRESS_KEY, DOCTOR_GUIDE_STEPS } from '../doctorGuideSteps';

describe('医生端陪玩式引导步骤', () => {
  it('共 7 步，每步有 icon/title/≥2 条 bullets', () => {
    expect(DOCTOR_GUIDE_STEPS).toHaveLength(7);
    for (const s of DOCTOR_GUIDE_STEPS) {
      expect(s.icon.length).toBeGreaterThan(0);
      expect(s.title.length).toBeGreaterThan(0);
      expect(s.bullets.length).toBeGreaterThanOrEqual(2);
      for (const b of s.bullets) expect(b.length).toBeGreaterThan(3);
    }
  });

  it('首步价值叙事纯讲解、末步操作说明纯讲解；中段 5 步带 tryRoute 体验目标（含 v3 新增患教工具）', () => {
    const steps = DOCTOR_GUIDE_STEPS;
    expect(steps[0].tryRoute).toBeUndefined();
    expect(steps[0].title).toContain('医生');
    expect(steps[steps.length - 1].tryRoute).toBeUndefined();
    const lastText = steps[steps.length - 1].bullets.join('\n');
    expect(lastText).toContain('功能引导'); // 重看入口路径必须出现
    const tryRoutes = steps.filter((s) => s.tryRoute).map((s) => s.tryRoute);
    expect(tryRoutes).toHaveLength(5);
    expect(tryRoutes).toContain('PatientEdu'); // v3 新增患教工具步（防后续误删）
  });

  it('每个体验步 tryRoute/tryName/tryHint 必填（导航+召回卡依赖）', () => {
    for (const s of DOCTOR_GUIDE_STEPS) {
      if (!s.tryRoute) continue;
      expect(s.tryRoute.length).toBeGreaterThan(0);
      expect(!!s.tryName?.trim()).toBe(true);
      expect(!!s.tryHint?.trim()).toBe(true);
    }
  });

  it('存储 key：done bump 到 v3（看过 v2 的用户重弹），progress 独立键', () => {
    expect(DOCTOR_GUIDE_DONE_KEY).toBe('onboarding.doctor.v3');
    expect(DOCTOR_GUIDE_PROGRESS_KEY).toBe('onboarding.doctor.progress');
    expect(DOCTOR_GUIDE_DONE_KEY).not.toBe(DOCTOR_GUIDE_PROGRESS_KEY);
  });
});
