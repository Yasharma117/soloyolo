// After "Not needed", one optional question: why? The mark is saved first, so skipping costs nothing.
// The answers are Run 6's buckets (spike/eval/RESULTS.md), counted from real use instead of a one-off scoring.
import { ReasonSheet, type Reason } from '@soloyolo/design-system'
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import type { Item } from './types'

export type ReasonKey = 'off_chat' | 'not_needed' | 'let_go' | 'misread'

export const REASONS: Reason<ReasonKey>[] = [
  { key: 'off_chat', label: 'Done, just not on the chat', icon: 'checkmark-circle' },
  { key: 'not_needed', label: 'No longer needed', icon: 'remove-circle-outline' },
  { key: 'let_go', label: 'Letting it go', icon: 'hand-left-outline' },
  { key: 'misread', label: 'Never a real promise', icon: 'alert-circle' },
]

type Ask = (item: Item) => Promise<ReasonKey | null>
const Ctx = createContext<Ask>(async () => null)

export function ReasonProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<{ item: Item; done: (k: ReasonKey | null) => void } | null>(null)
  const ask = useCallback<Ask>((item) => new Promise((done) => setPending({ item, done })), [])
  const finish = (k: ReasonKey | null) => {
    pending?.done(k)
    setPending(null)
  }
  return (
    <Ctx.Provider value={ask}>
      {children}
      <ReasonSheet open={!!pending} title="Why isn’t it needed?" subtitle={pending?.item.action}
                   reasons={REASONS} onPick={finish} onSkip={() => finish(null)} />
    </Ctx.Provider>
  )
}

export const useAskWhy = () => useContext(Ctx)
