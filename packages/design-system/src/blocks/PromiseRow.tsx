import { View } from 'react-native'
import { Avatar } from '../components/Avatar/Avatar'
import { ReasonChips } from '../components/Chip/Chip'
import { ListRow } from '../components/ListRow/ListRow'
import { ReviewStrip } from '../components/ReviewStrip/ReviewStrip'
import { Row } from '../components/Stack/Stack'
import { STATUS, StatusBadge, type Status } from '../components/StatusBadge/StatusBadge'
import { SwipeRow, useSwipeTap, type SwipeAction } from '../components/SwipeRow/SwipeRow'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import { PromiseSentence } from './PromiseSentence'
import { ago, type PromiseItem } from './types'

/** Kept for screens written before the shared vocabulary: the same as Status. */
export type PromiseState = Status

/** A promise in a list. With `showPerson`, led by their avatar and name; without, by a state dot. */
export function PromiseRow({ item, state, showPerson = true, highlighted, onPress, trailing, leading, onSettle }: {
  item: PromiseItem; state: Status; showPerson?: boolean; highlighted?: boolean; onPress?: () => void
  trailing?: SwipeAction; leading?: SwipeAction
  /** Confirms the suggestion when the item looks settled. */
  onSettle?: () => void
}) {
  const t = useTheme()
  const swipe = useSwipeTap(onPress)
  const closed = state === 'done' || state === 'not needed' || state === 'later'
  const dot = <View style={{ width: 8, height: 8, borderRadius: 4, marginTop: 7, backgroundColor: state === 'quiet' ? t.color.border : t.color[STATUS[state].color] }} />
  return (
    <SwipeRow trailing={trailing} leading={leading} onDragStart={swipe.dragStart}>
      <ListRow lead={showPerson ? <Avatar name={item.name} size="md" /> : dot} onPress={swipe.tap} highlighted={highlighted}
               title={showPerson ? item.name : undefined}>
        <PromiseSentence item={item} size="small" struck={closed} />
        <Row gap="sm">
          <StatusBadge status={state} />
          <Text variant="caption" tone="tertiary">said {ago(item.source_ts)} ago{item.due ? ` · due ${item.due}` : ''}</Text>
        </Row>
        {state === 'today' ? <View style={{ marginTop: 4 }}><ReasonChips reasons={item.reasons} /></View> : null}
        {state === 'settled' && item.suggestion ? (
          <View style={{ marginTop: 6 }}><ReviewStrip message={item.suggestion} actionLabel={onSettle ? 'Mark done' : undefined} onAction={onSettle} /></View>
        ) : null}
      </ListRow>
    </SwipeRow>
  )
}
