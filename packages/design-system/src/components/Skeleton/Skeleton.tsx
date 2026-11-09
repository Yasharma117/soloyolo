import { useEffect } from 'react'
import { StyleSheet, View } from 'react-native'
import Animated, { Easing, ReduceMotion, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated'
import { useTheme } from '../../theme'

/** A placeholder line at a real line's size while data loads. It breathes, unless the phone asks for less motion. */
export function Skeleton({ width = '60%', height = 12 }: { width?: number | `${number}%`; height?: number }) {
  const t = useTheme()
  const o = useSharedValue(1)
  useEffect(() => {
    o.value = withRepeat(withTiming(0.5, { duration: 900, easing: Easing.inOut(Easing.quad), reduceMotion: ReduceMotion.System }), -1, true)
  }, [o])
  const style = useAnimatedStyle(() => ({ opacity: o.value }))
  return <Animated.View style={[{ width, height, borderRadius: height / 2, backgroundColor: t.color.surfaceRaised }, style]} />
}

/** Today's card while it loads: the same size and padding as PromiseCard, so nothing jumps when it arrives. */
export function CardSkeleton() {
  const t = useTheme()
  return (
    <View style={{ marginHorizontal: t.space.lg, marginBottom: t.space.md + 2, padding: t.space.lg, gap: t.space.md, borderRadius: t.radius.card,
                   backgroundColor: t.color.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.space.sm }}>
        <Skeleton width={24} height={24} /><Skeleton width="35%" height={12} />
      </View>
      <Skeleton width="90%" height={16} /><Skeleton width="65%" height={16} />
      <Skeleton width="80%" height={11} />
    </View>
  )
}

/** A list row while it loads: avatar, name, one line. */
export function RowSkeleton() {
  const t = useTheme()
  return (
    <View style={{ flexDirection: 'row', gap: t.space.md, paddingHorizontal: t.space.xl, paddingVertical: t.space.md + 2,
                   borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: t.color.border }}>
      <Skeleton width={36} height={36} />
      <View style={{ flex: 1, gap: 8, paddingTop: 2 }}><Skeleton width="40%" height={12} /><Skeleton width="85%" height={12} /></View>
    </View>
  )
}
