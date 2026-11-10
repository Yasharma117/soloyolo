import { ActionMenu, Banner, CardSkeleton, CheckInCard, Chip, InsightCard, EmptyState, Icon, InlineError, PromiseCard, TopBar, Wash, useScrollChrome, QuietPile, Row, SectionLabel, Text, TodayHeader, formatRelative, useTheme } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useState } from 'react'
import { RefreshControl, View } from 'react-native'
import Animated from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { refresh, useData, useMode } from '../../lib/api'
import { useMarks } from '../../lib/marks'
import { sayInsight } from '../../lib/insight'
import { keyOf, type Insight, type Item, type Status, type TodaySummary } from '../../lib/types'

export default function Today() {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const mode = useMode()
  const marks = useMarks()
  const chrome = useScrollChrome()
  // ?state=empty|error|loading shows that state on demand, for review (Markon's page-state; listed in /screens)
  const { state: preview } = useLocalSearchParams<{ state?: 'empty' | 'error' | 'loading' }>()
  const live = useData<TodaySummary>('/api/today')
  const s = preview === 'loading' ? { data: null, error: null, loading: true }
    : preview === 'error' ? { data: null, error: 'preview', loading: false }
    : preview === 'empty' ? { data: { today: [], live: 0, quiet: 0, open: 0 }, error: null, loading: false } : live
  const all = useData<Item[]>('/api/all')
  const status = useData<Status>('/api/status')
  const insight = sayInsight(useData<Insight>('/api/insight').data)
  const wa = status.data?.networks.find((x) => x.network === 'whatsapp')
  const [openedAt] = useState(() => Date.now() / 1000) // the clock is read once, when Today opens
  const stale = wa && openedAt - wa.last > 12 * 3600
  const quiet = (all.data ?? []).filter((x) => !x.live)
  // the Still on? deck: quiet ones asked about one at a time; Skip just moves on (it stays quiet, so assumed done)
  const [seen, setSeen] = useState<string[]>([])
  const deck = quiet.filter((x) => !x.suggestion && !seen.includes(keyOf(x)))
  const next = (it: Item) => setSeen((s) => [...s, keyOf(it)])
  const [menu, setMenu] = useState<Item | null>(null) // the card a long-press lifted
  const n = s.data?.today.length ?? 0
  const open = (it: Item) => router.push({ pathname: '/person/[id]', params: { id: String(it.person_id), focus: String(it.source_message_id) } })
  return (
    <View style={{ flex: 1, backgroundColor: t.color.background }}>
    <Animated.ScrollView showsVerticalScrollIndicator={false} onScroll={chrome.onScroll} scrollEventThrottle={16} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}
                refreshControl={<RefreshControl refreshing={false} onRefresh={refresh} />}>
      <Wash />
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
      {s.error ? <InlineError title="We couldn’t load today’s list." body="soloyolo on your Mac didn’t answer. Check it’s running, then try again." onRetry={refresh} /> : null}
      {s.loading && !s.data && !s.error ? <><CardSkeleton /><CardSkeleton /><CardSkeleton /></> : null}
      {s.data?.today.map((it) => (
        <PromiseCard key={keyOf(it)} item={it} onPress={() => open(it)} onDone={() => marks.done(it)} onDismiss={() => marks.dismiss(it)} onSettle={() => marks.done(it)} onLongPress={() => setMenu(it)} />
      ))}
      {s.data && !n ? (
        <EmptyState title="Nothing you said you’d do needs you today." body="Older things are assumed done, unless someone chases you about them." />
      ) : null}
      {n ? <Text variant="small" tone="tertiary" style={{ paddingHorizontal: t.space.xl }}>Swipe left when it’s done, right if it’s not needed. Hold a card for more.</Text> : null}
      {deck.length && s.data ? (
        <>
          <SectionLabel>{`Still on? · ${deck.length}`}</SectionLabel>
          <CheckInCard item={deck[0]!} waiting={deck.length - 1} onSkip={() => next(deck[0]!)}
                       yes={{ label: 'Still on', onPress: () => { void marks.keep(deck[0]!); next(deck[0]!) } }}
                       no={{ label: 'It’s done', onPress: () => { void marks.done(deck[0]!); next(deck[0]!) } }} />
        </>
      ) : null}
      {insight && s.data ? <View style={{ marginTop: t.space.xl }}><InsightCard {...insight} /></View> : null}
      {quiet.length && s.data ? (
        <>
          <SectionLabel>Quiet · assumed done</SectionLabel>
          <QuietPile names={quiet.map((q) => q.name)} onPress={() => router.navigate('/all')} />
        </>
      ) : null}
    </Animated.ScrollView>
    <TopBar y={chrome.y} title="Today" at={150} />
    <ActionMenu open={!!menu} onClose={() => setMenu(null)}
                preview={menu ? <View style={{ marginHorizontal: -t.space.lg }}><PromiseCard item={menu} /></View> : null}
                groups={menu ? [
                  [{ label: 'Mark done', icon: 'checkmark', onPress: () => marks.done(menu) },
                   { label: 'Snooze a day', icon: 'time-outline', onPress: () => marks.snooze(menu, 1) },
                   { label: 'Open chat', icon: 'chatbubble-outline', onPress: () => open(menu) }],
                  [{ label: 'Not needed', icon: 'close', onPress: () => marks.dismiss(menu) }],
                ] : []} />
    </View>
  )
}
