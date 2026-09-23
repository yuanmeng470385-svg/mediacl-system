# 用法: python restore_brand_defaults.py <mobile|mobile-doctor|all>
# build-brands.sh 每轮构建后调用：把 brandConfig.ts 还原为母版默认（BRAND=null）
import sys

TEMPLATE = '''// 品牌包构建时由 deploy/multi-tenant/build-brands.sh 覆写；母版与本地开发保持 null（行为不变）
export const BRAND: {
  slug: string;
  name: string; // 公司全称（登录页品牌块 / 关于页）
  short: string; // 简称
  appName: string; // App 显示名（尊品数字员工/尊品医生）：桌面名与登录页共用
  primary: string; // 品牌主色 #RRGGBB
  char: string; // 字标首字
  tagline: string; // 副标语
  apiPort: number; // 该租户 web 入口端口（8801-8805），全部流量走它
} | null = null;
'''

apps = ['mobile', 'mobile-doctor'] if sys.argv[1:2] == ['all'] or not sys.argv[1:] else [sys.argv[1]]
for app in apps:
    open(f'{app}/src/brandConfig.ts', 'w', encoding='utf-8', newline='\n').write(TEMPLATE)
    print(f'{app}/src/brandConfig.ts restored')
