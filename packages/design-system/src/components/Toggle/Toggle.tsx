import * as Haptics from 'expo-haptics'
import { useEffect } from 'react'
import { Platform, Pressable, StyleSheet } from 'react-native'
import Animated, { interpolateColor, ReduceMotion, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated'
import { useTheme } from '../../theme'

const W = 50, H = 30, KNOB = 26

/**
 * On or off, for a setting that takes effect at once (no Save). On is the inverse fill, not green: green means Done.
 * Put it in a NavRow's `trailing`; `label` names the setting for screen readers.
 */
export function Toggle({ value, onChange, label, disabled }: { value: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  const t = useTheme()
  const p = useSharedValue(value ? 1 : 0)
  useEffect(() => {
    p.value = withTiming(value ? 1 : 0, { duration: t.motion.fast, reduceMotion: ReduceMotion.System })
  }, [value, p, t.motion.fast])
  const track = useAnimatedStyle(() => ({ backgroundColor: interpolateColor(p.value, [0, 1], [t.color.surfaceRaised, t.color.inverse]) }))
  const knob = useAnimatedStyle(() => ({
    transform: [{ translateX: p.value * (W - KNOB - 4) }],
    backgroundColor: interpolateColor(p.value, [0, 1], [t.color.surface, t.color.onInverse]),
  }))
  const flip = () => {
    if (Platform.OS !== 'web') Haptics.selectionAsync().catch(() => {})
    onChange(!value)
  }
  return (
    <Pressable accessibilityRole="switch" accessibilityLabel={label} accessibilityState={{ checked: value, disabled }} aria-checked={value} disabled={disabled}
               onPress={flip} hitSlop={8} style={{ opacity: disabled ? 0.4 : 1 }}>
      <Animated.View style={[{ width: W, height: H, borderRadius: H / 2, padding: 2, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border }, track]}>
        <Animated.View style={[{ width: KNOB, height: KNOB, borderRadius: KNOB / 2, shadowColor: t.color.shadow, shadowOpacity: 0.18, shadowRadius: 3,
                                 shadowOffset: { width: 0, height: 1 }, elevation: 2 }, knob]} />
      </Animated.View>
    </Pressable>
  )
}
