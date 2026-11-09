import { FloatingTabBar, type TabItem } from '@soloyolo/design-system'
import { Tabs } from 'expo-router/js-tabs'
import { useData } from '../../lib/api'
import type { TodaySummary } from '../../lib/types'

export default function TabsLayout() {
  const today = useData<TodaySummary>('/api/today')
  const items: TabItem[] = [
    { key: 'index', label: 'Today', icon: 'sunny-outline', iconActive: 'sunny', dot: !!today.data?.today.length },
    { key: 'people', label: 'People', icon: 'people-outline', iconActive: 'people' },
    { key: 'all', label: 'All open', icon: 'albums-outline', iconActive: 'albums' },
    { key: 'sources', label: 'Sources', icon: 'git-network-outline', iconActive: 'git-network' },
  ]
  return (
    <Tabs screenOptions={{ headerShown: false }}
          tabBar={({ state, navigateToTab }) => (
            <FloatingTabBar items={items} active={state.routes[state.index]!.name}
                            onSelect={(name) => { const r = state.routes.find((x) => x.name === name); if (r) navigateToTab(r.key) }} />
          )}>
      <Tabs.Screen name="index" options={{ title: 'Today' }} />
      <Tabs.Screen name="people" options={{ title: 'People' }} />
      <Tabs.Screen name="all" options={{ title: 'All open' }} />
      <Tabs.Screen name="sources" options={{ title: 'Sources' }} />
    </Tabs>
  )
}
