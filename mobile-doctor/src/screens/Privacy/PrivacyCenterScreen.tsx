/**
 * 隐私中心（三期 L，需求 5.7）：隐私政策全文 + 个人信息 + 四类申请入口。
 * 注销需二次确认（Alert.alert 确认后才提交 confirm=true，后端再校验一次）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, Modal, Pressable, ScrollView, Text, TextInput, View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { privacyAPI } from '../../api/privacy';
import type { CreatePrivacyRequestPayload, PersonalData, PrivacyPolicy } from '../../api/privacy';
import type { RootStackParamList } from '../../navigation/types';
import { Colors, FontSize } from '../../constants/theme';

type Props = NativeStackScreenProps<RootStackParamList, 'PrivacyCenter'>;

type FormKind = Extract<CreatePrivacyRequestPayload['request_type'], 'correct' | 'export' | 'delete' | 'account_delete'>;

const FORM_META: Record<FormKind, { title: string; hint: string; confirmText?: string }> = {
  correct: { title: '申请更正', hint: '填写要更正为的姓名/手机号（至少一项）' },
  export: { title: '申请导出', hint: '申请导出本人全部数据包，管理端 30 日内处理' },
  delete: { title: '申请删除', hint: '删除采用去标识化处理，依法留存的合规记录不物理删除' },
  account_delete: {
    title: '申请注销',
    hint: '注销后账号不可恢复，个人信息将去标识化',
    confirmText: '注销后账号将无法登录且不可恢复，确认申请注销？',
  },
};

export default function PrivacyCenterScreen({ navigation }: Props) {
  const [policy, setPolicy] = useState<PrivacyPolicy | null>(null);
  const [personal, setPersonal] = useState<PersonalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formKind, setFormKind] = useState<FormKind | null>(null);
  const [detail, setDetail] = useState('');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [p, d] = await Promise.all([privacyAPI.getPrivacyPolicy(), privacyAPI.getPersonalData()]);
      setPolicy(p);
      setPersonal(d);
    } catch (e: any) {
      // client 只抛 APIError、无任何全局提示；加载失败须本屏自显（错误态 + 重试，照 FavoritesScreen）
      setError(e?.message || '隐私中心加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const submit = (kind: FormKind) => {
    const meta = FORM_META[kind];
    const doSubmit = async () => {
      setSubmitting(true);
      try {
        const payload: CreatePrivacyRequestPayload = { request_type: kind, detail };
        // 残留字段守卫：fullName/phone 仅属于 correct；取消/返回只关弹窗不清输入，
        // 残留值不能泄入 export/delete/account_delete（否则 fields 为 undefined 仍赋值 → TypeError 被吞、静默不发请求）
        if (kind === 'correct') {
          if (fullName || phone) payload.fields = {};
          if (fullName) payload.fields!.full_name = fullName;
          if (phone) payload.fields!.phone = phone;
        }
        if (kind === 'account_delete') payload.confirm = true;
        await privacyAPI.createPrivacyRequest(payload);
        setFormKind(null);
        setDetail(''); setFullName(''); setPhone('');
        Alert.alert('已提交', '请求已受理，将在 30 日内处理，可在「我的隐私请求」查看进度');
      } catch (e: any) {
        // 后端校验驳回（422 带 message，如 correct 字段为空/手机号格式）必须可见，不能静默吞掉
        Alert.alert('提交失败', e?.message || '请稍后重试');
      } finally {
        setSubmitting(false);
      }
    };

    if (meta.confirmText) {
      Alert.alert('二次确认', meta.confirmText, [
        { text: '取消', style: 'cancel' },
        { text: '确认', style: 'destructive', onPress: () => doSubmit() },
      ]);
      return;
    }
    doSubmit();
  };

  if (loading) {
    return <View style={{ flex: 1, justifyContent: 'center' }}><ActivityIndicator /></View>;
  }

  if (error && !policy && !personal) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background, padding: 24 }}>
        <Text style={{ color: Colors.textSecondary, fontSize: FontSize.md, textAlign: 'center' }}>{error}</Text>
        <Pressable
          onPress={load}
          style={{ backgroundColor: Colors.primary, borderRadius: 8, paddingHorizontal: 20, paddingVertical: 8, marginTop: 16 }}
        >
          <Text style={{ color: Colors.textWhite, fontWeight: '600' }}>重试</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1, backgroundColor: Colors.background }} contentContainerStyle={{ padding: 16, gap: 16 }}>
      <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 8 }}>
        <Text style={{ fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary }}>
          {policy?.title ?? '隐私政策'}（v{policy?.version ?? '—'}）
        </Text>
        <Text style={{ color: Colors.textSecondary, lineHeight: 20 }}>{policy?.content ?? ''}</Text>
      </View>

      <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 8 }}>
        <Text style={{ fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary }}>个人信息</Text>
        <Text style={{ color: Colors.textSecondary }}>姓名：{personal?.user.full_name ?? '—'}</Text>
        <Text style={{ color: Colors.textSecondary }}>手机号：{personal?.user.phone ?? '—'}</Text>
        <Text style={{ color: Colors.textSecondary }}>地区：{personal?.user.region ?? '—'}</Text>
        <Text style={{ color: Colors.textSecondary }}>
          历史对话：请前往「我的-收藏历史」查看本人问答记录
        </Text>
      </View>

      <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 12 }}>
        <Text style={{ fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary }}>数据权利申请</Text>
        {(Object.keys(FORM_META) as FormKind[]).map((kind) => (
          <Pressable
            key={kind}
            onPress={() => setFormKind(kind)}
            style={{ padding: 12, borderRadius: 8, backgroundColor: Colors.background }}
          >
            <Text style={{ color: Colors.textPrimary, fontWeight: '500' }}>{FORM_META[kind].title}</Text>
            <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm, marginTop: 2 }}>
              {FORM_META[kind].hint}
            </Text>
          </Pressable>
        ))}
        <Pressable
          onPress={() => navigation.navigate('PrivacyRequests')}
          style={{ padding: 12, borderRadius: 8, backgroundColor: Colors.background }}
        >
          <Text style={{ color: Colors.primary, fontWeight: '500' }}>我的隐私请求（进度查询）</Text>
        </Pressable>
      </View>

      <Modal visible={!!formKind} transparent animationType="fade" onRequestClose={() => setFormKind(null)}>
        <View style={{ flex: 1, justifyContent: 'center', padding: 24, backgroundColor: 'rgba(0,0,0,0.4)' }}>
          <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 10 }}>
            <Text style={{ fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary }}>
              {formKind ? FORM_META[formKind].title : ''}
            </Text>
            <TextInput
              value={detail}
              onChangeText={setDetail}
              placeholder="申请说明（可选，500 字内）"
              multiline
              style={{ borderWidth: 1, borderColor: Colors.border, borderRadius: 8, padding: 8, color: Colors.textPrimary }}
            />
            {formKind === 'correct' && (
              <>
                <TextInput
                  value={fullName}
                  onChangeText={setFullName}
                  placeholder="更正为的姓名（与手机号至少填一项）"
                  style={{ borderWidth: 1, borderColor: Colors.border, borderRadius: 8, padding: 8, color: Colors.textPrimary }}
                />
                <TextInput
                  value={phone}
                  onChangeText={setPhone}
                  placeholder="更正为的手机号（11 位）"
                  keyboardType="phone-pad"
                  style={{ borderWidth: 1, borderColor: Colors.border, borderRadius: 8, padding: 8, color: Colors.textPrimary }}
                />
              </>
            )}
            <View style={{ flexDirection: 'row', gap: 12, justifyContent: 'flex-end' }}>
              <Pressable onPress={() => setFormKind(null)} style={{ padding: 8 }}>
                <Text style={{ color: Colors.textSecondary }}>取消</Text>
              </Pressable>
              <Pressable
                onPress={() => formKind && submit(formKind)}
                disabled={submitting}
                style={{ padding: 8 }}
              >
                <Text style={{ color: Colors.primary, fontWeight: '600' }}>{submitting ? '提交中…' : '提交'}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}
