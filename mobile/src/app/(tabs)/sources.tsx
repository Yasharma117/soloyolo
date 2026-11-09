import { Button, PageTitle, SectionLabel, SourceRow, Surface, Text, useTheme, type IconName } from '@soloyolo/design-system'
import { useRouter } from 'expo-router'
import { ScrollView, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { serverUrl, useData, useMode } from '../../lib/api'
import { ago, type Status } from '../../lib/types'

type Src = { icon: IconName; name: string; state: string; tone: 'on' | 'off' | 'hold'; note: string }

export default function Sources() {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const mode = useMode()
  const { data: s } = useData<Status>('/api/status')
  const has = Object.fromEntries((s?.networks ?? []).map((n) => [n.network, n]))
  const groups = (s?.groups ?? []).reduce((a, g) => a + g.lines, 0)
  const imported = (n: string, icon: IconName, name: string, how: string): Src => has[n]
    ? { icon, name, state: `imported ${ago(has[n]!.last)} ago`, tone: 'on', note: `${has[n]!.messages.toLocaleString()} messages` }
    : { icon, name, state: 'not imported', tone: 'off', note: how }
  const messages: Src[] = [
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
  const daily: Src[] = [
    { icon: 'paper-plane-outline', name: 'Telegram', state: s?.telegram ? 'paired' : 'not paired', tone: s?.telegram ? 'on' : 'off',
      note: s?.telegram ? 'Today’s items at 07:30, with Done / Not needed / Still on' : 'Run: python -m spike telegram pair' },
    { icon: 'reader-outline', name: 'Reading', state: s?.last_read ? `${ago(s.last_read)} ago` : 'never', tone: s?.last_read ? 'on' : 'off',
      note: 'Claude reads the chats that changed, every 30 minutes' },
  ]
  const group = (rows: Src[]) => (
    <View style={{ marginHorizontal: t.space.lg }}>
      <Surface variant="outline" radius="xl" padded={false} style={{ overflow: 'hidden' }}>
        {rows.map((r, i) => <SourceRow key={r.name} {...r} last={i === rows.length - 1} />)}
      </Surface>
    </View>
  )
  return (
    <ScrollView style={{ backgroundColor: t.color.background }} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}>
      <PageTitle title="Sources" subtitle={mode === 'live' ? `Where soloyolo reads from. Connected to your Mac (${serverUrl}).` : 'Where soloyolo reads from. Showing the demo: your Mac isn’t reachable.'} />
      <SectionLabel>Messages</SectionLabel>
      {group(messages)}
      <SectionLabel>Every morning</SectionLabel>
      {group(daily)}
      <SectionLabel>Privacy</SectionLabel>
      <View style={{ marginHorizontal: t.space.lg }}>
        <Surface variant="outline" radius="xl">
          <Text variant="body" tone="secondary">
            {s?.disclosures.length
              ? `Text from your store has been sent to: ${s.disclosures.join(', ')}. Each send is logged before it happens.`
              : 'No text from your store has left your Mac.'}
          </Text>
        </Surface>
      </View>
      {s?.muted.length ? (
        <>
          <SectionLabel>Muted</SectionLabel>
          {s.muted.map((m) => (
            <View key={m.id} style={{ paddingHorizontal: t.space.lg, marginBottom: t.space.xs }}>
              <Button label={`${m.name}: unmute or view`} variant="ghost" onPress={() => router.push({ pathname: '/person/[id]', params: { id: String(m.id) } })} />
            </View>
          ))}
        </>
      ) : null}
      <SectionLabel>For builders</SectionLabel>
      <View style={{ paddingHorizontal: t.space.lg, alignItems: 'flex-start' }}>
        <Button label="Design system" icon="color-palette-outline" onPress={() => router.push('/design')} />
      </View>
    </ScrollView>
  )
}
