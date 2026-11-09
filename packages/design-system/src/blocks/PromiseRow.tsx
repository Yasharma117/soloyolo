import { View } from 'react-native'
import { Avatar } from '../components/Avatar/Avatar'
import { ReasonChips } from '../components/Chip/Chip'
import { ListRow } from '../components/ListRow/ListRow'
import { SwipeRow, type SwipeAction } from '../components/SwipeRow/SwipeRow'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import { PromiseSentence } from './PromiseSentence'
import { ago, type PromiseItem } from './types'

export type PromiseState = 'today' | 'quiet' | 'done' | 'not needed' | 'later'

/** A promise in a list. With `showPerson`, led by their avatar and name; without, by a state dot. */
export function PromiseRow({ item, state, showPerson = true, highlighted, onPress, trailing, leading }: {
  item: PromiseItem; state: PromiseState; showPerson?: boolean; highlighted?: boolean; onPress?: () => void
  trailing?: SwipeAction; leading?: SwipeAction
}) {
  const t = useTheme()
  const closed = state === 'done' || state === 'not needed' || state === 'later'
  const dot = <View style={{ width: 8, height: 8, borderRadius: 4, marginTop: 7, backgroundColor: closed ? t.color.textTertiary : state === 'quiet' ? t.color.border : t.color.accent }} />
  return (
    <SwipeRow trailing={trailing} leading={leading}>
      <ListRow lead={showPerson ? <Avatar name={item.name} size="md" /> : dot} onPress={onPress} highlighted={highlighted}
               title={showPerson ? item.name : undefined}>
        <PromiseSentence item={item} size="small" struck={closed} />
        <Text variant="caption" tone="tertiary">{state} · said {ago(item.source_ts)} ago{item.due ? ` · due ${item.due}` : ''}</Text>
        {state === 'today' ? <View style={{ marginTop: 4 }}><ReasonChips reasons={item.reasons} /></View> : null}
      </ListRow>
    </SwipeRow>
  )
}
