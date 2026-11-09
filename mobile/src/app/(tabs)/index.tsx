import { Link } from 'expo-router'
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { ItemRow, TodayCard } from '../../components/SwipeItem'
import { LargeTitle, SectionTitle } from '../../components/ui'
import { refresh, useData, useMode } from '../../lib/api'
import { usePalette } from '../../lib/theme'
import type { Item, TodaySummary } from '../../lib/types'
import { keyOf } from '../../lib/types'

export default function Today() {
  const c = usePalette()
  const insets = useSafeAreaInsets()
  const mode = useMode()
  const s = useData<TodaySummary>('/api/today')
  const all = useData<Item[]>('/api/all')
  const quiet = (all.data ?? []).filter((x) => !x.live).slice(0, 4)
  const date = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
  const n = s.data?.today.length ?? 0
  return (
    <ScrollView style={{ backgroundColor: c.ground }} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 40 }}
                refreshControl={<RefreshControl refreshing={false} onRefresh={refresh} />}>
      {mode === 'demo' && (
        <View style={[styles.demo, { backgroundColor: c.raised }]}>
          <Text style={{ color: c.ink2, fontSize: 12, fontWeight: '600' }}>DEMO · MADE-UP PEOPLE</Text>
        </View>
      )}
      <LargeTitle title="Today" subtitle={s.data ? `${date} · ${n ? `${n} ${n === 1 ? 'thing' : 'things'}` : 'nothing owed'}` : date} />
      <View style={{ height: 12 }} />
      {s.error ? <Text style={[styles.note, { color: c.ink2 }]}>Couldn’t load: {s.error}</Text> : null}
      {s.data?.today.map((it) => <TodayCard key={keyOf(it)} item={it} />)}
      {s.data && !n ? (
        <View style={[styles.empty, { backgroundColor: c.card }]}>
          <Text style={{ color: c.ink, fontSize: 17, fontWeight: '600' }}>Nothing needs you today</Text>
          <Text style={{ color: c.ink2, fontSize: 15, marginTop: 4, lineHeight: 20 }}>
            Anything older than a few days is assumed done, unless someone chases you about it.
          </Text>
        </View>
      ) : null}
      {n ? <Text style={[styles.note, { color: c.ink3 }]}>Swipe left when it’s done, right if it’s not needed.</Text> : null}
      {quiet.length ? (
        <>
          <SectionTitle>{`Quiet · assumed done · ${s.data?.quiet ?? quiet.length}`}</SectionTitle>
          <View style={[styles.group, { backgroundColor: c.card }]}>
            {quiet.map((it, i) => <ItemRow key={keyOf(it)} item={it} showName last={i === quiet.length - 1} />)}
          </View>
          <Link href="/all" style={[styles.more, { color: c.accent }]}>See all {s.data?.open ?? ''} open</Link>
        </>
      ) : null}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  demo: { alignSelf: 'flex-end', marginRight: 16, marginTop: 6, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  note: { fontSize: 13, paddingHorizontal: 20, marginTop: 2, marginBottom: 4 },
  empty: { marginHorizontal: 16, borderRadius: 16, padding: 16 },
  group: { marginHorizontal: 16, borderRadius: 14, overflow: 'hidden' },
  more: { fontSize: 15, fontWeight: '600', paddingHorizontal: 20, paddingVertical: 12 },
})
