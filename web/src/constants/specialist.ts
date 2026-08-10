/** 专员生命周期状态 → Tag 颜色/文案（SpecialistList 与 SpecialistOffice 共用） */
export const STATUS_MAP: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  active: { color: 'green', text: '正式' },
  disabled: { color: 'red', text: '停用' },
};
