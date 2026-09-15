/**
 * 版本更新门（2026-09-15 挂账：App 版本检查+更新提示）
 *
 * 时机：启动时查一次 + 每次从后台切回前台再查（60s 内不重复查，避免频繁切应用打接口）。
 * 表现：本机版本 < 最低可用版本 → 强制更新，弹窗不可关（无「暂不更新」、返回键无效）；
 *       只低于最新版本 → 提示更新，可以「暂不更新」跳过。
 * 安装：点「立即更新」用系统浏览器打开 APK 下载地址（相对路径自动补服务器地址），
 *       下载完成后点安装包安装即可（首次需允许「安装未知来源应用」）。
 *
 * 静默失败：查不到版本（离线/后端未部署该表）绝不打扰用户——更新提示是锦上添花，
 * 不能因为查版本失败让人用不了 App。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AppState, Linking, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';

import { appVersionAPI, type AppVersionInfo } from '../api/appVersion';
import { Colors, FontSize } from '../constants/theme';
import { APP_VERSION, hasUpdate, isForcedUpdate, resolveDownloadUrl } from '../utils/appVersion';

/** 本 App 对应后端的 platform 标识（医生端包改成 'doctor'） */
const PLATFORM: 'rep' | 'doctor' = 'rep';
/** 两次版本检查的最小间隔：用户在多个 App 间来回切时别把接口打爆 */
const MIN_CHECK_INTERVAL_MS = 60 * 1000;

export default function UpdateGate() {
  const [info, setInfo] = useState<AppVersionInfo | null>(null);
  const [forced, setForced] = useState(false);
  const [opened, setOpened] = useState(false); // 是否已拉起下载页（补一句安装提示）
  const lastCheckRef = useRef(0);
  const busyRef = useRef(false);

  const check = useCallback(async (immediate = false) => {
    if (busyRef.current) return;
    if (!immediate && Date.now() - lastCheckRef.current < MIN_CHECK_INTERVAL_MS) return;
    busyRef.current = true;
    lastCheckRef.current = Date.now();
    try {
      const data = await appVersionAPI.check(PLATFORM);
      if (!data || !hasUpdate(APP_VERSION, data.latest_version)) {
        // 已是最新（或无数据）：把可能开着的提示收掉，强制更新窗不动它
        setInfo((prev) => (prev && isForcedUpdate(APP_VERSION, prev.min_version) ? prev : null));
        return;
      }
      setForced(isForcedUpdate(APP_VERSION, data.min_version));
      setOpened(false);
      setInfo(data);
    } catch {
      // 静默：离线或后端异常不影响正常使用
    } finally {
      busyRef.current = false;
    }
  }, []);

  useEffect(() => {
    check(true);
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') check();
    });
    return () => sub.remove();
  }, [check]);

  const onUpdate = useCallback(async () => {
    const url = resolveDownloadUrl(info?.download_url);
    if (!url) return;
    try {
      await Linking.openURL(url);
      setOpened(true);
    } catch {
      // 打不开（无浏览器/地址不合法）：留下地址让用户自己复制
      setOpened(true);
    }
  }, [info]);

  if (!info) return null;

  return (
    <Modal
      visible
      transparent
      animationType="fade"
      statusBarTranslucent
      // 强制更新：安卓返回键/点击遮罩都不关（用户必须先更新）
      onRequestClose={() => { /* 强制更新时不可关闭；非强制时也用按钮关 */ }}
    >
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <Text style={styles.title}>
            {forced ? '需要更新后才能继续使用' : `发现新版本 v${info.latest_version}`}
          </Text>
          <Text style={styles.meta}>
            当前版本 v{APP_VERSION} → 最新版本 v{info.latest_version}
            {forced ? `（低于最低可用版本 v${info.min_version}）` : ''}
          </Text>

          <ScrollView style={styles.notes} contentContainerStyle={styles.notesInner}>
            <Text style={styles.notesTitle}>更新内容</Text>
            <Text style={styles.notesText}>
              {(info.release_notes || '').trim() || '提升了稳定性与体验。'}
            </Text>
            {opened && (
              <Text style={styles.tip}>
                已打开下载页：下载完成后点开安装包安装（首次安装需允许「安装未知应用」）。
                装好后回到这里即可继续使用。
              </Text>
            )}
          </ScrollView>

          <View style={styles.actions}>
            {!forced && (
              <TouchableOpacity style={[styles.btn, styles.btnGhost]} onPress={() => setInfo(null)}>
                <Text style={styles.btnGhostText}>暂不更新</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity style={[styles.btn, styles.btnPrimary]} onPress={onUpdate}>
              <Text style={styles.btnPrimaryText}>立即更新</Text>
            </TouchableOpacity>
          </View>

          {forced && (
            <Text style={styles.footHint}>
              当前版本过旧，为避免数据不一致已暂停使用；更新后自动恢复。
            </Text>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  card: {
    width: '100%',
    maxWidth: 420,
    backgroundColor: Colors.card,
    borderRadius: 16,
    padding: 20,
  },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary },
  meta: { marginTop: 8, fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  notes: { maxHeight: 220, marginTop: 14 },
  notesInner: { paddingBottom: 4 },
  notesTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textPrimary, marginBottom: 6 },
  notesText: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 22 },
  tip: {
    marginTop: 12,
    fontSize: FontSize.xs,
    color: Colors.primaryLight,
    lineHeight: 20,
    backgroundColor: Colors.primarySurface,
    borderRadius: 8,
    padding: 10,
  },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: 18 },
  btn: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: 8, marginLeft: 12 },
  btnGhost: { borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.white },
  btnGhostText: { color: Colors.textSecondary, fontSize: FontSize.md, fontWeight: '600' },
  btnPrimary: { backgroundColor: Colors.primary },
  btnPrimaryText: { color: Colors.textOnPrimary, fontSize: FontSize.md, fontWeight: '700' },
  footHint: { marginTop: 12, fontSize: FontSize.xs, color: Colors.textHint, lineHeight: 18 },
});
