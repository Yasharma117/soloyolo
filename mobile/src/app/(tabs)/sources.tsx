import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { LargeTitle, SectionTitle } from '../../components/ui'
import { serverUrl, useData, useMode } from '../../lib/api'
import { usePalette } from '../../lib/theme'
import { ago, type Status } from '../../lib/types'

type Row = { icon: keyof typeof Ionicons.glyphMap; name: string; state: string; tone: 'on' | 'off' | 'hold'; note: string }

export default function Sources() {
  const c = usePalette()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const mode = useMode()
  const { data: s } = useData<Status>('/api/status')
  const has = Object.fromEntries((s?.networks ?? []).map((n) => [n.network, n]))
  const groups = (s?.groups ?? []).reduce((a, g) => a + g.lines, 0)
  const imported = (n: string, icon: Row['icon'], name: string, how: string): Row => has[n]
    ? { icon, name, state: `imported ${ago(has[n]!.last)} ago`, tone: 'on', note: `${has[n]!.messages.toLocaleString()} messages` }
    : { icon, name, state: 'not imported', tone: 'off', note: how }
  const messages: Row[] = [
    has.whatsapp
      ? { icon: 'logo-whatsapp', name: 'WhatsApp', state: `synced ${ago(has.whatsapp.last)} ago`, tone: 'on',
          note: `${has.whatsapp.messages.toLocaleString()} messages${groups ? ` · groups read as evidence (${groups.toLocaleString()} lines)` : ''}` }
      : { icon: 'logo-whatsapp', name: 'WhatsApp', state: 'not linked', tone: 'off', note: 'Link from your Mac: connectord link --phone 91…' },
    imported('linkedin', 'logo-linkedin', 'LinkedIn', 'From your data export'),
    imported('instagram', 'logo-instagram', 'Instagram', 'From your data export (JSON)'),
    imported('x', 'logo-x', 'X', 'From your archive'),
    { icon: 'logo-slack', name: 'Slack', state: 'on hold', tone: 'hold', note: 'Work Slack: waiting on your employer’s written OK' },
    { icon: 'notifications-outline', name: 'Android notifications', state: 'not set up', tone: 'off', note: 'Catches people chasing you on any app' },
  ]
  const daily: Row[] = [
    { icon: 'paper-plane-outline', name: 'Telegram', state: s?.telegram ? 'paired' : 'not paired', tone: s?.telegram ? 'on' : 'off',
      note: s?.telegram ? 'Today’s items at 07:30, with Done / Not needed / Still on' : 'Run: python -m spike telegram pair' },
    { icon: 'reader-outline', name: 'Reading', state: s?.last_read ? `${ago(s.last_read)} ago` : 'never', tone: s?.last_read ? 'on' : 'off',
      note: 'Claude reads the chats that changed, every 30 minutes' },
  ]
  const tone = { on: c.live, off: c.ink3, hold: c.hot }
  const group = (rows: Row[]) => (
    <View style={[styles.group, { backgroundColor: c.card }]}>
      {rows.map((r, i) => (
        <View key={r.name} style={styles.row}>
          <Ionicons name={r.icon} size={20} color={c.ink2} style={{ marginTop: 1 }} />
          <View style={[styles.rowBody, i < rows.length - 1 && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.line }]}>
            <View style={styles.line}>
              <Text style={{ color: c.ink, fontSize: 17 }}>{r.name}</Text>
              <Text style={{ color: tone[r.tone], fontSize: 14 }}>{r.state}</Text>
            </View>
            <Text style={{ color: c.ink2, fontSize: 13, marginTop: 2 }}>{r.note}</Text>
          </View>
        </View>
      ))}
    </View>
  )
  return (
    <ScrollView style={{ backgroundColor: c.ground }} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 40 }}>
      <LargeTitle title="Sources" subtitle={mode === 'live' ? `Connected to your Mac (${serverUrl})` : 'Showing the demo: your Mac isn’t reachable'} />
      <SectionTitle>Messages</SectionTitle>
      {group(messages)}
      <SectionTitle>Every morning</SectionTitle>
      {group(daily)}
      <SectionTitle>Privacy</SectionTitle>
      <View style={[styles.group, { backgroundColor: c.card, padding: 14 }]}>
        <Text style={{ color: c.ink2, fontSize: 15, lineHeight: 20 }}>
          {s?.disclosures.length
            ? `Text from your store has been sent to: ${s.disclosures.join(', ')}. Each send is logged before it happens.`
            : 'No text from your store has left your Mac.'}
        </Text>
      </View>
      {s?.muted.length ? (
        <>
          <SectionTitle>Muted</SectionTitle>
          <View style={[styles.group, { backgroundColor: c.card }]}>
            {s.muted.map((m) => (
              <Pressable key={m.id} style={[styles.row, { paddingVertical: 12 }]} onPress={() => router.push({ pathname: '/person/[id]', params: { id: String(m.id) } })}>
                <Text style={{ color: c.ink, fontSize: 17, flex: 1 }}>{m.name}</Text>
                <Ionicons name="chevron-forward" size={18} color={c.ink3} style={{ marginRight: 14 }} />
              </Pressable>
            ))}
          </View>
        </>
      ) : null}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  group: { marginHorizontal: 16, borderRadius: 14, overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'flex-start', paddingLeft: 14, gap: 12 },
  rowBody: { flex: 1, paddingVertical: 11, paddingRight: 14 },
  line: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 },
})
