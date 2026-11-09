import Ionicons from '@expo/vector-icons/Ionicons'
import { StyleSheet, Text, View, type TextStyle, type ViewStyle } from 'react-native'
import { HOT } from '../lib/types'
import { nameColor, usePalette } from '../lib/theme'

export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/)
  const initials = ((words[0]?.[0] ?? '') + (words.length > 1 ? words[words.length - 1]![0] : '')).toUpperCase() || '?'
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: nameColor(name), alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ color: '#fff', fontSize: size * 0.4, fontWeight: '600' }}>{initials}</Text>
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

/** The apps a person is on, as small glyphs; with `label`, the first app's name beside it. */
export function Apps({ networks = [], label = false }: { networks?: string[]; label?: boolean }) {
  const c = usePalette()
  if (!networks.length) return null
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      {networks.slice(0, label ? 1 : 3).map((n) => (
        <Ionicons key={n} name={NET_ICON[n] ?? 'chatbubble-ellipses'} size={13} color={c.ink3} />
      ))}
      {label && <Text style={{ color: c.ink2, fontSize: 13 }}>{NET_NAME[networks[0]!] ?? networks[0]}</Text>}
    </View>
  )
}

export function Chips({ reasons }: { reasons?: string[] }) {
  const c = usePalette()
  if (!reasons?.length) return null
  return (
    <View style={styles.chips}>
      {reasons.slice(0, 3).map((r) => {
        const hot = HOT.test(r)
        return (
          <View key={r} style={[styles.chip, { backgroundColor: hot ? c.hotSoft : c.raised }]}>
            <Text style={{ color: hot ? c.hot : c.ink2, fontSize: 13, fontWeight: hot ? '600' : '400' }}>{r}</Text>
          </View>
        )
      })}
    </View>
  )
}

export function Quote({ text, style }: { text?: string | null; style?: ViewStyle }) {
  const c = usePalette()
  if (!text) return null
  return (
    <View style={[{ borderLeftWidth: 2, borderLeftColor: c.line, paddingLeft: 10 }, style]}>
      <Text style={{ color: c.ink2, fontSize: 15, lineHeight: 20 }} numberOfLines={3}>
        “{text}”
      </Text>
    </View>
  )
}

export function SectionTitle({ children, style }: { children: string; style?: TextStyle }) {
  const c = usePalette()
  return <Text style={[styles.section, { color: c.ink2 }, style]}>{children.toUpperCase()}</Text>
}

export function LargeTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  const c = usePalette()
  return (
    <View style={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: 6 }}>
      <Text style={{ color: c.ink, fontSize: 34, fontWeight: '700', letterSpacing: 0.3 }}>{title}</Text>
      {subtitle ? <Text style={{ color: c.ink2, fontSize: 15, marginTop: 2 }}>{subtitle}</Text> : null}
    </View>
  )
}

const styles = StyleSheet.create({
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 9, paddingVertical: 4, borderRadius: 8 },
  section: { fontSize: 13, fontWeight: '600', letterSpacing: 0.3, paddingHorizontal: 20, marginTop: 24, marginBottom: 8 },
})
