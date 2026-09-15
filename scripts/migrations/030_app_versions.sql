-- 030：App 版本检查 + 更新提示（2026-09-15 挂账落地）
-- 两端 App 启动时 / 从后台切回时静默查 GET /api/v1/app/version?platform=rep|doctor：
--   本机版本 < latest_version → 弹窗提示（可跳过）；本机版本 < min_version → 强制更新（不更新不能用）。
-- 版本号与更新说明由 web 管理端「系统配置 → App 版本与更新」维护
-- （GET /api/v1/app/config、PUT /api/v1/app/config/{platform}，admin）。
-- download_url 允许两种写法：绝对地址（http/https，换域名后用它）或相对路径
-- （如 /apk/medagent-rep.apk，App 侧按自身配置的服务地址补全为 {scheme}://{host}:8080/...）。
-- release_notes 是给用户看的大白话，App 弹窗原文展示（支持多行）。
CREATE TABLE IF NOT EXISTS app_versions (
    platform VARCHAR(20) PRIMARY KEY CHECK (platform IN ('rep', 'doctor')),
    latest_version VARCHAR(20) NOT NULL,          -- 最新版本：高于本机即提示更新
    min_version VARCHAR(20) NOT NULL,             -- 最低可用版本：本机低于它强制更新
    download_url TEXT NOT NULL,                   -- APK 下载地址
    release_notes TEXT,                           -- 更新说明（多行）
    updated_by BIGINT,                            -- 最后修改人（users.id，不设 FK：审计已留痕，且防删号阻塞）
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 首版种子：与两端 App 的 package.json version（1.0.0）齐平 —— 装的就是最新版，不会一上线就弹更新
INSERT INTO app_versions (platform, latest_version, min_version, download_url, release_notes)
VALUES
    ('rep', '1.0.0', '1.0.0', '/apk/medagent-rep.apk', '首个版本：数字专员问答、AI 陪练、拜访记录、夜间简报。'),
    ('doctor', '1.0.0', '1.0.0', '/apk/medagent-doctor.apk', '首个版本：分身问答、医学问答、学术卡片收件箱。')
ON CONFLICT (platform) DO NOTHING;
