import { Tabs } from 'expo-router/js-tabs'
import { TabBar } from '../../components/TabBar'
import { useData } from '../../lib/api'
import type { TodaySummary } from '../../lib/types'

export default function TabsLayout() {
  const today = useData<TodaySummary>('/api/today')
  return (
    <Tabs tabBar={(props) => <TabBar {...props} badge={today.data?.today.length} />} screenOptions={{ headerShown: false }}>
      <Tabs.Screen name="index" options={{ title: 'Today' }} />
      <Tabs.Screen name="people" options={{ title: 'People' }} />
      <Tabs.Screen name="all" options={{ title: 'All open' }} />
      <Tabs.Screen name="sources" options={{ title: 'Sources' }} />
    </Tabs>
  )
}
