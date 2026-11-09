import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { PromiseCard } from '../../components/SwipeItem'
import { DotGrid, Label, Orb } from '../../components/ui'
import { refresh, useData, useMode } from '../../lib/api'
import { serif, usePalette } from '../../lib/theme'
import { keyOf, type Item, type TodaySummary } from '../../lib/types'

function greeting(d = new Date()) {
  const h = d.getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

export default function Today() {
  const c = usePalette()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const mode = useMode()
  const s = useData<TodaySummary>('/api/today')
  const all = useData<Item[]>('/api/all')
  const quiet = (all.data ?? []).filter((x) => !x.live)
  const now = new Date()
  const n = s.data?.today.length ?? 0
  const count = n === 0 ? 'nothing' : n === 1 ? 'one thing' : `${['', '', 'two', 'three'][n] ?? n} things`
  return (
    <ScrollView style={{ backgroundColor: c.ground }} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}
                refreshControl={<RefreshControl refreshing={false} onRefresh={refresh} />}>
      <DotGrid height={260} />
      <View style={styles.top}>
        <Text style={[styles.day, { color: c.ink }]}>{now.getDate()}</Text>
        <View style={[styles.sun, { backgroundColor: c.accent }]} />
        <View style={{ flex: 1 }} />
        <View style={{ alignItems: 'flex-end' }}>
          <Text style={{ color: c.ink2, fontSize: 15, fontWeight: '600' }}>{now.toLocaleDateString(undefined, { weekday: 'long' })}</Text>
          <Text style={{ color: c.ink3, fontSize: 15 }}>{now.toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}</Text>
        </View>
      </View>
      <Text style={[styles.hello, { color: c.ink }]}>{greeting(now)},</Text>
      <Text style={[styles.hello, { color: c.ink3, marginBottom: 22 }]}>
        you have <Text style={{ color: c.ink }}>{s.data ? count : '…'}</Text> {n ? 'to do today.' : 'owed today.'}
      </Text>
      {mode === 'demo' && (
        <View style={[styles.demo, { backgroundColor: c.raised }]}>
          <Ionicons name="flask-outline" size={13} color={c.ink2} />
          <Text style={{ color: c.ink2, fontSize: 12, fontWeight: '600' }}>Demo: made-up people</Text>
        </View>
      )}
      {s.error ? <Text style={[styles.note, { color: c.ink2 }]}>Couldn’t load: {s.error}</Text> : null}
      {s.data?.today.map((it) => <PromiseCard key={keyOf(it)} item={it} />)}
      {s.data && !n ? (
        <View style={[styles.empty, { borderColor: c.line }]}>
          <Text style={{ fontFamily: serif, fontSize: 20, color: c.ink, lineHeight: 27 }}>Nothing you said you’d do needs you today.</Text>
          <Text style={{ color: c.ink2, fontSize: 14, marginTop: 6, lineHeight: 20 }}>
            Older things are assumed done, unless someone chases you about them.
          </Text>
        </View>
      ) : null}
      {n ? <Text style={[styles.note, { color: c.ink3 }]}>Swipe left when it’s done, right if it’s not needed.</Text> : null}
      {quiet.length ? (
        <>
          <Label>Quiet · assumed done</Label>
          <Pressable onPress={() => router.navigate('/all')} style={[styles.pile, { backgroundColor: c.card, borderColor: c.line }]}>
            <View style={styles.faces}>
              {quiet.slice(0, 4).map((q, i) => (
                <View key={keyOf(q)} style={{ marginLeft: i ? -10 : 0, borderRadius: 20, borderWidth: 2, borderColor: c.card }}>
                  <Orb name={q.name} size={30} />
                </View>
              ))}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: c.ink, fontSize: 15, fontWeight: '600' }}>{quiet.length} quiet {quiet.length === 1 ? 'thing' : 'things'}</Text>
              <Text style={{ color: c.ink2, fontSize: 13 }} numberOfLines={1}>{quiet.slice(0, 3).map((q) => q.name.split(' ')[0]).join(', ')}{quiet.length > 3 ? ' and others' : ''}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={c.ink3} />
          </Pressable>
        </>
      ) : null}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  top: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingTop: 18 },
  day: { fontSize: 52, fontWeight: '800', letterSpacing: -2 },
  sun: { width: 14, height: 14, borderRadius: 7, marginLeft: 10, marginTop: 6 },
  hello: { fontSize: 24, fontWeight: '700', letterSpacing: -0.4, paddingHorizontal: 20, lineHeight: 30 },
  demo: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', marginLeft: 20, marginBottom: 14, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  note: { fontSize: 13, paddingHorizontal: 20, marginTop: 2 },
  empty: { marginHorizontal: 16, borderRadius: 22, borderWidth: 1, borderStyle: 'dashed', padding: 20 },
  pile: { marginHorizontal: 16, borderRadius: 18, borderWidth: StyleSheet.hairlineWidth, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12 },
  faces: { flexDirection: 'row' },
})
