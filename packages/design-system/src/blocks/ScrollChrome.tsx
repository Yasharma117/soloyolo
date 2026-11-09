import { BlurView } from 'expo-blur'
import { LinearGradient } from 'expo-linear-gradient'
import type { ReactNode } from 'react'
import { StyleSheet, View, useWindowDimensions } from 'react-native'
import Animated, { Extrapolation, interpolate, useAnimatedScrollHandler, useAnimatedStyle, useSharedValue, type SharedValue } from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

/**
 * Scroll-aware screen chrome, from Markon's Screen (app-shell/screen.tsx): the top bar is clear while the page sits
 * at rest so the wash shows through, and fills in, with the title, once content scrolls under it.
 *
 *   const chrome = useScrollChrome()
 *   <Animated.ScrollView onScroll={chrome.onScroll} scrollEventThrottle={16}>
 *     <Wash />  ...the screen...
 *   </Animated.ScrollView>
 *   <TopBar y={chrome.y} title="People" />
 */
export function useScrollChrome() {
  const y = useSharedValue(0)
  const onScroll = useAnimatedScrollHandler((e) => { y.value = e.contentOffset.y })
  return { y, onScroll }
}

/** The warm tint at the top of a screen, gone by about a quarter of the way down. Put it first inside the scroller. */
export function Wash() {
  const t = useTheme()
  const { height } = useWindowDimensions()
  const h = Math.min(240, Math.max(180, height * 0.25))
  return (
    <LinearGradient pointerEvents="none" colors={[t.color.wash, t.color.background]}
                    style={{ position: 'absolute', top: -400, left: 0, right: 0, height: h + 400 }} locations={[400 / (h + 400), 1]} />
  )
}

/**
 * The bar over the status bar and the top of the screen. `title` fades in once the page has scrolled past `at`
 * (where the screen's own big title ends). `leading` and `trailing` stay put the whole time, and their buttons sit
 * on the bar, so a close or back control never scrolls away.
 */
export function TopBar({ y, title, at = 56, leading, trailing }: { y: SharedValue<number>; title?: string; at?: number; leading?: ReactNode; trailing?: ReactNode }) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const fill = useAnimatedStyle(() => ({ opacity: interpolate(y.value, [4, 28], [0, 1], Extrapolation.CLAMP) }))
  const name = useAnimatedStyle(() => ({
    opacity: interpolate(y.value, [at - 16, at + 8], [0, 1], Extrapolation.CLAMP),
    transform: [{ translateY: interpolate(y.value, [at - 16, at + 8], [6, 0], Extrapolation.CLAMP) }],
  }))
  return (
    <View pointerEvents="box-none" style={{ position: 'absolute', top: 0, left: 0, right: 0, paddingTop: insets.top }}>
      <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, fill]}>
        <BlurView intensity={40} tint={t.scheme === 'dark' ? 'dark' : 'light'} style={StyleSheet.absoluteFill} />
        <View style={[StyleSheet.absoluteFill, { backgroundColor: t.color.surfaceFloating, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: t.color.border }]} />
      </Animated.View>
      <View pointerEvents="box-none" style={{ height: 52, flexDirection: 'row', alignItems: 'center', paddingHorizontal: t.space.lg, gap: t.space.md }}>
        <View style={{ minWidth: 36 }}>{leading}</View>
        <Animated.View pointerEvents="none" style={[{ flex: 1, alignItems: 'center' }, name]}>
          {title ? <Text variant="bodyStrong" numberOfLines={1}>{title}</Text> : null}
        </Animated.View>
        <View style={{ minWidth: 36, alignItems: 'flex-end' }}>{trailing}</View>
      </View>
    </View>
  )
}
