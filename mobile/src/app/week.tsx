// The week's review: what you closed, what settled without you, and what went quiet (/api/week).
import { CardSkeleton, EmptyState, InlineError, PromiseRow, Screen, SectionLabel, WeekReview, formatDate, statusOf } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useState } from 'react'
import { View } from 'react-native'
import { refresh, useData } from '../lib/api'
import { keyOf, type Item, type Week } from '../lib/types'

export default function WeekScreen() {
  const router = useRouter()
  const { state: preview } = useLocalSearchParams<{ state?: 'empty' | 'error' | 'loading' }>()
  const [openedAt] = useState(() => Date.now() / 1000) // the clock is read once, when the screen opens
  const live = useData<Week>('/api/week')
  const s = preview === 'loading' ? { data: null, error: null, loading: true }
    : preview === 'error' ? { data: null, error: 'preview', loading: false }
    : preview === 'empty' ? { data: { since: openedAt - 7 * 86400, done: [], settled: [], quiet: [] }, error: null, loading: false } : live
  const w = s.data
  const open = (it: Item) => router.push({ pathname: '/person/[id]', params: { id: String(it.person_id), focus: String(it.source_message_id) } })
  const list = (title: string, items: Item[]) => items.length ? (
    <View>
      <SectionLabel>{`${title} · ${items.length}`}</SectionLabel>
      {items.map((it) => <PromiseRow key={keyOf(it)} item={it} state={statusOf(it)} onPress={() => open(it)} />)}
    </View>
  ) : null
  return (
    <Screen>
      <Screen.Header title="This week" subtitle="What closed in the last seven days, and what went quiet." onBack={() => (router.canGoBack() ? router.back() : router.replace('/'))} />
      <Screen.Body>
        {s.error ? <InlineError title="We couldn’t load this week." body="soloyolo on your Mac didn’t answer. Check it’s running and up to date, then try again." onRetry={refresh} /> : null}
        {s.loading && !w && !s.error ? <CardSkeleton /> : null}
        {w ? (
          <>
            <WeekReview range={`${formatDate(w.since)} to ${formatDate(openedAt)}`} done={w.done.length} settled={w.settled.length} quiet={w.quiet.length} />
            {!w.done.length && !w.settled.length && !w.quiet.length
              ? <EmptyState title="Nothing closed or went quiet this week." body="Things you mark done, and things the chat settles, show up here." /> : null}
            {list('Done by you', w.done)}
            {list('Settled without you', w.settled)}
            {list('Went quiet', w.quiet)}
          </>
        ) : null}
      </Screen.Body>
    </Screen>
  )
}
