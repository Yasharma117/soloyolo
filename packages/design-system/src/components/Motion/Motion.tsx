// Motion primitives. Short (under 400ms), calm, and off when the phone asks for reduced motion.
import { Children, useEffect, useState, type ReactNode } from 'react'
import { View } from 'react-native'
import Animated, { FadeInDown, useReducedMotion } from 'react-native-reanimated'
import { useTheme } from '../../theme'
import { Text, type TextPropsDS } from '../Text/Text'

/** Rise into place once, on mount. */
export function FadeIn({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const t = useTheme()
  const reduced = useReducedMotion()
  if (reduced) return <View>{children}</View>
  return <Animated.View entering={FadeInDown.duration(t.motion.base + 60).delay(delay)}>{children}</Animated.View>
}

/** Children arrive one after another, `step` ms apart: a list landing, not popping in at once. */
export function Stagger({ children, step = 60 }: { children: ReactNode; step?: number }) {
  return <>{Children.toArray(children).map((c, i) => <FadeIn key={i} delay={i * step}>{c}</FadeIn>)}</>
}

/** A number that counts up to its value (counts, not money that must read exactly at once). */
export function CountUp({ value, duration = 600, format = (n: number) => String(n), ...text }: { value: number; duration?: number; format?: (n: number) => string } & TextPropsDS) {
  const reduced = useReducedMotion()
  const [shown, setShown] = useState(reduced ? value : 0)
  useEffect(() => {
    if (reduced) return
    const start = Date.now()
    const id = setInterval(() => {
      const k = Math.min(1, (Date.now() - start) / duration)
      setShown(Math.round(value * (1 - Math.pow(1 - k, 3))))
      if (k === 1) clearInterval(id)
    }, 16)
    return () => clearInterval(id)
  }, [value, duration, reduced])
  return <Text {...text}>{format(reduced ? value : shown)}</Text>
}

/** Three dots for "Reading your chats...". Steady when motion is reduced. */
export function Loader({ label }: { label?: string }) {
  const t = useTheme()
  const reduced = useReducedMotion()
  const [n, setN] = useState(0)
  useEffect(() => {
    if (reduced) return
    const id = setInterval(() => setN((x) => (x + 1) % 3), 320)
    return () => clearInterval(id)
  }, [reduced])
  return (
    <View accessibilityRole="progressbar" accessibilityLabel={label ?? 'Loading'} style={{ alignItems: 'center', gap: t.space.sm }}>
      <View style={{ flexDirection: 'row', gap: 6 }}>
        {[0, 1, 2].map((i) => <View key={i} style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: t.color.accent, opacity: reduced || i === n ? 1 : 0.3 }} />)}
      </View>
      {label ? <Text variant="small" tone="secondary">{label}</Text> : null}
    </View>
  )
}
