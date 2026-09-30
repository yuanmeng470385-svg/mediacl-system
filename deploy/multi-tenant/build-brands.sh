#!/bin/bash
# 品牌包一键构建：5 品牌 x (代表端 + 医生端) = 10 个 APK
# 2026-09-29 图标命名定稿（智联星芒）：桌面图标与 App 名全品牌统一为 医智代表/医智医生
# （res 由 mobile/scripts/gen_icons.js 生成并入库，本脚本不再动），公司名只留登录页/关于页。
# 做两件事（全部构建后 git checkout 还原，母版/开发行为不变）：
#   1. 覆写 <app>/src/brandConfig.ts（登录页品牌块 + 端口全走该租户 880x；appName 字段为统一名）
#   2. 注入品牌 splash（品牌色打底 + 居中统一图标）并 gradle assembleRelease -PBRAND_SUFFIX=.<slug>（包名后缀，5 家可同机共存）
# 产物 out/medagent-{rep,doctor}-<slug>.apk；上传映射：apk-<slug>/medagent-{rep,doctor}.apk
set -euo pipefail
cd "$(dirname "$0")/../.."

# 与 setup-tenants.sh 的 TENANTS 表同源（slug|全称|简称|主色|字标|web端口），改动两处同步
BRANDS=(
  "zunpin|北京尊品科技有限公司|尊品科技|#2F54EB|尊|8801"
  "xiluoli|北京希洛利科技有限公司|希洛利科技|#0E9488|希|8802"
  "chenglin|郑州成琳网络科技有限公司|成琳网络|#D97706|成|8803"
  "qiyijia|北京琪艺嘉科技有限公司|琪艺嘉科技|#7C3AED|琪|8804"
  "jidian|集典（北京）信息科技有限公司|集典信息|#BE123C|典|8805"
)
OUT=deploy/multi-tenant/out
mkdir -p "$OUT"

inject_brand() { # $1=app $2=slug $3=全称 $4=简称 $5=主色 $6=字标 $7=端口
  python - "$1" "$2" "$3" "$4" "$5" "$6" "$7" <<'PY'
import sys
app, slug, full, short, color, char, port = sys.argv[1:8]
app_name = '医智代表' if app == 'mobile' else '医智医生'  # 2026-09-29 定稿：App 名全品牌统一，公司名只留登录页/关于页
open(f'{app}/src/brandConfig.ts', 'w', encoding='utf-8', newline='\n').write(
    f'''// 自动生成（deploy/multi-tenant/build-brands.sh），构建后由脚本还原；勿手改
export const BRAND = {{
  slug: '{slug}',
  name: '{full}',
  short: '{short}',
  appName: '{app_name}',
  primary: '{color}',
  char: '{char}',
  tagline: '药企 AI 数字员工系统',
  apiPort: {port},
}} as const;
''')
# Splash：品牌色打底 + 居中统一图标——<bitmap> 必须引 @drawable/ic_launcher_legacy
# （drawable-nodpi 成品 PNG；不能引 @mipmap/ic_launcher——API26+ 解析为 adaptive XML，<bitmap> 拒收启动即闪退）
N = chr(10)
res = f'{app}/android/app/src/main/res'
open(f'{res}/values/colors.xml', 'w', encoding='utf-8', newline='').write(
    '<resources>' + N + '    <color name="brand_splash">' + color + '</color>' + N + '</resources>' + N)
open(f'{res}/drawable/brand_splash.xml', 'w', encoding='utf-8', newline='').write(
    '<?xml version="1.0" encoding="utf-8"?>' + N
    + '<layer-list xmlns:android="http://schemas.android.com/apk/res/android">' + N
    + '    <item android:drawable="@color/brand_splash" />' + N
    + '    <item>' + N
    + '        <bitmap android:src="@drawable/ic_launcher_legacy" android:gravity="center" />' + N
    + '    </item>' + N
    + '</layer-list>' + N)
stp = f'{res}/values/styles.xml'
st = open(stp, encoding='utf-8').read()
marker = '<item name="android:editTextBackground">@drawable/rn_edit_text_material</item>'
assert marker in st
st = st.replace(marker, marker + N + '        <item name="android:windowBackground">@drawable/brand_splash</item>', 1)
open(stp, 'w', encoding='utf-8', newline='').write(st)
PY
}

for row in "${BRANDS[@]}"; do
  IFS='|' read -r slug full short color char port <<<"$row"
  # BRAND_ONLY=<slug> 只出指定品牌（单租户改名/修复重出用，免跑全量 10 包）
  [ -n "${BRAND_ONLY:-}" ] && [ "$slug" != "$BRAND_ONLY" ] && continue
  for app in mobile mobile-doctor; do
    echo "=== $app / $slug ($short) ==="
    inject_brand "$app" "$slug" "$full" "$short" "$color" "$char" "$port"
    (cd "$app/android" && ./gradlew.bat assembleRelease -PBRAND_SUFFIX=".$slug" -q)
    apkname=medagent-rep; [ "$app" = mobile-doctor ] && apkname=medagent-doctor
    cp "$app/android/app/build/outputs/apk/release/app-release.apk" "$OUT/$apkname-$slug.apk"
    # 还原：res 走 git checkout；brandConfig.ts 用独立脚本写回母版默认值
    git checkout -- "$app/android/app/src/main/res"
    rm -f "$app/android/app/src/main/res/values/colors.xml" "$app/android/app/src/main/res/drawable/brand_splash.xml"
    python deploy/multi-tenant/restore_brand_defaults.py "$app"
    echo "built $OUT/$apkname-$slug.apk"
  done
done
ls -la "$OUT"
