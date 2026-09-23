import { getBrand } from '../brand';

// 品牌字标：主色圆角方块 + 首字白字（5 家公司无 logo 文件，走字标方案；将来有文件换 logoUrl）
export default function BrandLogo({ size = 40 }: { size?: number }) {
  const b = getBrand();
  const char = (b.logoChar || b.short || b.name || 'M').slice(0, 1);
  const bg = b.primary || '#1677ff';
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.28),
        background: bg,
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: Math.round(size * 0.55),
        fontWeight: 600,
        flexShrink: 0,
        userSelect: 'none',
      }}
    >
      {char}
    </div>
  );
}
