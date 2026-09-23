#!/bin/bash
# 品牌包一键构建：5 品牌 x (代表端 + 医生端) = 10 个 APK
# 做四件事（全部构建后 git checkout 还原，母版/开发行为不变）：
#   1. 覆写 <app>/src/brandConfig.ts（登录页品牌块 + 端口全走该租户 880x）
#   2. strings.xml app_name -> "<简称>数字员工"/"<简称>医生"
#   3. PIL 重生成桌面图标（主色字标）
#   4. gradle assembleRelease -PBRAND_SUFFIX=.<slug>（包名后缀，5 家可同机共存）
# 产物 out/medagent-{rep,doctor}-<slug>.apk；上传映射：apk-<slug>/medagent-{rep,doctor}.apk
set -euo pipefail
cd "$(dirname "$0")/../.."

# 与 setup-tenants.sh 的 TENANTS 表同源（slug|全称|简称|主色|字标|web端口），改动两处同步
BRANDS=(
  "zunpin|北京尊品科技有限公司|尊品科技|#2F54EB|尊|8801"
  "xiluoli|北京希洛利科技有限公司|希洛利科技|#0E9488|希|8802"
  "chenglin|郑州成琳网络科技有限公司|成琳网络|#D97706|成|8803"
  "qiyijia|北京琪宜嘉科技有限公司|琪宜嘉科技|#7C3AED|琪|8804"
  "jidian|集典（北京）信息科技有限公司|集典信息|#BE123C|典|8805"
)
OUT=deploy/multi-tenant/out
mkdir -p "$OUT"

inject_brand() { # $1=app $2=slug $3=全称 $4=简称 $5=主色 $6=字标 $7=端口
  python - "$1" "$2" "$3" "$4" "$5" "$6" "$7" <<'PY'
import sys, re
app, slug, full, short, color, char, port = sys.argv[1:8]
app_name = short[:2] + ('数字员工' if app == 'mobile' else '医生')  # 2 字品牌前缀，过长会被 launcher 截断
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
sp = f'{app}/android/app/src/main/res/values/strings.xml'
s = open(sp, encoding='utf-8').read()
s = re.sub(r'(<string name="app_name">).*?(</string>)', lambda m: m.group(1) + app_name + m.group(2), s)
open(sp, 'w', encoding='utf-8', newline='\n').write(s)
PY
  python deploy/multi-tenant/gen_brand_icon.py "$5" "$6" "$1/android/app/src/main/res"
}

for row in "${BRANDS[@]}"; do
  IFS='|' read -r slug full short color char port <<<"$row"
  for app in mobile mobile-doctor; do
    echo "=== $app / $slug ($short) ==="
    inject_brand "$app" "$slug" "$full" "$short" "$color" "$char" "$port"
    (cd "$app/android" && ./gradlew.bat assembleRelease -PBRAND_SUFFIX=".$slug" -q)
    apkname=medagent-rep; [ "$app" = mobile-doctor ] && apkname=medagent-doctor
    cp "$app/android/app/build/outputs/apk/release/app-release.apk" "$OUT/$apkname-$slug.apk"
    # 还原：res/strings 走 git checkout；brandConfig.ts 用独立脚本写回母版默认值
    git checkout -- "$app/android/app/src/main/res"
    python deploy/multi-tenant/restore_brand_defaults.py "$app"
    echo "built $OUT/$apkname-$slug.apk"
  done
done
ls -la "$OUT"
