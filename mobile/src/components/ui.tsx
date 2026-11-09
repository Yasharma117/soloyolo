import Ionicons from '@expo/vector-icons/Ionicons'
import { LinearGradient } from 'expo-linear-gradient'
import type { ReactNode } from 'react'
import { StyleSheet, Text, View, type TextStyle, type ViewStyle } from 'react-native'
import Svg, { Circle, Defs, Pattern, Rect } from 'react-native-svg'
import { HOT, type Item } from '../lib/types'
import { orbColors, serif, usePalette } from '../lib/theme'

/** A Mesh-style gradient orb with the person's initials. */
export function Orb({ name, size = 32 }: { name: string; size?: number }) {
  const words = name.replace(/[\uD800-\uDFFF()[\]{}.,!?'"@#*_~-]/g, '').trim().split(/\s+/)
  const initials = ((words[0]?.[0] ?? '') + (words.length > 1 ? words[words.length - 1]![0] : '')).toUpperCase() || '?'
  const [a, b] = orbColors(name)
  return (
    <LinearGradient colors={[a, b]} start={{ x: 0.15, y: 0.1 }} end={{ x: 0.9, y: 0.95 }}
                    style={{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ color: '#fff', fontSize: size * 0.38, fontWeight: '700' }}>{initials}</Text>
    </LinearGradient>
  )
}

/** Atoms' dotted paper, fading out behind a header. */
export function DotGrid({ height = 220 }: { height?: number }) {
  const c = usePalette()
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { height }]}>
      <Svg width="100%" height={height}>
        <Defs>
          <Pattern id="dots" width={10} height={10} patternUnits="userSpaceOnUse">
            <Circle cx={2} cy={2} r={1.1} fill={c.dot} />
          </Pattern>
        </Defs>
        <Rect width="100%" height={height} fill="url(#dots)" />
      </Svg>
      <LinearGradient colors={['transparent', c.ground]} style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: height * 0.7 }} />
    </View>
  )
}

const NET_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  whatsapp: 'logo-whatsapp', linkedin: 'logo-linkedin', instagram: 'logo-instagram', x: 'logo-x', slack: 'logo-slack',
  imessage: 'chatbubble', sms: 'chatbox', telegram: 'paper-plane',
}
export const NET_NAME: Record<string, string> = {
  whatsapp: 'WhatsApp', linkedin: 'LinkedIn', instagram: 'Instagram', x: 'X', slack: 'Slack', imessage: 'iMessage', sms: 'SMS', telegram: 'Telegram',
}

export function NetIcon({ network, size = 13, color }: { network: string; size?: number; color?: string }) {
  const c = usePalette()
  return <Ionicons name={NET_ICON[network] ?? 'chatbubble-ellipses'} size={size} color={color ?? c.ink3} />
}

/** Small uppercase label with air around the letters, as Mesh sections its lists. */
export function Label({ children, right, style }: { children: string; right?: ReactNode; style?: ViewStyle }) {
  const c = usePalette()
  return (
    <View style={[styles.label, style]}>
      <Text style={{ color: c.ink3, fontSize: 11, fontWeight: '600', letterSpacing: 1.2 }}>{children.toUpperCase()}</Text>
      {right}
    </View>
  )
}

export function Chips({ reasons, style }: { reasons?: string[]; style?: ViewStyle }) {
  const c = usePalette()
  if (!reasons?.length) return null
  return (
    <View style={[{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }, style]}>
      {reasons.slice(0, 3).map((r) => {
        const hot = HOT.test(r)
        return (
          <View key={r} style={{ paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999, backgroundColor: hot ? c.hotSoft : c.raised }}>
            <Text style={{ color: hot ? c.hot : c.ink2, fontSize: 12, fontWeight: hot ? '600' : '500' }}>{r}</Text>
          </View>
        )
      })}
    </View>
  )
}

const lower = (s: string) => (s.length > 1 && s[1] === s[1]!.toLowerCase() ? s[0]!.toLowerCase() + s.slice(1) : s)

/** The promise as a sentence, its key words underlined (Atoms). */
export function Sentence({ item, size = 21, style }: { item: Item; size?: number; style?: TextStyle }) {
  const c = usePalette()
  const first = item.name.split(' ')[0]!
  const lead = item.owner === 'me'
    ? item.kind === 'ask' ? `${first} asked you to ` : 'You said you’d '
    : item.kind === 'ask' ? `You asked ${first} to ` : `Waiting on ${first} to `
  return (
    <Text style={[{ fontFamily: serif, fontSize: size, lineHeight: Math.round(size * 1.32), color: c.ink }, style]}>
      <Text style={{ color: c.ink2 }}>{lead}</Text>
      <Text style={{ textDecorationLine: 'underline', textDecorationColor: c.accent }}>{lower(item.action)}</Text>
    </Text>
  )
}

export function Quote({ text, style }: { text?: string | null; style?: ViewStyle }) {
  const c = usePalette()
  if (!text) return null
  return (
    <View style={[{ flexDirection: 'row', gap: 8 }, style]}>
      <View style={{ width: 2, borderRadius: 1, backgroundColor: c.line }} />
      <Text style={{ flex: 1, color: c.ink2, fontSize: 14, lineHeight: 19 }} numberOfLines={2}>“{text}”</Text>
    </View>
  )
}

/** HEY-style page title: big, plain, with one line saying what this is for. */
export function Title({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  const c = usePalette()
  return (
    <View style={{ paddingHorizontal: 20, paddingTop: 12, paddingBottom: 4 }}>
      <Text style={{ color: c.ink, fontSize: 32, fontWeight: '800', letterSpacing: -0.6 }}>{title}</Text>
      {subtitle ? <Text style={{ color: c.ink2, fontSize: 15, lineHeight: 21, marginTop: 4 }}>{subtitle}</Text> : null}
      {children}
    </View>
  )
}

const styles = StyleSheet.create({
  label: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, marginTop: 28, marginBottom: 10 },
})
