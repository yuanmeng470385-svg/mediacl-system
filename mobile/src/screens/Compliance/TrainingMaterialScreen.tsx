/**
 * 培训材料页（二期 F）：材料列表 + 详情 Modal。
 * listMaterials 返回 {items, total}（request 已解包 data），屏幕直接消费 res.items。
 */
import React, { useEffect, useState } from 'react';
import { Alert, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { examAPI } from '../../api/exam';
import Icon from '../../components/Icon';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

const TYPE_TEXT: Record<string, string> = { regulation: '办法', rdpac: 'RDPAC', internal: '内部政策' };

export default function TrainingMaterialScreen() {
  const navigation = useNavigation();
  const [items, setItems] = useState<any[]>([]);
  const [detail, setDetail] = useState<any | null>(null);

  const load = async () => {
    try {
      const res = await examAPI.listMaterials({ page: 1, page_size: 50 });
      setItems(res?.items || []);
    } catch { Alert.alert('加载失败', '无法获取培训材料'); }
  };

  useEffect(() => { load(); }, []);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}><Icon name="chevron-left" size={22} color={Colors.textWhite} /></TouchableOpacity>
        <Text style={styles.headerTitle}>培训材料</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        {items.map(item => (
          <TouchableOpacity key={item.id} style={[styles.card, Shadow.card]} onPress={() => setDetail(item)}>
            <Text style={styles.cardTitle}>{item.title}</Text>
            <Text style={styles.desc}>{TYPE_TEXT[item.material_type] || item.material_type} · 版本 {item.version}</Text>
          </TouchableOpacity>
        ))}
        {!items.length && <Text style={styles.empty}>暂无培训材料</Text>}
      </ScrollView>
      <Modal visible={!!detail} transparent animationType="slide" onRequestClose={() => setDetail(null)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalBody}>
            <ScrollView>
              <Text style={styles.modalTitle}>{detail?.title}</Text>
              <Text style={styles.modalContent}>{detail?.content}</Text>
            </ScrollView>
            <TouchableOpacity style={styles.closeBtn} onPress={() => setDetail(null)}><Text style={styles.closeText}>关闭</Text></TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14, paddingHorizontal: Spacing.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', ...Shadow.header },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  desc: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4 },
  empty: { textAlign: 'center', color: Colors.textHint, marginTop: 40 },
  modalWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.5)' },
  modalBody: { backgroundColor: Colors.card, borderTopLeftRadius: BorderRadius.lg, borderTopRightRadius: BorderRadius.lg, padding: Spacing.lg, maxHeight: '80%' },
  modalTitle: { fontSize: FontSize.lg, fontWeight: '600', marginBottom: Spacing.md },
  modalContent: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24 },
  closeBtn: { marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm, padding: Spacing.md, alignItems: 'center' },
  closeText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
