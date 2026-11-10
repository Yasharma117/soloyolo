// "Same person?": the pairs of chats soloyolo thinks are one person (spike/identity.py's review queue).
// It only suggests: nothing merges until you say Same person, and that can be undone from the toast.
import { CardSkeleton, EmptyState, InlineError, MergeSuggestion, Screen, useToast } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useState } from 'react'
import { decideMerge, refresh, undoMerge, useData } from '../lib/api'
import type { MergePair } from '../lib/types'

const FAILED = 'Couldn’t save that. Check soloyolo is running on your Mac, then try again.'

export default function Merges() {
  const router = useRouter()
  const toast = useToast()
  const { state: preview } = useLocalSearchParams<{ state?: 'empty' | 'error' | 'loading' }>()
  const live = useData<MergePair[]>('/api/merges')
  const s = preview === 'loading' ? { data: null, error: null, loading: true }
    : preview === 'error' ? { data: null, error: 'preview', loading: false }
    : preview === 'empty' ? { data: [], error: null, loading: false } : live
  const [busy, setBusy] = useState<string | null>(null)
  const decide = async (p: MergePair, same: boolean) => {
    setBusy(`${p.a.id}:${p.b.id}`)
    try {
      const id = await decideMerge(p.a.id, p.b.id, same)
      toast.show(same ? 'Chats merged' : 'Kept as two people', id != null ? () => undoMerge(id).catch(() => toast.show(FAILED)) : undefined)
    } catch {
      toast.show(FAILED)
    } finally {
      setBusy(null)
    }
  }
  return (
    <Screen>
      <Screen.Header title="Same person?" subtitle="Chats that look like one person. Merging joins their promises and history."
                     onBack={() => (router.canGoBack() ? router.back() : router.replace('/people'))} />
      <Screen.Body>
        {s.error ? <InlineError title="We couldn’t load the suggestions." body="soloyolo on your Mac didn’t answer. Check it’s running and up to date, then try again." onRetry={refresh} /> : null}
        {s.loading && !s.data && !s.error ? <><CardSkeleton /><CardSkeleton /></> : null}
        {s.data?.map((p) => (
          <MergeSuggestion key={`${p.a.id}:${p.b.id}`} a={p.a} b={p.b} reasons={p.reasons} busy={busy === `${p.a.id}:${p.b.id}`}
                           onSame={() => decide(p, true)} onDifferent={() => decide(p, false)} />
        ))}
        {s.data && !s.data.length ? <EmptyState title="No one looks like a duplicate." body="When two chats look like the same person, soloyolo asks here before joining them." /> : null}
      </Screen.Body>
    </Screen>
  )
}
