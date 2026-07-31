/**
 * 我的 - 个人中心
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';

export default function ProfileScreen() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>我的</Text>
      </View>
      <View style={styles.content}>
        <View style={styles.card}>
          <Text style={styles.name}>医药代表</Text>
          <Text style={styles.role}>肿瘤事业部 · 华东区</Text>
        </View>
        <View style={styles.stats}>
          <View style={styles.statItem}>
            <Text style={styles.statNum}>0</Text>
            <Text style={styles.statLabel}>对话</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statNum}>0</Text>
            <Text style={styles.statLabel}>拜访</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statNum}>0</Text>
            <Text style={styles.statLabel}>收藏</Text>
          </View>
        </View>
        <TouchableOpacity style={styles.logoutBtn}>
          <Text style={styles.logoutText}>退出登录</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: { backgroundColor: '#3b82f6', padding: 20, paddingTop: 50 },
  title: { color: '#fff', fontSize: 20, fontWeight: '600' },
  content: { flex: 1, padding: 16 },
  card: { backgroundColor: '#fff', padding: 20, borderRadius: 8, marginBottom: 16 },
  name: { fontSize: 18, fontWeight: '600' },
  role: { fontSize: 14, color: '#666', marginTop: 4 },
  stats: { flexDirection: 'row', backgroundColor: '#fff', borderRadius: 8, padding: 16, marginBottom: 16 },
  statItem: { flex: 1, alignItems: 'center' },
  statNum: { fontSize: 24, fontWeight: '700', color: '#3b82f6' },
  statLabel: { fontSize: 12, color: '#999', marginTop: 4 },
  logoutBtn: { padding: 16, alignItems: 'center' },
  logoutText: { color: '#dc2626', fontSize: 16 },
});
