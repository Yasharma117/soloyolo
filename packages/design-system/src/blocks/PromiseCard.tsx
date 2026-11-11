import { View } from 'react-native'
import { Avatar } from '../components/Avatar/Avatar'
import { ReasonChips } from '../components/Chip/Chip'
import { NetworkIcon } from '../components/Icon/Icon'
import { ReviewStrip } from '../components/ReviewStrip/ReviewStrip'
import { Row } from '../components/Stack/Stack'
import { Surface } from '../components/Surface/Surface'
import { SwipeRow, useSwipeTap } from '../components/SwipeRow/SwipeRow'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import { PromiseSentence } from './PromiseSentence'
import { ago, type PromiseItem } from './types'

export function Quote({ text }: { text?: string | null }) {
  const t = useTheme()
  if (!text) return null
  return (
    <Row gap="sm" align="stretch">
      <View style={{ width: 2, borderRadius: 1, backgroundColor: t.color.border }} />
      <Text variant="small" tone="secondary" numberOfLines={2} style={{ flex: 1, fontSize: 14, lineHeight: 19 }}>“{text}”</Text>
    </Row>
  )
}

/** Today's card. Swipe left: Done. Swipe right: Not needed. Tap: open the person. Long-press: every action (ActionMenu). */
export function PromiseCard({ item, onPress, onDone, onDismiss, onSettle, onLongPress }: { item: PromiseItem; onPress?: () => void; onLongPress?: () => void; onDone?: () => void; onDismiss?: () => void; onSettle?: () => void }) {
  const t = useTheme()
  const swipe = useSwipeTap(onPress)
  return (
    <View style={{ marginHorizontal: t.space.lg, marginBottom: t.space.md + 2 }}>
      <SwipeRow radius={t.radius.card} onDragStart={swipe.dragStart}
                trailing={onDone ? { label: 'Done', icon: 'checkmark', tone: 'success', onAction: onDone } : undefined}
                leading={onDismiss ? { label: 'Not needed', icon: 'close', tone: 'neutralAction', onAction: onDismiss } : undefined}>
        <Surface onPress={swipe.tap} onLongPress={onLongPress} style={{ gap: t.space.md }}>
          <Row gap="sm">
            <Avatar name={item.name} size="sm" />
            <Text variant="small" style={{ fontWeight: '600', flexShrink: 1, fontSize: 14 }} numberOfLines={1}>{item.name}</Text>
            {item.networks?.[0] ? <NetworkIcon network={item.networks[0]} /> : null}
            <Text variant="caption" tone="tertiary" style={{ marginLeft: 'auto' }}>{ago(item.source_ts)}</Text>
          </Row>
          <PromiseSentence item={item} />
          <Quote text={item.source_text?.slice(0, 160)} />
          <ReasonChips reasons={item.reasons} />
          {item.suggestion ? <ReviewStrip message={item.suggestion} actionLabel={onSettle ? 'Mark done' : undefined} onAction={onSettle} /> : null}
        </Surface>
      </SwipeRow>
    </View>
  )
}
