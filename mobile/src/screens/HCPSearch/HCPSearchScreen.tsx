/**
 * 医生搜索页
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export default function HCPSearchScreen() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>医生</Text>
      </View>
      <View style={styles.content}>
        <Text style={styles.empty}>暂无医生数据</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: { backgroundColor: '#3b82f6', padding: 20, paddingTop: 50 },
  title: { color: '#fff', fontSize: 20, fontWeight: '600' },
  content: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 16 },
  empty: { fontSize: 14, color: '#999' },
});
