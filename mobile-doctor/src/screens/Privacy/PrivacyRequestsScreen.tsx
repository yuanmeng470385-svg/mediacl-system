/**
 * 我的隐私请求（三期 L）：本人请求列表 + 状态/SLA 展示 + 处理回复。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { privacyAPI } from '../../api/privacy';
import type { PrivacyRequestItem } from '../../api/privacy';
import { Colors, FontSize } from '../../constants/theme';

const STATUS_TEXT: Record<string, { label: string; color: string }> = {
  pending: { label: '待处理', color: '#fa8c16' },
  processing: { label: '处理中', color: '#1677ff' },
  done: { label: '已完成', color: '#52c41a' },
  rejected: { label: '已驳回', color: '#ff4d4f' },
};

const TYPE_TEXT: Record<string, string> = {
  view: '查阅', correct: '更正', delete: '删除', export: '导出', account_delete: '注销',
};

export default function PrivacyRequestsScreen() {
  const [items, setItems] = useState<PrivacyRequestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await privacyAPI.getMyPrivacyRequests();
      setItems(data.items ?? []);
    } catch (e: any) {
      // client 只抛 APIError、无任何全局提示；加载失败须显示错误态 + 重试，不能伪装成"暂无"（此页承载法定 SLA 进度）
      setError(e?.message || '隐私请求加载失败，请检查网络');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading && items.length === 0) {
    return <View style={{ flex: 1, justifyContent: 'center' }}><ActivityIndicator /></View>;
  }

  return (
    <FlatList
      style={{ flex: 1, backgroundColor: Colors.background }}
      contentContainerStyle={{ padding: 16, gap: 12 }}
      data={items}
      keyExtractor={(item) => String(item.id)}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
      ListEmptyComponent={
        <View style={{ alignItems: 'center', paddingTop: 32, paddingHorizontal: 24 }}>
          <Text style={{ color: Colors.textSecondary, fontSize: FontSize.md, fontWeight: '600', textAlign: 'center' }}>
            {error || '暂无隐私请求'}
          </Text>
          {error ? (
            <Pressable
              onPress={load}
              style={{ backgroundColor: Colors.primary, borderRadius: 8, paddingHorizontal: 20, paddingVertical: 8, marginTop: 16 }}
            >
              <Text style={{ color: Colors.textWhite, fontWeight: '600' }}>重试</Text>
            </Pressable>
          ) : null}
        </View>
      }
      renderItem={({ item }) => (
        <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 6 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ fontWeight: '600', color: Colors.textPrimary }}>
              #{item.id} {TYPE_TEXT[item.request_type] ?? item.request_type}
            </Text>
            <Text style={{ color: STATUS_TEXT[item.status]?.color ?? Colors.textSecondary }}>
              {STATUS_TEXT[item.status]?.label ?? item.status}
            </Text>
          </View>
          {item.content?.detail ? (
            <Text style={{ color: Colors.textSecondary }}>{item.content.detail}</Text>
          ) : null}
          {item.content?.fields?.full_name || item.content?.fields?.phone ? (
            <Text style={{ color: Colors.textSecondary }}>
              待更正：{item.content.fields.full_name ?? ''} {item.content.fields.phone ?? ''}
            </Text>
          ) : null}
          {item.content?.response ? (
            <Text style={{ color: Colors.primary }}>回复：{item.content.response}</Text>
          ) : null}
          <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm }}>
            SLA 截止：{item.sla_deadline ?? '—'}
          </Text>
        </View>
      )}
    />
  );
}
