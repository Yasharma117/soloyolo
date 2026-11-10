import { useEffect } from 'react'
import { StyleSheet, View } from 'react-native'
import Animated, { ReduceMotion, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated'
import { Icon, NetworkIcon } from '../components/Icon/Icon'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import type { StepState } from './OnboardingStep'

export type ImportStage = { label: string; state: StepState; /** What it found: "312", "4 promises". */ value?: string }

/**
 * An export being read. The headline is the running count, said as a finding ("Found 4 promises so far", after
 * Brink), over a thin bar; under it the stages, each ticked as it finishes with what it found (Blinkist's checklist).
 * `skipped` says what was left out and why, so a low count isn't a mystery.
 */
export function ImportProgress({ network, headline, detail, progress, stages, skipped }: {
  network: string; headline: string; detail?: string; /** 0 to 1. */ progress: number; stages: ImportStage[]; skipped?: string
}) {
  const t = useTheme()
  const p = useSharedValue(progress)
  useEffect(() => {
    p.value = withTiming(Math.min(1, Math.max(0, progress)), { duration: t.motion.slow, reduceMotion: ReduceMotion.System })
  }, [progress, p, t.motion.slow])
  const fill = useAnimatedStyle(() => ({ width: `${p.value * 100}%` }))
  return (
    <View style={{ paddingHorizontal: t.space.xl, gap: t.space.xl }}>
      <View style={{ alignItems: 'center', gap: t.space.md, paddingTop: t.space.lg }}>
        <View style={{ width: 64, height: 64, borderRadius: t.radius.xl, alignItems: 'center', justifyContent: 'center', backgroundColor: t.color.surface,
                       shadowColor: t.color.shadow, ...t.shadow.card }}>
          <NetworkIcon network={network} size="xxl" />
        </View>
        <Text variant="headline" align="center" accessibilityLiveRegion="polite">{headline}</Text>
        {detail ? <Text variant="body" tone="secondary" align="center">{detail}</Text> : null}
        <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(progress * 100) }}
              style={{ alignSelf: 'stretch', height: 6, borderRadius: 3, backgroundColor: t.color.surfaceRaised, overflow: 'hidden', marginTop: t.space.xs }}>
          <Animated.View style={[{ height: 6, borderRadius: 3, backgroundColor: t.color.inverse }, fill]} />
        </View>
      </View>
      <View style={{ backgroundColor: t.color.surface, borderRadius: t.radius.xl, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border, overflow: 'hidden' }}>
        {stages.map((s, i) => (
          <View key={s.label} style={{ flexDirection: 'row', alignItems: 'center', gap: t.space.md, paddingHorizontal: t.space.lg, paddingVertical: t.space.md + 1,
                                      borderTopWidth: i ? StyleSheet.hairlineWidth : 0, borderTopColor: t.color.border, opacity: s.state === 'later' ? 0.5 : 1 }}>
            <Icon name={s.state === 'done' ? 'checkmark-circle' : s.state === 'now' ? 'time-outline' : 'ellipse-outline'} size="lg"
                  tone={s.state === 'done' ? 'success' : s.state === 'now' ? 'accent' : 'tertiary'} />
            <Text variant="body" style={{ flex: 1, fontWeight: s.state === 'now' ? '600' : '400' }}>{s.label}</Text>
            {s.value ? <Text variant="body" tone="secondary" style={{ fontWeight: '500' }}>{s.value}</Text> : null}
          </View>
        ))}
      </View>
      {skipped ? <Text variant="small" tone="tertiary">{skipped}</Text> : null}
    </View>
  )
}
