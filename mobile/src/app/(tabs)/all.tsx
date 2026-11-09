import { ChipGroup, InlineError, PageTitle, PromiseRow, RowSkeleton, SectionLabel, Text, TopBar, Wash, statusOf, useScrollChrome, useTheme, type ChipOption } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useState } from 'react'
import { View } from 'react-native'
import Animated from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { refresh, useData } from '../../lib/api'
import { useMarks } from '../../lib/marks'
import { keyOf, type Item } from '../../lib/types'

type Filter = 'all' | 'me' | 'them' | 'money' | 'settled'

const FILTERS: { value: Filter; label: string; test: (i: Item) => boolean }[] = [
  { value: 'all', label: 'All', test: () => true },
  { value: 'me', label: 'You owe', test: (i) => i.owner === 'me' },
  { value: 'them', label: 'Owed to you', test: (i) => i.owner === 'them' },
  // the server decides what's money (spike/priority.py is_money) and says so in reasons; the app doesn't guess
  { value: 'money', label: 'Money', test: (i) => !!i.reasons?.includes('money') },
  { value: 'settled', label: 'Looks settled', test: (i) => !!i.suggestion },
]

export default function All() {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const marks = useMarks()
  const [filter, setFilter] = useState<Filter>('all')
  const chrome = useScrollChrome()
  const { state: preview } = useLocalSearchParams<{ state?: 'empty' | 'error' | 'loading' }>()
  const real = useData<Item[]>('/api/all')
  const { data, error, loading } = preview === 'loading' ? { data: null, error: null, loading: true }
    : preview === 'error' ? { data: null, error: 'preview', loading: false }
    : preview === 'empty' ? { data: [] as Item[], error: null, loading: false } : real
  const every = data ?? []
  const options: ChipOption<Filter>[] = FILTERS.map((f) => ({ value: f.value, label: f.label, count: every.filter(f.test).length }))
    .filter((o) => o.value === 'all' || o.count > 0 || o.value === filter)
  const shown = every.filter(FILTERS.find((f) => f.value === filter)!.test)
  const live = shown.filter((x) => x.live)
  const quiet = shown.filter((x) => !x.live)
  const open = (it: Item) => router.push({ pathname: '/person/[id]', params: { id: String(it.person_id), focus: String(it.source_message_id) } })
  const row = (it: Item) => {
    const st = statusOf(it)
    return (
      <PromiseRow key={keyOf(it)} item={it} state={st} onPress={() => open(it)} onSettle={() => marks.done(it)}
                  trailing={st === 'quiet' ? { label: 'Still on', icon: 'refresh', tone: 'later', onAction: () => marks.keep(it) }
                    : { label: 'Done', icon: 'checkmark', tone: 'success', onAction: () => marks.done(it) }}
                  leading={{ label: 'Not needed', icon: 'close', tone: 'neutralAction', onAction: () => marks.dismiss(it) }} />
    )
  }
  return (
    <View style={{ flex: 1, backgroundColor: t.color.background }}>
    <Animated.ScrollView onScroll={chrome.onScroll} scrollEventThrottle={16} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}>
      <Wash />
      <PageTitle title="All open" subtitle="Everything still open. Quiet ones are assumed done; swipe one left if it isn’t." />
      {error ? <InlineError title="We couldn’t load your promises." body="soloyolo on your Mac didn’t answer. Check it’s running, then try again." onRetry={refresh} /> : null}
      {every.length ? <View style={{ marginBottom: t.space.xs }}><ChipGroup scroll label="Show" options={options} value={filter} onChange={setFilter} /></View> : null}
      {loading && !data && !error ? <View style={{ paddingTop: t.space.lg }}>{[0, 1, 2, 3, 4].map((i) => <RowSkeleton key={i} />)}</View> : null}
      {data ? <>
      <SectionLabel>{`On today · ${live.length}`}</SectionLabel>
      {live.length ? live.map(row) : <Text variant="small" tone="tertiary" style={{ paddingHorizontal: t.space.xl }}>Nothing.</Text>}
      <SectionLabel>{`Quiet · ${quiet.length}`}</SectionLabel>
      {quiet.length ? quiet.map(row) : <Text variant="small" tone="tertiary" style={{ paddingHorizontal: t.space.xl }}>Nothing.</Text>}
      </> : null}
    </Animated.ScrollView>
    <TopBar y={chrome.y} title="All open" at={70} />
    </View>
  )
}
