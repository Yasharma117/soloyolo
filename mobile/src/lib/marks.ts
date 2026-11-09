// What a swipe or tap does to an item: save the mark, say so, offer Undo.
import { useToast } from '@soloyolo/design-system'
import { mark } from './api'
import { useAskWhy, type ReasonKey } from './reasons'
import type { Item, Mark } from './types'

const SAID: Record<Mark, string> = {
  done: 'Marked done', dismissed: 'Marked not needed', open: 'Kept on for 3 more days', snoozed: 'Snoozed for 3 days', clear: 'Undone',
}
const SAID_WHY: Record<ReasonKey, string> = {
  off_chat: 'Marked done', not_needed: 'Marked not needed', let_go: 'Let go', misread: 'Marked not a promise',
}
const FAILED = 'Couldn’t save that. Check soloyolo is running on your Mac, then try again.'

export function useMarks() {
  const toast = useToast()
  const askWhy = useAskWhy()
  const act = async (item: Item, state: Mark) => {
    try {
      await mark(item, state)
      toast.show(SAID[state], state === 'clear' ? undefined : () => mark(item, 'clear'))
    } catch {
      toast.show(FAILED)
    }
  }
  // Saved before the question, so a skipped sheet, a closed app or a lost connection still leaves the mark.
  const dismiss = async (item: Item) => {
    try {
      await mark(item, 'dismissed')
    } catch {
      return toast.show(FAILED)
    }
    const why = await askWhy(item)
    try {
      if (why) await mark(item, 'dismissed', why)
      toast.show(why ? SAID_WHY[why] : SAID.dismissed, () => mark(item, 'clear'))
    } catch {
      toast.show(FAILED)
    }
  }
  return {
    done: (i: Item) => act(i, 'done'),
    dismiss,
    keep: (i: Item) => act(i, 'open'),
    undo: (i: Item) => act(i, i.status === 'done' && i.resolved_by && i.resolved_by !== 'you' ? 'open' : 'clear'),
  }
}
