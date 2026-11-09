import Ionicons from '@expo/vector-icons/Ionicons'
import { Tabs } from 'expo-router/js-tabs'
import type { ColorValue } from 'react-native'
import { useData } from '../../lib/api'
import { usePalette } from '../../lib/theme'
import type { TodaySummary } from '../../lib/types'

export default function TabsLayout() {
  const c = usePalette()
  const today = useData<TodaySummary>('/api/today')
  const n = today.data?.today.length ?? 0
  const icon = (name: keyof typeof Ionicons.glyphMap, filled: keyof typeof Ionicons.glyphMap) =>
    ({ color, focused, size }: { color: ColorValue; focused: boolean; size: number }) => <Ionicons name={focused ? filled : name} size={size - 2} color={color as string} />
  return (
    <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: c.ink, tabBarInactiveTintColor: c.ink3,
                           tabBarStyle: { backgroundColor: c.card, borderTopColor: c.line } }}>
      <Tabs.Screen name="index" options={{ title: 'Today', tabBarIcon: icon('sunny-outline', 'sunny'),
                                          tabBarBadge: n || undefined, tabBarBadgeStyle: { backgroundColor: c.accent, color: '#fff' } }} />
      <Tabs.Screen name="people" options={{ title: 'People', tabBarIcon: icon('people-outline', 'people') }} />
      <Tabs.Screen name="all" options={{ title: 'All open', tabBarIcon: icon('list-outline', 'list') }} />
      <Tabs.Screen name="sources" options={{ title: 'Sources', tabBarIcon: icon('git-network-outline', 'git-network') }} />
    </Tabs>
  )
}
