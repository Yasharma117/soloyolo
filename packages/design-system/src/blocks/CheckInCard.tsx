import { Pressable, StyleSheet, View } from 'react-native'
import Animated, { FadeInDown, FadeOut } from 'react-native-reanimated'
import { Button } from '../components/Button/Button'
import { Icon } from '../components/Icon/Icon'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import { ago, type PromiseItem } from './types'

const lower = (s: string) => (s.length > 1 && s[1] === s[1]!.toLowerCase() ? s[0]!.toLowerCase() + s.slice(1) : s)

export type CheckInAction = { label: string; onPress: () => void }

/**
 * One quiet promise, asked about plainly: "Is <it> still on?" (from the Atoms redesign's check-in, "Is Read 10 pages
 * still working for you?"). An eyebrow, the question with the promise picked out, two facts side by side, one warm
 * action and one soft one. When more are waiting, cards stack behind it, so the pile reads at a glance.
 *
 * soloyolo assumes quiet things are done; this is the calm way to catch the one that isn't.
 */
export function CheckInCard({ item, waiting = 0, yes, no, onSkip }: {
  item: PromiseItem
  /** How many more are behind this one: draws up to two cards in the stack. */
  waiting?: number
  /** The warm action: "Still on". */
  yes: CheckInAction
  /** The soft action: "It's done". */
  no: CheckInAction
  onSkip?: () => void
}) {
  const t = useTheme()
  const first = item.name.split(' ')[0]!
  const card = { backgroundColor: t.color.surface, borderRadius: t.radius.card, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border,
                 shadowColor: t.color.shadow, ...t.shadow.card }
  const behind = Math.min(2, waiting)
  return (
    <View style={{ marginHorizontal: t.space.lg, paddingBottom: behind * 10 }}>
      {/* the stack behind: each a little narrower and lower, as in the redesign */}
      {[2, 1].filter((i) => i <= behind).map((i) => (
        <View key={i} pointerEvents="none" style={[card, { position: 'absolute', left: i * 10, right: i * 10, top: 0, bottom: (behind - i) * 10, opacity: 1 - i * 0.12 }]} />
      ))}
      <Animated.View key={`${item.name}${item.action}`} entering={FadeInDown.duration(t.motion.base)} exiting={FadeOut.duration(t.motion.fast)}
                     style={[card, { paddingHorizontal: t.space.lg, paddingBottom: t.space.lg }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: t.space.md,
                       borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: t.color.border }}>
          <Icon name="sparkles" size="xs" tone="primary" />
          <Text variant="small" style={{ fontWeight: '700' }}>Still on?</Text>
          {onSkip ? (
            <Pressable accessibilityRole="button" accessibilityLabel="Skip" onPress={onSkip} hitSlop={10} style={{ position: 'absolute', right: 0 }}>
              <Text variant="small" tone="tertiary">Skip</Text>
            </Pressable>
          ) : null}
        </View>
        <View style={{ alignItems: 'center', gap: t.space.sm, paddingTop: t.space.lg, paddingBottom: t.space.lg }}>
          <Text variant="heading" align="center" style={{ fontSize: 22, lineHeight: 28 }}>
            {item.owner === 'me' ? 'Are you still going to ' : `Is ${first} still going to `}
            <Text variant="heading" tone="accent" style={{ fontSize: 22, lineHeight: 28 }}>{lower(item.action)}</Text>
            ?
          </Text>
          {item.source_text ? (
            <Text variant="small" tone="tertiary" align="center" numberOfLines={2}>“{item.source_text}”</Text>
          ) : null}
        </View>
        <View style={{ flexDirection: 'row', backgroundColor: t.color.background, borderRadius: t.radius.md + 2, borderWidth: StyleSheet.hairlineWidth,
                       borderColor: t.color.border, marginBottom: t.space.lg }}>
          {[['Said', `${ago(item.source_ts)} ago`], [item.owner === 'me' ? 'Owed to' : 'Owed by', first]].map(([label, value], i) => (
            <View key={label} style={{ flex: 1, alignItems: 'center', paddingVertical: t.space.sm + 2, borderLeftWidth: i ? StyleSheet.hairlineWidth : 0, borderLeftColor: t.color.border }}>
              <Text variant="caption" style={{ fontWeight: '700' }}>{label}</Text>
              <Text variant="heading" style={{ fontSize: 22, lineHeight: 28 }}>{value}</Text>
            </View>
          ))}
        </View>
        <View style={{ gap: t.space.xs + 2 }}>
          <Button label={yes.label} variant="warm" onPress={yes.onPress} />
          <Button label={no.label} variant="soft" onPress={no.onPress} />
        </View>
      </Animated.View>
    </View>
  )
}
