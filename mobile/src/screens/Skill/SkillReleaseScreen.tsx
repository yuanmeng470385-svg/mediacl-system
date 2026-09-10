/**
 * 发布 Skill（三期 J）：填写名称/说明/话术内容 + 风格标签 + 沟通风格权重 + 匿名开关，
 * 提交后进入审核（audit_status=pending），审核通过后上架广场。
 * 三期 P：携带 draft 参数进入（SkillExtractScreen replace 过来）时预填各字段；
 * 手动进入（无草稿）时顶部展示「从陪练对话生成」入口引导走 AI 提取链路。
 */
import React, { useState } from 'react';
import {
  Alert, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { plazaAPI } from '../../api/practice';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Route = RouteProp<RootStackParamList, 'SkillRelease'>;

const STYLE_TAG_OPTIONS = ['严谨学术', '亲和力', '幽默', '专业'];
const FORMAL_OPTIONS = ['非常严谨', '标准学术', '略带亲和力'];
const LENGTH_OPTIONS = ['简洁', '标准', '详尽'];
// 与后端 specialists.py / skill_packages.py 的 opening_mode 白名单逐字对齐（决策 12）
const OPENING_OPTIONS = ['直切主题', '先寒暄再进入'];

export default function SkillReleaseScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  // 三期 P：陪练提取草稿（枚举已过后端白名单过滤，预填即合法值）；手动进入时为 undefined
  const draft = route.params?.draft;
  const [name, setName] = useState(draft?.name ?? '');
  const [description, setDescription] = useState(draft?.description ?? '');
  const [content, setContent] = useState(draft?.content ?? '');
  const [styleTags, setStyleTags] = useState<string[]>(
    Array.isArray(draft?.style_tags) ? draft.style_tags : [],
  );
  const [formalLevel, setFormalLevel] = useState(draft?.skill_weights?.formal_level ?? FORMAL_OPTIONS[1]);
  const [replyLength, setReplyLength] = useState(draft?.skill_weights?.reply_length ?? LENGTH_OPTIONS[1]);
  const [openingMode, setOpeningMode] = useState(draft?.skill_weights?.opening_mode ?? OPENING_OPTIONS[0]);
  const [isAnonymous, setIsAnonymous] = useState(draft?.is_anonymous ?? false);
  const [submitting, setSubmitting] = useState(false);

  const toggleTag = (tag: string) => {
    setStyleTags((prev) => (
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    ));
  };

  const submit = async () => {
    if (!name.trim()) { Alert.alert('请填写名称', 'Skill 名称不能为空'); return; }
    if (!description.trim()) { Alert.alert('请填写说明', '治疗领域/说明不能为空'); return; }
    if (!content.trim()) { Alert.alert('请填写话术内容', '话术内容不能为空'); return; }

    setSubmitting(true);
    try {
      await plazaAPI.releaseSkill({
        name: name.trim(),
        description: description.trim(),
        content: content.trim(),
        style_tags: styleTags.length > 0 ? styleTags : undefined,
        skill_weights: {
          formal_level: formalLevel,
          reply_length: replyLength,
          opening_mode: openingMode,
        },
        is_anonymous: isAnonymous,
        // 审核溯源（2026-09-01；2026-09-10 扩拜访）：提取链路带来的来源会话/拜访
        // 原样回传，后端校验归属后留档
        source_session_ids: draft?.source_session_ids ?? undefined,
        source_visit_ids: draft?.source_visit_ids ?? undefined,
      });
      Alert.alert('已提交', 'Skill 已进入审核，审核通过后上架广场', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('提交失败', err?.message || '请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>发布 Skill</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {/* 从陪练对话生成入口（三期 P）：无草稿时展示 */}
        {!draft && (
          <TouchableOpacity
            style={styles.extractEntry}
            onPress={() => navigation.navigate('SkillExtract')}
            activeOpacity={0.7}
          >
            <View style={styles.extractIconBox}>
              <Icon name="creation" size={18} color={Colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.extractTitle}>从陪练对话生成</Text>
              <Text style={styles.extractHint}>选择已结束的陪练会话，由 AI 提取你的说话风格</Text>
            </View>
            <Icon name="chevron-right" size={18} color={Colors.textHint} />
          </TouchableOpacity>
        )}

        {/* 基础信息 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>基础信息</Text>
          <Text style={styles.label}>名称</Text>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="如：亲和力型"
            placeholderTextColor={Colors.textHint}
          />
          <Text style={styles.label}>治疗领域 / 说明</Text>
          <TextInput
            style={styles.input}
            value={description}
            onChangeText={setDescription}
            placeholder="如：心内科"
            placeholderTextColor={Colors.textHint}
          />
          <Text style={styles.label}>话术内容</Text>
          <TextInput
            style={[styles.input, styles.multiline]}
            value={content}
            onChangeText={setContent}
            placeholder="填写话术素材内容"
            placeholderTextColor={Colors.textHint}
            multiline
            textAlignVertical="top"
          />
        </View>

        {/* 风格标签（多选） */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>风格标签（可多选）</Text>
          <View style={styles.chipWrap}>
            {STYLE_TAG_OPTIONS.map((tag) => {
              const active = styleTags.includes(tag);
              return (
                <TouchableOpacity
                  key={tag}
                  style={[styles.chip, active && styles.chipActive]}
                  onPress={() => toggleTag(tag)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{tag}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* 沟通风格权重（三选） */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>沟通风格权重</Text>
          <Picker label="正式程度" options={FORMAL_OPTIONS} value={formalLevel} onChange={setFormalLevel} />
          <Picker label="回复长度" options={LENGTH_OPTIONS} value={replyLength} onChange={setReplyLength} />
          <Picker label="开场方式" options={OPENING_OPTIONS} value={openingMode} onChange={setOpeningMode} />
        </View>

        {/* 匿名开关 */}
        <View style={[styles.card, Shadow.card]}>
          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.switchLabel}>匿名发布</Text>
              <Text style={styles.switchHint}>开启后广场不展示发布者信息</Text>
            </View>
            <Switch
              value={isAnonymous}
              onValueChange={setIsAnonymous}
              trackColor={{ false: Colors.border, true: Colors.primaryLight }}
              thumbColor={isAnonymous ? Colors.primary : Colors.white}
            />
          </View>
        </View>

        {/* 提交 */}
        <TouchableOpacity
          style={[styles.submitBtn, submitting && { opacity: 0.6 }]}
          disabled={submitting}
          onPress={submit}
          activeOpacity={0.7}
        >
          <Icon name="send" size={18} color={Colors.textWhite} />
          <Text style={styles.submitText}>{submitting ? '提交中…' : '提交审核'}</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

function Picker({ label, options, value, onChange }: {
  label: string; options: string[]; value: string; onChange: (v: string) => void;
}) {
  return (
    <View style={styles.picker}>
      <Text style={styles.pickerLabel}>{label}</Text>
      <View style={styles.chipWrap}>
        {options.map((opt) => {
          const active = value === opt;
          return (
            <TouchableOpacity
              key={opt}
              style={[styles.chip, active && styles.chipActive]}
              onPress={() => onChange(opt)}
              activeOpacity={0.7}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{opt}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  extractEntry: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    borderWidth: 1, borderColor: Colors.primary, borderRadius: BorderRadius.md,
    backgroundColor: Colors.primarySurface, padding: Spacing.md, marginBottom: Spacing.md,
  },
  extractIconBox: {
    width: 36, height: 36, borderRadius: 10, backgroundColor: Colors.white,
    alignItems: 'center', justifyContent: 'center',
  },
  extractTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.primary },
  extractHint: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 2 },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  label: { fontSize: FontSize.xs, color: Colors.textSecondary, marginBottom: Spacing.xs, marginTop: Spacing.xs },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    fontSize: FontSize.md, color: Colors.textPrimary, backgroundColor: Colors.white,
  },
  multiline: { minHeight: 100, paddingTop: Spacing.md },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  chip: {
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.white,
  },
  chipActive: { backgroundColor: Colors.primarySurface, borderColor: Colors.primary },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.primary, fontWeight: '600' },
  picker: { marginBottom: Spacing.sm },
  pickerLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, marginBottom: Spacing.xs },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  switchLabel: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  switchHint: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  submitBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.sm, marginTop: Spacing.xs,
  },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
