/**
 * 深藏入口的一次性提示气泡（A 档：代表端 3 处）。
 * 首次挂载弹 Modal（标题+正文+「知道了」），AsyncStorage 记录后永不再弹。
 * 与通知设置同款存储惯例；读存储失败不弹（fail-safe，不骚扰）。
 */
import React, { useEffect, useState } from 'react';
import { View, Text, Modal, StyleSheet, TouchableOpacity } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Colors, FontSize, Spacing, BorderRadius } from '../constants/theme';

interface Props {
  storageKey: string;
  title: string;
  content: string;
}

export default function FirstUseTip({ storageKey, title, content }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let alive = true;
    AsyncStorage.getItem(storageKey).then((v) => {
      if (alive && v === null) setVisible(true);
    }).catch(() => {/* 存储异常不弹 */});
    return () => { alive = false; };
  }, [storageKey]);

  const ack = async () => {
    setVisible(false);
    await AsyncStorage.setItem(storageKey, String(Date.now())).catch(() => {});
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={ack}>
      <View style={styles.mask}>
        <View style={styles.card}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.content}>{content}</Text>
          <TouchableOpacity style={styles.btn} onPress={ack}>
            <Text style={styles.btnText}>知道了</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  mask: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center', alignItems: 'center', padding: Spacing.xl },
  card: {
    width: '100%', backgroundColor: Colors.white, borderRadius: BorderRadius.lg, padding: Spacing.lg,
  },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.primary, marginBottom: Spacing.sm },
  content: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 24, marginBottom: Spacing.lg },
  btn: { alignSelf: 'stretch', backgroundColor: Colors.primary, borderRadius: BorderRadius.md, paddingVertical: Spacing.sm + 2, alignItems: 'center' },
  btnText: { color: '#fff', fontSize: FontSize.md, fontWeight: '600' },
});
