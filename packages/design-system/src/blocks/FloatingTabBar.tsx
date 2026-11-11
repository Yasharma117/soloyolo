import { BlurView } from 'expo-blur'
import { useEffect, useState } from 'react'
import { Pressable, StyleSheet, View } from 'react-native'
import Animated, { Easing, ReduceMotion, useAnimatedStyle, useSharedValue, withDelay, withSequence, withTiming } from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Icon, type IconName } from '../components/Icon/Icon'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

export type TabItem = { key: string; label: string; icon: IconName; iconActive: IconName; dot?: boolean }

// Markon's floating dock (app-shell/bottom-nav.tsx, after Kuvera): one dock across the bottom, the active tab opens
// into a soft pill with its label beside the icon, the others are icons only. On a change the pill slides and
// stretches to the new tab, the old label folds away, the new one fades in a beat later, and the icon pops.
const GROW = 2.2 // the active tab's share of the dock against 1 for the others
const PAD = 6
const glide = { duration: 300, easing: Easing.bezier(0.22, 1, 0.36, 1), reduceMotion: ReduceMotion.System }

function Tab({ item, on, share, onPress }: { item: TabItem; on: boolean; share: number; onPress: () => void }) {
  const t = useTheme()
  const width = useSharedValue(share)
  const open = useSharedValue(on ? 1 : 0)
  const scale = useSharedValue(1)
  useEffect(() => {
    width.value = withTiming(share, glide)
  }, [share, width])
  useEffect(() => {
    open.value = on ? withDelay(75, withTiming(1, glide)) : withTiming(0, { ...glide, duration: 200 })
    if (on) scale.value = withSequence(withTiming(0.82, { duration: 0, reduceMotion: ReduceMotion.System }),
                                       withTiming(1.14, { duration: 150, easing: glide.easing, reduceMotion: ReduceMotion.System }),
                                       withTiming(1, { duration: 210, easing: glide.easing, reduceMotion: ReduceMotion.System }))
  }, [on, open, scale])
  const box = useAnimatedStyle(() => ({ width: width.value }))
  const label = useAnimatedStyle(() => ({ maxWidth: open.value * 96, marginLeft: open.value * 8, opacity: open.value }))
  const pop = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }))
  return (
    <Animated.View style={[{ height: '100%' }, box]}>
      <Pressable accessibilityRole="tab" accessibilityLabel={item.label} accessibilityState={{ selected: on }} onPress={onPress}
                 style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: t.radius.pill }}>
        <Animated.View style={pop}>
          <Icon name={on ? item.iconActive : item.icon} size="lg" tone={on ? 'primary' : 'tertiary'} />
          {item.dot ? (
            <View style={{ position: 'absolute', top: -2, right: -4, width: 9, height: 9, borderRadius: 5, backgroundColor: t.color.accent,
                           borderWidth: 2, borderColor: on ? t.color.surfaceRaised : t.color.surfaceFloating }} />
          ) : null}
        </Animated.View>
        <Animated.View style={[{ overflow: 'hidden' }, label]}>
          <Text variant="small" numberOfLines={1} style={{ fontWeight: '600' }}>{item.label}</Text>
        </Animated.View>
      </Pressable>
    </Animated.View>
  )
}

/** The app's tab bar: a floating dock with a sliding pill (from Markon's floating dock). */
export function FloatingTabBar({ items, active, onSelect }: { items: TabItem[]; active: string; onSelect: (key: string) => void }) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const [inner, setInner] = useState(0) // the dock's width inside its padding
  const at = Math.max(0, items.findIndex((i) => i.key === active))
  const total = items.length - 1 + GROW
  const share = (i: number) => (inner * (i === at ? GROW : 1)) / total
  const left = useSharedValue(0)
  const width = useSharedValue(0)
  useEffect(() => {
    if (!inner) return
    const to = PAD + (at * inner) / total
    // the first measurement places the pill without a slide; after that it glides
    left.value = width.value ? withTiming(to, glide) : to
    width.value = width.value ? withTiming(share(at), glide) : share(at)
  }, [at, inner]) // eslint-disable-line react-hooks/exhaustive-deps
  const pill = useAnimatedStyle(() => ({ left: left.value, width: width.value, opacity: width.value ? 1 : 0 }))
  return (
    <View pointerEvents="box-none" style={{ position: 'absolute', left: 0, right: 0, bottom: Math.max(insets.bottom, 12) + 4, paddingHorizontal: t.space.md }}>
      <View accessibilityRole="tablist" onLayout={(e) => setInner(e.nativeEvent.layout.width - PAD * 2)}
            style={{ height: 64, flexDirection: 'row', alignItems: 'center', padding: PAD, borderRadius: t.radius.pill,
                     borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border, shadowColor: t.color.shadow, ...t.shadow.floating }}>
        {/* glass, as in Markon's dock: the page blurs behind a near-opaque tint, so the bar reads over any content */}
        <View pointerEvents="none" style={[StyleSheet.absoluteFill, { borderRadius: t.radius.pill, overflow: 'hidden' }]}>
          <BlurView intensity={40} tint={t.scheme === 'dark' ? 'dark' : 'light'} style={StyleSheet.absoluteFill} />
          <View style={[StyleSheet.absoluteFill, { backgroundColor: t.color.surfaceFloating }]} />
        </View>
        <Animated.View pointerEvents="none"
                       style={[{ position: 'absolute', top: PAD, bottom: PAD, borderRadius: t.radius.pill, backgroundColor: t.color.surfaceRaised,
                                 borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border }, pill]} />
        {inner ? items.map((it, i) => (
          <Tab key={it.key} item={it} on={i === at} share={share(i)} onPress={() => i !== at && onSelect(it.key)} />
        )) : null}
      </View>
    </View>
  )
}
