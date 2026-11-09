// What a swipe or tap does to an item: save the mark, say so, offer Undo.
import { useToast } from '@soloyolo/design-system'
import { mark } from './api'
import type { Item, Mark } from './types'

const SAID: Record<Mark, string> = {
  done: 'Marked done', dismissed: 'Marked not needed', open: 'Kept on for 3 more days', snoozed: 'Snoozed for 3 days', clear: 'Undone',
}

export function useMarks() {
  const toast = useToast()
  const act = async (item: Item, state: Mark) => {
    try {
      await mark(item, state)
      toast.show(SAID[state], state === 'clear' ? undefined : () => mark(item, 'clear'))
    } catch {
      toast.show('Couldn’t save that. Is soloyolo running on your Mac?')
    }
  }
  return {
    done: (i: Item) => act(i, 'done'),
    dismiss: (i: Item) => act(i, 'dismissed'),
    keep: (i: Item) => act(i, 'open'),
    undo: (i: Item) => act(i, i.status === 'done' && i.resolved_by && i.resolved_by !== 'you' ? 'open' : 'clear'),
  }
}
