/**
 * 医生搜索页 - 搜索 + 筛选 + 字母索引
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import EmptyState from '../../components/EmptyState';
import Icon from '../../components/Icon';
import { ActionIcons } from '../../components/Icon';
import { hcpAPI } from '../../api/hcp';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { HCP } from '../../types';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const DEPARTMENTS = ['全部', '肿瘤科', '心内科', '呼吸科', '消化科', '神经内科'];
const REGIONS = ['全部', '华东', '华南', '华北', '华中', '西南', '西北'];

export default function HCPSearchScreen() {
  const navigation = useNavigation<Nav>();
  const [hcps, setHcps] = useState<HCP[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [deptFilter, setDeptFilter] = useState('全部');
  const [regionFilter, setRegionFilter] = useState('全部');
  const [showFilters, setShowFilters] = useState(false);
  const [error, setError] = useState('');

  const loadHCPs = useCallback(async () => {
    try {
      const params: Record<string, any> = { page: 1, page_size: 50 };
      if (searchText) params.name = searchText;
      if (deptFilter !== '全部') params.department = deptFilter;
      if (regionFilter !== '全部') params.region = regionFilter;
      const result = await hcpAPI.list(params);
      setHcps(result.items || []);
      setError('');
    } catch (e: any) {
      // G4：失败不再静默置空 —— 断网时置空会误显示"暂无医生数据"，改错误态 + 重试
      setError(e?.message || '医生数据加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, [searchText, deptFilter, regionFilter]);

  useEffect(() => {
    loadHCPs();
  }, [loadHCPs]);

  const handleRetry = () => {
    setLoading(true);
    setError('');
    loadHCPs();
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadHCPs();
    setRefreshing(false);
  };

  const renderHCP = ({ item }: { item: HCP }) => (
    <TouchableOpacity
      style={[styles.hcpCard, Shadow.card]}
      onPress={() =>
        navigation.navigate('HCPDetail', { hcpId: item.id })
      }
      activeOpacity={0.7}
    >
      <View
        style={[styles.avatar, { backgroundColor: Colors.primary }]}
      >
        <Text style={styles.avatarText}>
          {item.name?.charAt(0) || '医'}
        </Text>
      </View>
      <View style={styles.hcpInfo}>
        <View style={styles.nameRow}>
          <Text style={styles.hcpName}>{item.name}</Text>
          {item.influence_level === 'high' && (
            <Text style={styles.influence}>高影响力</Text>
          )}
        </View>
        <Text style={styles.hcpDept}>
          {item.hospital} · {item.department}
        </Text>
        <Text style={styles.hcpTitle}>{item.title}</Text>
        {item.tags && item.tags.length > 0 && (
          <View style={styles.tagRow}>
            {item.tags.slice(0, 3).map((tag, i) => (
              <View key={i} style={styles.tag}>
                <Text style={styles.tagText}>{tag}</Text>
              </View>
            ))}
          </View>
        )}
      </View>
      <Text style={styles.arrow}>›</Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {/* 搜索栏 */}
      <View style={styles.searchBar}>
        <View style={styles.searchInputRow}>
          <Icon name={ActionIcons.search} size={18} color={Colors.textHint} />
          <TextInput
            style={styles.searchInput}
            placeholder="搜索医生姓名、医院..."
            placeholderTextColor={Colors.textHint}
            value={searchText}
            onChangeText={setSearchText}
            returnKeyType="search"
            onSubmitEditing={loadHCPs}
          />
          {searchText.length > 0 && (
            <TouchableOpacity onPress={() => { setSearchText(''); loadHCPs(); }}>
              <Icon name={ActionIcons.close} size={18} color={Colors.textHint} />
            </TouchableOpacity>
          )}
        </View>
        <TouchableOpacity
          style={styles.filterToggle}
          onPress={() => setShowFilters(!showFilters)}
        >
          <Icon name={ActionIcons.filter} size={20} color={Colors.textWhite} />
        </TouchableOpacity>
      </View>

      {/* 筛选区 */}
      {showFilters && (
        <View style={styles.filterPanel}>
          <Text style={styles.filterLabel}>科室</Text>
          <View style={styles.filterRow}>
            {DEPARTMENTS.map((d) => (
              <TouchableOpacity
                key={d}
                style={[
                  styles.filterChip,
                  deptFilter === d && styles.filterChipActive,
                ]}
                onPress={() => setDeptFilter(d)}
              >
                <Text
                  style={[
                    styles.filterChipText,
                    deptFilter === d && styles.filterChipTextActive,
                  ]}
                >
                  {d}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.filterLabel, { marginTop: Spacing.md }]}>
            区域
          </Text>
          <View style={styles.filterRow}>
            {REGIONS.map((r) => (
              <TouchableOpacity
                key={r}
                style={[
                  styles.filterChip,
                  regionFilter === r && styles.filterChipActive,
                ]}
                onPress={() => setRegionFilter(r)}
              >
                <Text
                  style={[
                    styles.filterChipText,
                    regionFilter === r && styles.filterChipTextActive,
                  ]}
                >
                  {r}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}

      {/* 列表 */}
      <FlatList
        data={hcps}
        renderItem={renderHCP}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            colors={[Colors.primary]}
          />
        }
        ListEmptyComponent={
          loading ? (
            <View style={styles.loadingArea}>
              <ActivityIndicator size="large" color={Colors.primary} />
            </View>
          ) : error && hcps.length === 0 ? (
            // G4：加载失败显示错误 + 重试（与全站错误态一致），不伪装成"暂无医生数据"
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
              <TouchableOpacity style={styles.retryBtn} onPress={handleRetry} activeOpacity={0.8}>
                <Text style={styles.retryText}>重试</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <EmptyState
              icon="doctor"
              title="暂无医生数据"
              description="联系管理员导入医生数据"
            />
          )
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  // 搜索
  searchBar: {
    backgroundColor: Colors.primary,
    paddingTop: 52,
    paddingBottom: Spacing.md,
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  searchInputRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.full,
    paddingHorizontal: Spacing.md,
    gap: Spacing.sm,
  },
  searchIcon: { fontSize: 16 },
  searchInput: {
    flex: 1,
    fontSize: FontSize.md,
    color: Colors.textPrimary,
    paddingVertical: 10,
  },
  clearBtn: { color: Colors.textHint, fontSize: 16, padding: 4 },
  filterToggle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.2)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterIcon: { fontSize: 18 },
  // 筛选面板
  filterPanel: {
    backgroundColor: Colors.white,
    padding: Spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  filterLabel: {
    fontSize: FontSize.sm,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
  },
  filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  filterChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.background,
  },
  filterChipActive: { backgroundColor: Colors.primary },
  filterChipText: { fontSize: FontSize.xs, color: Colors.textSecondary },
  filterChipTextActive: { color: Colors.textWhite, fontWeight: '600' },
  // 列表
  list: { padding: Spacing.lg },
  loadingArea: { padding: Spacing.xxxl, alignItems: 'center' },
  errorBox: { alignItems: 'center', padding: Spacing.xxxl },
  errorText: {
    fontSize: FontSize.md, color: Colors.danger,
    marginBottom: Spacing.lg, paddingHorizontal: Spacing.xl, textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  hcpCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
  hcpInfo: { flex: 1, gap: 2 },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  hcpName: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  influence: {
    fontSize: 10,
    color: Colors.warning,
    backgroundColor: '#fef3c7',
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: BorderRadius.sm,
    fontWeight: '600',
    overflow: 'hidden',
  },
  hcpDept: { fontSize: FontSize.sm, color: Colors.textSecondary },
  hcpTitle: { fontSize: FontSize.xs, color: Colors.textHint },
  tagRow: { flexDirection: 'row', gap: Spacing.xs, marginTop: 4 },
  tag: {
    backgroundColor: Colors.background,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  tagText: { fontSize: 10, color: Colors.textSecondary },
  arrow: { fontSize: 24, color: Colors.textHint },
});
