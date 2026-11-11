import { useEffect, useState } from 'react'
import { Pressable, View } from 'react-native'
import Animated, { ReduceMotion, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

const PAD = 3

/**
 * Two to four views of the same thing: Today / This week. A white thumb slides under the chosen one (Withings).
 * Tabs switch between different content; ChipGroup filters a list.
 */
export function SegmentedControl<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string
}) {
  const t = useTheme()
  const [w, setW] = useState(0)
  const seg = w ? (w - PAD * 2) / options.length : 0
  const i = Math.max(0, options.findIndex((o) => o.value === value))
  const x = useSharedValue(0)
  useEffect(() => {
    x.value = withTiming(i * seg, { duration: t.motion.base, reduceMotion: ReduceMotion.System })
  }, [i, seg, x, t.motion.base])
  // The thumb is the lighter of the two fills in either theme, so it always reads as raised.
  const dark = t.scheme === 'dark'
  const thumb = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }] }))
  return (
    <View accessibilityRole="tablist" accessibilityLabel={label} onLayout={(e) => setW(e.nativeEvent.layout.width)}
          style={{ flexDirection: 'row', height: 38, padding: PAD, borderRadius: t.radius.pill, backgroundColor: dark ? t.color.surface : t.color.surfaceRaised }}>
      {seg ? (
        <Animated.View style={[{ position: 'absolute', top: PAD, bottom: PAD, left: PAD, width: seg, borderRadius: t.radius.pill,
                                 backgroundColor: dark ? t.color.border : t.color.surface, shadowColor: t.color.shadow, shadowOpacity: 0.1, shadowRadius: 4,
                                 shadowOffset: { width: 0, height: 1 }, elevation: 1 }, thumb]} />
      ) : null}
      {options.map((o) => {
        const on = o.value === value
        return (
          <Pressable key={o.value} accessibilityRole="tab" accessibilityState={{ selected: on }} onPress={() => onChange(o.value)}
                     style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
            <Text variant="small" tone={on ? 'primary' : 'secondary'} numberOfLines={1} style={{ fontWeight: on ? '600' : '500' }}>{o.label}</Text>
          </Pressable>
        )
      })}
    </View>
  )
}
