/**
 * 医生端新人引导轮播配置形状测试（A 档 2026-09-09）：
 * 锁定文案结构——首屏价值叙事、认证屏、末屏操作说明含重看路径。
 */
import { DOCTOR_ONBOARDING_KEY, DOCTOR_ONBOARDING_SLIDES } from '../doctorSlides';

describe('医生端新人引导 slides', () => {
  it('共 4 屏，每屏有 icon/title/至少 2 条 bullets', () => {
    expect(DOCTOR_ONBOARDING_SLIDES).toHaveLength(4);
    for (const s of DOCTOR_ONBOARDING_SLIDES) {
      expect(s.icon.length).toBeGreaterThan(0);
      expect(s.title.length).toBeGreaterThan(0);
      expect(s.bullets.length).toBeGreaterThanOrEqual(2);
      for (const b of s.bullets) expect(b.length).toBeGreaterThan(3);
    }
  });

  it('首屏价值叙事；认证有专屏；末屏操作说明含重看路径', () => {
    expect(DOCTOR_ONBOARDING_SLIDES[0].title).toContain('医生');
    expect(
      DOCTOR_ONBOARDING_SLIDES.some((s) => s.title.includes('认证')),
    ).toBe(true);
    const lastText = DOCTOR_ONBOARDING_SLIDES[DOCTOR_ONBOARDING_SLIDES.length - 1].bullets.join('\n');
    expect(lastText).toContain('功能引导');
  });

  it('存储 key 版本化（onboarding.doctor.v1，与代表端 key 隔离）', () => {
    expect(DOCTOR_ONBOARDING_KEY).toBe('onboarding.doctor.v1');
  });
});
