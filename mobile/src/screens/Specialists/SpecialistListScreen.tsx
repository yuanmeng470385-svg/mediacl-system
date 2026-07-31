/**
 * 数字专员列表页
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export default function SpecialistListScreen() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>数字专员</Text>
      </View>
      <View style={styles.content}>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>肿瘤专员「小K」</Text>
          <Text style={styles.status}>状态：待配置</Text>
          <Text style={styles.hint}>百炼 App ID 配置后即可使用</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: { backgroundColor: '#3b82f6', padding: 20, paddingTop: 50 },
  title: { color: '#fff', fontSize: 20, fontWeight: '600' },
  content: { flex: 1, padding: 16 },
  card: { backgroundColor: '#fff', padding: 16, borderRadius: 8 },
  cardTitle: { fontSize: 16, fontWeight: '600', marginBottom: 8 },
  status: { fontSize: 14, color: '#666' },
  hint: { fontSize: 12, color: '#999', marginTop: 4 },
});
