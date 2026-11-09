import { InlineError, PageTitle, PersonRow, RowSkeleton, SearchField, SectionLabel, TopBar, Wash, useScrollChrome, useTheme } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useMemo, useState } from 'react'
import { View } from 'react-native'
import Animated from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { refresh, useData } from '../../lib/api'
import { isOpen, type PersonSummary } from '../../lib/types'

export default function People() {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const [q, setQ] = useState('')
  const chrome = useScrollChrome()
  const { state: preview } = useLocalSearchParams<{ state?: 'empty' | 'error' | 'loading' }>()
  const real = useData<PersonSummary[]>('/api/people')
  const { data, error, loading } = preview === 'loading' ? { data: null, error: null, loading: true }
    : preview === 'error' ? { data: null, error: 'preview', loading: false }
    : preview === 'empty' ? { data: [] as PersonSummary[], error: null, loading: false } : real
  const list = useMemo(() => (data ?? [])
    .filter((p) => !p.muted && (!q || p.name.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => b.score - a.score)
    .slice(0, 150), [data, q])
  return (
    <View style={{ flex: 1, backgroundColor: t.color.background }}>
    <Animated.FlatList
      onScroll={chrome.onScroll} scrollEventThrottle={16}
      contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}
      data={list}
      keyExtractor={(p) => String(p.id)}
      keyboardDismissMode="on-drag"
      ListHeaderComponent={
        <View>
          <Wash />
          <PageTitle title="People" subtitle="Everyone you talk to, closest first, with what you owe each other." />
          {error ? <View style={{ marginTop: t.space.md }}><InlineError title="We couldn’t load your people." body="soloyolo on your Mac didn’t answer. Check it’s running, then try again." onRetry={refresh} /></View> : null}
          <View style={{ paddingHorizontal: t.space.lg, marginTop: t.space.md + 2 }}><SearchField value={q} onChangeText={setQ} /></View>
          <SectionLabel>{q ? 'Matches' : 'Closest first'}</SectionLabel>
          {loading && !data && !error ? [0, 1, 2, 3, 4, 5].map((i) => <RowSkeleton key={i} />) : null}
        </View>
      }
      renderItem={({ item: p }) => (
        <PersonRow name={p.name} networks={p.networks} last={p.last}
                   youOwe={p.commitments.filter((x) => x.owner === 'me' && isOpen(x)).length}
                   theyOwe={p.commitments.filter((x) => x.owner === 'them' && isOpen(x)).length}
                   onPress={() => router.push({ pathname: '/person/[id]', params: { id: String(p.id) } })} />
      )}
    />
    <TopBar y={chrome.y} title="People" at={60} />
    </View>
  )
}
