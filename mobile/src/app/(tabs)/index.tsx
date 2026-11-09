import { Banner, Chip, EmptyState, Icon, PromiseCard, QuietPile, Row, SectionLabel, Text, TodayHeader, formatRelative, useTheme } from '@soloyolo/design-system'
import { useRouter } from 'expo-router'
import { useState } from 'react'
import { RefreshControl, ScrollView, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { refresh, useData, useMode } from '../../lib/api'
import { useMarks } from '../../lib/marks'
import { keyOf, type Item, type Status, type TodaySummary } from '../../lib/types'

export default function Today() {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const mode = useMode()
  const marks = useMarks()
  const s = useData<TodaySummary>('/api/today')
  const all = useData<Item[]>('/api/all')
  const status = useData<Status>('/api/status')
  const wa = status.data?.networks.find((x) => x.network === 'whatsapp')
  const [openedAt] = useState(() => Date.now() / 1000) // the clock is read once, when Today opens
  const stale = wa && openedAt - wa.last > 12 * 3600
  const quiet = (all.data ?? []).filter((x) => !x.live)
  const n = s.data?.today.length ?? 0
  const open = (it: Item) => router.push({ pathname: '/person/[id]', params: { id: String(it.person_id), focus: String(it.source_message_id) } })
  return (
    <ScrollView style={{ backgroundColor: t.color.background }} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}
                refreshControl={<RefreshControl refreshing={false} onRefresh={refresh} />}>
      <TodayHeader count={s.data ? n : null} />
      {mode === 'demo' && (
        <Row padX="xl" style={{ marginBottom: t.space.md + 2 }}>
          <Row gap="xs"><Icon name="flask-outline" size="xs" tone="secondary" /><Chip label="Demo: made-up people" /></Row>
        </Row>
      )}
      {stale ? (
        <View style={{ paddingHorizontal: t.space.lg, marginBottom: t.space.md + 2 }}>
          <Banner tone="warning" title="WhatsApp isn’t syncing"
                  body={`Last message arrived ${formatRelative(wa!.last)}. New promises won’t show up until your Mac syncs again.`}
                  action={{ label: 'Open sources', onPress: () => router.navigate('/sources') }} />
        </View>
      ) : null}
      {s.error ? <Text variant="small" tone="secondary" style={{ paddingHorizontal: t.space.xl }}>Couldn’t load: {s.error}</Text> : null}
      {s.data?.today.map((it) => (
        <PromiseCard key={keyOf(it)} item={it} onPress={() => open(it)} onDone={() => marks.done(it)} onDismiss={() => marks.dismiss(it)} />
      ))}
      {s.data && !n ? (
        <EmptyState title="Nothing you said you’d do needs you today." body="Older things are assumed done, unless someone chases you about them." />
      ) : null}
      {n ? <Text variant="small" tone="tertiary" style={{ paddingHorizontal: t.space.xl }}>Swipe left when it’s done, right if it’s not needed.</Text> : null}
      {quiet.length ? (
        <>
          <SectionLabel>Quiet · assumed done</SectionLabel>
          <QuietPile names={quiet.map((q) => q.name)} onPress={() => router.navigate('/all')} />
        </>
      ) : null}
    </ScrollView>
  )
}
