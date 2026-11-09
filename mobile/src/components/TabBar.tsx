// Mesh's floating pill tab bar: icons only, the current one dark, sitting over the content.
import Ionicons from '@expo/vector-icons/Ionicons'
import type { BottomTabBarProps } from 'expo-router/js-tabs'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { usePalette } from '../lib/theme'

const ICONS: Record<string, [keyof typeof Ionicons.glyphMap, keyof typeof Ionicons.glyphMap]> = {
  index: ['sunny-outline', 'sunny'],
  people: ['people-outline', 'people'],
  all: ['albums-outline', 'albums'],
  sources: ['git-network-outline', 'git-network'],
}

export function TabBar({ state, descriptors, navigateToTab, badge }: BottomTabBarProps & { badge?: number }) {
  const c = usePalette()
  const insets = useSafeAreaInsets()
  return (
    <View pointerEvents="box-none" style={[styles.wrap, { bottom: Math.max(insets.bottom, 12) + 4 }]}>
      <View style={[styles.pill, { backgroundColor: c.pill, borderColor: c.line, shadowColor: '#2b2310' }]}>
        {state.routes.map((route, i) => {
          const focused = state.index === i
          const label = descriptors[route.key]?.options.title ?? route.name
          const [off, on] = ICONS[route.name] ?? ['ellipse-outline', 'ellipse']
          return (
            <Pressable key={route.key} accessibilityRole="tab" accessibilityLabel={label} accessibilityState={{ selected: focused }}
                       onPress={() => { if (!focused) navigateToTab(route.key) }}
                       style={[styles.tab, focused && { backgroundColor: c.black }]}>
              <Ionicons name={focused ? on : off} size={20} color={focused ? c.onBlack : c.ink2} />
              {focused ? <Text style={{ color: c.onBlack, fontSize: 13, fontWeight: '600' }}>{label}</Text> : null}
              {route.name === 'index' && badge && !focused ? <View style={[styles.badge, { backgroundColor: c.accent }]} /> : null}
            </Pressable>
          )
        })}
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  pill: { flexDirection: 'row', gap: 4, padding: 6, borderRadius: 999, borderWidth: StyleSheet.hairlineWidth,
          shadowOpacity: 0.12, shadowRadius: 20, shadowOffset: { width: 0, height: 8 }, elevation: 6 },
  tab: { flexDirection: 'row', alignItems: 'center', gap: 6, height: 44, minWidth: 48, paddingHorizontal: 14, borderRadius: 999, justifyContent: 'center' },
  badge: { position: 'absolute', top: 9, right: 12, width: 7, height: 7, borderRadius: 4 },
})
