/** 3D 办公室布局常量（世界单位）。坐标系：桌面 y=0.96，行沿 x，行距沿 z，所有桌朝 +z。 */
export const PER_ROW = 5;
export const DESK_W = 2.08;
export const DESK_D = 1.17;
export const DESK_H = 0.96;
export const COL_X = 2.6;        // 桌列间距（净空 0.52）
export const ROW_Z = 2.4;        // 行间距（排间过道净空 1.23）
export const ROWS_MAX = 4;       // 最多 4 排（4×5 = 20 专员）
export const AISLE_PATROL_SPEED = 0.8;
export const DESK_APPROACH_SPEED = 1.4;
export const SIT_Z_OFFSET = 1.07; // 坐姿位置 = 桌中心 z + 此偏移（桌 +z 侧）

/** 第 col 列（0..4）的 x */
export function deskX(col: number): number {
  return (col - (PER_ROW - 1) / 2) * COL_X;
}
/** 第 ri 排的 z（排居中） */
export function rowZ(ri: number): number {
  return (ri - (ROWS_MAX - 1) / 2) * ROW_Z;
}
/** 第 ri 排 +z 侧过道巡逻线的 z */
export function aisleZ(ri: number): number {
  return rowZ(ri) + ROW_Z / 2;
}
/** 专员序号 → 工位行列（按 items 顺序稳定分配） */
export function slotOf(index: number): { ri: number; col: number } {
  return { ri: Math.floor(index / PER_ROW), col: index % PER_ROW };
}
/** 坐姿目标点（桌 +z 侧凳子前） */
export function sitPosOf(index: number): { x: number; z: number } {
  const s = slotOf(index);
  return { x: deskX(s.col), z: rowZ(s.ri) + SIT_Z_OFFSET };
}
/** 排内过道巡逻起点（该排过道线上、靠桌列 x） */
export function aislePosOf(index: number): { x: number; z: number } {
  const s = slotOf(index);
  return { x: deskX(s.col), z: aisleZ(s.ri) };
}
