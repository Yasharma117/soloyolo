import { Button, ChipGroup, NavList, PageTitle, SectionCard, SectionLabel, SourceRow, StatRow, StatTile, Surface, Text, TopBar, Wash, formatCompact, useScrollChrome, useTheme, type IconName } from '@soloyolo/design-system'
import { useRouter } from 'expo-router'
import { View } from 'react-native'
import Animated from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { serverUrl, useData, useMode } from '../../lib/api'
import { useAppearance, type Appearance } from '../../lib/appearance'
import { ago, type MergePair, type Status } from '../../lib/types'

type Src = { icon: IconName; name: string; state: string; tone: 'on' | 'off' | 'hold'; note: string }

export default function Sources() {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const mode = useMode()
  const chrome = useScrollChrome()
  const look = useAppearance()
  const { data: s } = useData<Status>('/api/status')
  const pairs = useData<MergePair[]>('/api/merges').data
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
    <View style={{ flex: 1, backgroundColor: t.color.background }}>
    <Animated.ScrollView showsVerticalScrollIndicator={false} onScroll={chrome.onScroll} scrollEventThrottle={16} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}>
      <Wash />
      <PageTitle title="Sources" subtitle={mode === 'live' ? `Where soloyolo reads from. Connected to your Mac (${serverUrl}).` : 'Where soloyolo reads from. Showing the demo: your Mac isn’t reachable.'} />
      {s ? (
        <View style={{ marginTop: t.space.md }}>
          <StatRow>
            <StatTile label="Messages read" value={formatCompact(s.networks.reduce((a, n) => a + n.messages, 0))} />
            <StatTile label="Sources on" value={String(s.networks.length)} hint={`of ${messages.length}`} />
            <StatTile label="Last read" value={s.last_read ? `${ago(s.last_read)} ago` : 'never'} tone={s.last_read ? 'primary' : 'danger'} />
          </StatRow>
        </View>
      ) : null}
      <SectionLabel>Review</SectionLabel>
      <SectionCard>
        <NavList rows={[
          { icon: 'people-outline', label: 'Same person?', description: 'Chats that look like one person', value: pairs?.length ? String(pairs.length) : undefined, onPress: () => router.push('/merges') },
          { icon: 'sparkles', label: 'This week', description: 'What closed and what went quiet', onPress: () => router.push('/week') },
          { icon: 'settings-outline', label: 'Set up', description: 'WhatsApp, Telegram and your exports', onPress: () => router.push('/welcome') },
        ]} />
      </SectionCard>
      <SectionLabel>Messages</SectionLabel>
      {group(messages)}
      <SectionLabel>Every morning</SectionLabel>
      {group(daily)}
      <SectionLabel>Appearance</SectionLabel>
      <View style={{ paddingHorizontal: t.space.lg }}>
        <ChipGroup<Appearance> label="Appearance" value={look.appearance} onChange={look.set}
                               options={[{ value: 'system', label: 'Match phone' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]} />
      </View>
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
        <View style={{ height: t.space.sm }} />
        <Button label="Every screen" icon="albums-outline" onPress={() => router.push('/screens')} />
      </View>
    </Animated.ScrollView>
    <TopBar y={chrome.y} title="Sources" at={60} />
    </View>
  )
}
