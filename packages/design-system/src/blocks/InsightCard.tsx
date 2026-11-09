import { LinearGradient } from 'expo-linear-gradient'
import { StyleSheet, View } from 'react-native'
import { GradientText } from '../components/GradientText/GradientText'
import { Icon } from '../components/Icon/Icon'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

/**
 * Something soloyolo noticed, said once (from the Atoms redesign's suggestion card, "Never Miss Twice"): an eyebrow,
 * a small caps label, a serif headline in the insight gradient, and one sentence of why. One on a screen, at most
 * one a week; it should read like a friend's observation, not a report.
 */
export function InsightCard({ eyebrow = 'This week', label, headline, body }: { eyebrow?: string; label: string; headline: string; body: string }) {
  const t = useTheme()
  return (
    <View style={{ marginHorizontal: t.space.lg, borderRadius: t.radius.card + 2, overflow: 'hidden', borderWidth: 1, borderColor: t.color.surface,
                   shadowColor: t.color.shadow, ...t.shadow.card }}>
      <LinearGradient colors={[t.color.cardWarmFrom, t.color.cardWarmTo]} start={{ x: 0.9, y: 0.1 }} end={{ x: 0.1, y: 0.9 }} style={StyleSheet.absoluteFill} />
      <View style={{ paddingHorizontal: t.space.lg, paddingBottom: t.space.xl }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: t.space.md,
                       borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: t.color.border }}>
          <Icon name="sparkles" size="xs" tone="primary" />
          <Text variant="small" style={{ fontWeight: '700' }}>{eyebrow}</Text>
        </View>
        <View style={{ alignItems: 'center', gap: t.space.md, paddingTop: t.space.lg }}>
          <Text variant="caption" tone="tertiary" upper align="center" style={{ letterSpacing: 1.4 }}>{label}</Text>
          <GradientText variant="sentence" align="center" colors={[t.color.insightFrom, t.color.insightTo]} style={{ fontSize: 36, lineHeight: 38 }}>
            {headline}
          </GradientText>
          <Text variant="small" tone="secondary" align="center">{body}</Text>
        </View>
      </View>
    </View>
  )
}
