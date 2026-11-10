import { Pressable, StyleSheet, View } from 'react-native'
import { Avatar } from '../components/Avatar/Avatar'
import { Icon } from '../components/Icon/Icon'
import { Row } from '../components/Stack/Stack'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import { Quote } from './PromiseCard'
import { ago } from './types'

/** How an edge's kind reads between two names. An unknown kind is shown as it was written. */
export const EDGE_WORDS: Record<string, string> = {
  intro: 'introduced you to', knows: 'knows', colleague: 'works with', family: 'is family of', referred: 'referred you to', reports_to: 'reports to',
}

/**
 * Who knows whom, learned from what was said: "Sonu referred you to Saurabh", what they're doing about it
 * ("forwarding your profile") and the line that says so. Every connection soloyolo found shows its quote.
 */
export function EdgeRow({ from, to, kind, note, quote, ts, onPress, first }: {
  from: string; to: string; kind: string; note?: string | null; quote?: string | null; ts?: number; onPress?: () => void; first?: boolean
}) {
  const t = useTheme()
  return (
    <Pressable accessibilityRole={onPress ? 'button' : undefined} onPress={onPress} disabled={!onPress}
               style={({ pressed }) => ({ gap: t.space.sm, paddingHorizontal: t.space.lg, paddingVertical: t.space.md + 1,
                                          backgroundColor: pressed ? t.color.surfaceRaised : 'transparent',
                                          borderTopWidth: first ? 0 : StyleSheet.hairlineWidth, borderTopColor: t.color.border })}>
      <Row gap="sm">
        <Avatar name={from} size="sm" />
        <Icon name="arrow-forward" size="sm" tone="tertiary" />
        <Avatar name={to} size="sm" />
        {ts ? <Text variant="caption" tone="tertiary" style={{ marginLeft: 'auto' }}>{ago(ts)}</Text> : null}
      </Row>
      <View style={{ gap: 2 }}>
        <Text variant="body">
          <Text variant="bodyStrong">{from}</Text> {EDGE_WORDS[kind] ?? kind.replace(/_/g, ' ')} <Text variant="bodyStrong">{to}</Text>
        </Text>
        {note ? <Text variant="small" tone="secondary">{note[0]!.toUpperCase() + note.slice(1)}</Text> : null}
      </View>
      <Quote text={quote?.slice(0, 160)} />
    </Pressable>
  )
}
