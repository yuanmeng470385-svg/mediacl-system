/**
 * 工作台 - 代表每天第一眼看到的页面
 */
import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';

export default function HomeScreen() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.greeting}>早上好</Text>
        <Text style={styles.date}>2026年7月31日 星期四</Text>
      </View>
      <ScrollView style={styles.content}>
        {/* 今日进度 */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>今日拜访进度</Text>
          <Text style={styles.progress}>0 / 3</Text>
        </View>
        {/* 今日拜访列表 */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>今日拜访</Text>
          <Text style={styles.empty}>暂无拜访安排</Text>
        </View>
        {/* 快捷功能 */}
        <View style={styles.quickActions}>
          <View style={styles.quickBtn}>
            <Text>问答</Text>
          </View>
          <View style={styles.quickBtn}>
            <Text>内容</Text>
          </View>
          <View style={styles.quickBtn}>
            <Text>医生</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: { backgroundColor: '#3b82f6', padding: 20, paddingTop: 50 },
  greeting: { color: '#fff', fontSize: 24, fontWeight: '600' },
  date: { color: 'rgba(255,255,255,0.8)', fontSize: 14, marginTop: 4 },
  content: { flex: 1, padding: 16 },
  card: { backgroundColor: '#fff', padding: 16, borderRadius: 8, marginBottom: 12 },
  cardTitle: { fontSize: 16, fontWeight: '600', marginBottom: 8 },
  progress: { fontSize: 32, fontWeight: '700', color: '#3b82f6', textAlign: 'center' },
  empty: { fontSize: 14, color: '#999', textAlign: 'center', paddingVertical: 20 },
  quickActions: { flexDirection: 'row', justifyContent: 'space-around', marginTop: 8 },
  quickBtn: { backgroundColor: '#fff', padding: 16, borderRadius: 8, alignItems: 'center', flex: 1, marginHorizontal: 4 },
});
