# 用法: python gen_brand_icon.py <#RRGGBB> <字标字> <android res 目录>
# 生成各密度 ic_launcher.png / ic_launcher_round.png：主色圆角方块（圆版为正圆）+ 白字居中。
# 无 logo 文件的字标方案；将来有真 logo 直接替换 PNG 即可。
import sys
from PIL import Image, ImageDraw, ImageFont

color_hex, char, res_dir = sys.argv[1], sys.argv[2], sys.argv[3]
rgb = tuple(int(color_hex[i:i + 2], 16) for i in (1, 3, 5))
SIZES = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}
FONTS = [r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf']

def load_font(px):
    for f in FONTS:
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    raise SystemExit('no CJK font found (msyh/simhei)')

for dpi, size in SIZES.items():
    for name, radius in (('ic_launcher', int(size * 0.22)), ('ic_launcher_round', size // 2)):
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=rgb + (255,))
        d.text((size / 2, size / 2 + size * 0.02), char, font=load_font(int(size * 0.55)),
               fill=(255, 255, 255, 255), anchor='mm')
        out = f'{res_dir}/mipmap-{dpi}/{name}.png'
        img.save(out)
print('icons generated for', char)
