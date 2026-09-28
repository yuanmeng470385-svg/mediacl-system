import React from 'react';
import { View, Text } from 'react-native';
import { BRAND } from '../brandConfig';

/**
 * 全局品牌条（v1.1.2）：挂在 App 根部导航器上方 —— 所有页面顶部常驻
 * 公司标签（字标 + 公司全称 + 标语，品牌主色底）。BRAND=null（母版/开发）渲染 null。
 */
export default function BrandBar() {
  if (!BRAND) return null;
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 14,
        paddingVertical: 5,
        backgroundColor: BRAND.primary,
      }}
    >
      <View
        style={{
          width: 18,
          height: 18,
          borderRadius: 5,
          backgroundColor: 'rgba(255,255,255,0.25)',
          alignItems: 'center',
          justifyContent: 'center',
          marginRight: 8,
        }}
      >
        <Text style={{ color: '#FFFFFF', fontSize: 11, fontWeight: '700' }}>{BRAND.char}</Text>
      </View>
      <Text style={{ color: '#FFFFFF', fontSize: 12, fontWeight: '600' }}>{BRAND.name}</Text>
      <Text
        numberOfLines={1}
        style={{ color: 'rgba(255,255,255,0.8)', fontSize: 11, marginLeft: 10, flexShrink: 1 }}
      >
        {BRAND.tagline}
      </Text>
    </View>
  );
}
