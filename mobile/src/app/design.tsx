// The design system's catalog: every token, component and block, live, in either theme.
// Like a Storybook that runs on the phone. Open it from Sources → Design system.
import {
  AVATAR_SIZE, Avatar, Badge, Banner, BottomSheet, ConfirmDialog, ReasonSheet, CountUp, FadeIn, KeyValueList, Loader, NavList, SectionCard, Stagger, StatusScreen, StepHeader,
  formatCompact, formatDate, formatINR, formatRelative, Button, Chip, Divider, EmptyState, Facepile, Icon, IconButton, ListRow, PageTitle, PersonHeader,
  PersonRow, PromiseCard, PromiseRow, QuietPile, ReasonChips, Row, SearchField, SectionLabel, Skeleton, SourceRow, Stack, Surface, Tabs,
  Text, ThemeProvider, TimelineEvent, TodayHeader, colors, radius, space, type, useTheme, type PromiseItem, type Scheme, type TypeVariant,
} from '@soloyolo/design-system'
import { useRouter } from 'expo-router'
import { useState, type ReactNode } from 'react'
import { REASONS } from '../lib/reasons'
import { ScrollView, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

const now = Date.now() / 1000
const SAMPLE: PromiseItem = {
  name: 'Rohan Mehta', owner: 'me', kind: 'promise', action: 'Send Rohan the rent agreement scan',
  source_text: 'Agreement ka scan bhej dena kal tak, broker maang raha hai', source_ts: now - 2 * 86400,
  networks: ['whatsapp'], reasons: ['asked again 3h ago', 'due tomorrow'],
}
const WAITING: PromiseItem = { ...SAMPLE, name: 'Priya Nair', owner: 'them', action: 'Share the hiring manager’s email', source_text: null, networks: ['linkedin'], reasons: ['overdue 1d'] }

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  const t = useTheme()
  return (
    <View style={{ marginTop: t.space.xxl }}>
      <View style={{ paddingHorizontal: t.space.xl, gap: t.space.xs, marginBottom: t.space.md }}>
        <Text variant="heading">{title}</Text>
        {note ? <Text variant="small" tone="secondary">{note}</Text> : null}
      </View>
      {children}
    </View>
  )
}

function Specimen({ name, children }: { name: string; children: ReactNode }) {
  const t = useTheme()
  return (
    <View style={{ paddingHorizontal: t.space.xl, marginBottom: t.space.lg, gap: t.space.sm }}>
      <Text variant="label" tone="tertiary">{name}</Text>
      {children}
    </View>
  )
}

function Catalog() {
  const t = useTheme()
  const [tab, setTab] = useState<'a' | 'b'>('a')
  const [q, setQ] = useState('')
  const [sheet, setSheet] = useState(false)
  const [dialog, setDialog] = useState(false)
  const [why, setWhy] = useState(false)
  const [replay, setReplay] = useState(0)
  const swatches = Object.keys(colors.light) as (keyof typeof colors.light)[]
  return (
    <View style={{ backgroundColor: t.color.background }}>
      <Section title="Color" note="Semantic tokens: name what a color is for. Components never use raw hex.">
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: t.space.md, paddingHorizontal: t.space.xl }}>
          {swatches.map((k) => (
            <View key={k} style={{ width: 96, gap: 4 }}>
              <View style={{ height: 44, borderRadius: t.radius.md, backgroundColor: t.color[k], borderWidth: 0.5, borderColor: t.color.border }} />
              <Text variant="caption" numberOfLines={1}>{k}</Text>
              <Text variant="caption" tone="tertiary" numberOfLines={1}>{t.color[k]}</Text>
            </View>
          ))}
        </View>
      </Section>
      <Section title="Type" note="One family for UI, the serif only for promise sentences. Hierarchy from size and weight.">
        {(Object.keys(type) as TypeVariant[]).map((v) => (
          <Specimen key={v} name={`${v} · ${type[v].fontSize}/${type[v].lineHeight}`}>
            <Text variant={v} numberOfLines={1}>{v === 'display' ? '9' : v.startsWith('sentence') ? 'You said you’d send the scan' : 'Good morning, three things'}</Text>
          </Specimen>
        ))}
      </Section>
      <Section title="Space and radius" note="A 4-point grid. Radius grows with the size of the object.">
        <Stack gap="sm" padX="xl">
          {(Object.keys(space) as (keyof typeof space)[]).filter((k) => space[k] > 0).map((k) => (
            <Row key={k} gap="md"><View style={{ width: space[k], height: 12, backgroundColor: t.color.accent, borderRadius: 2 }} /><Text variant="caption">{k} · {space[k]}</Text></Row>
          ))}
        </Stack>
        <Row gap="md" wrap padX="xl" style={{ marginTop: t.space.lg }}>
          {(Object.keys(radius) as (keyof typeof radius)[]).map((k) => (
            <View key={k} style={{ alignItems: 'center', gap: 4 }}>
              <View style={{ width: 56, height: 56, borderRadius: Math.min(radius[k], 28), backgroundColor: t.color.surface, borderWidth: 1, borderColor: t.color.border }} />
              <Text variant="caption">{k}</Text>
            </View>
          ))}
        </Row>
      </Section>
      <Section title="Components">
        <Specimen name="Button: primary · secondary · ghost · danger">
          <Row gap="sm" wrap><Button label="Primary" variant="primary" /><Button label="Secondary" /><Button label="Ghost" variant="ghost" /><Button label="Delete" variant="danger" /></Row>
          <Row gap="sm" wrap><Button label="Small" size="sm" icon="checkmark" /><Button label="Loading" loading /><Button label="Disabled" disabled /><IconButton icon="chevron-down" label="Close" /></Row>
        </Specimen>
        <Specimen name="Chip and ReasonChips"><Row gap="sm"><Chip label="neutral" /><Chip label="due tomorrow" tone="hot" /></Row><ReasonChips reasons={SAMPLE.reasons} /></Specimen>
        <Specimen name="Badge"><Row gap="md"><Badge /><Badge count={3} /></Row></Specimen>
        <Specimen name="Avatar sizes · Facepile">
          <Row gap="md">{(Object.keys(AVATAR_SIZE) as (keyof typeof AVATAR_SIZE)[]).map((s) => <Avatar key={s} name="Rohan Mehta" size={s} />)}</Row>
          <Facepile names={['Kabir Anand', 'Arjun Sethi', 'Meera Iyer', 'Tanvi Rao']} />
        </Specimen>
        <Specimen name="Icon"><Row gap="md" wrap>{(['sunny', 'people', 'albums', 'git-network', 'checkmark', 'close', 'refresh', 'logo-whatsapp', 'logo-linkedin', 'logo-instagram', 'logo-x'] as const).map((n) => <Icon key={n} name={n} size="lg" tone="primary" />)}</Row></Specimen>
        <Specimen name="SearchField"><SearchField value={q} onChangeText={setQ} /></Specimen>
        <Specimen name="Tabs"><View style={{ marginHorizontal: -t.space.xl }}><Tabs value={tab} onChange={setTab} items={[{ key: 'a', label: 'Promises' }, { key: 'b', label: 'Timeline' }]} /></View></Specimen>
        <Specimen name="Surface: card · outline · raised · dashed">
          <Surface><Text>Card</Text></Surface><Surface variant="outline"><Text>Outline</Text></Surface><Surface variant="raised"><Text>Raised</Text></Surface><Surface variant="dashed"><Text>Dashed</Text></Surface>
        </Specimen>
        <Specimen name="Skeleton · Divider"><Skeleton width="70%" /><Skeleton width="45%" height={10} /><Divider /></Specimen>
        <SectionLabel trailing={<Text variant="caption" tone="tertiary">trailing</Text>}>SectionLabel</SectionLabel>
        <ListRow lead={<Avatar name="Ma" />} title="ListRow" subtitle="lead · title · subtitle · trailing" trailing={<Text variant="caption" tone="tertiary">2d</Text>} onPress={() => {}} />
        <View style={{ marginTop: t.space.lg }}><EmptyState title="Nothing you said you’d do needs you today." body="EmptyState: what’s missing, and what happens next." /></View>
      </Section>
      <Section title="Feedback" note="Banner: a state worth knowing before reading the screen. Sheet: a secondary choice. Dialog: a decision that's hard to undo. ReasonSheet: why, asked after the action, skippable.">
        <Stack gap="sm" padX="lg">
          <Banner tone="warning" title="WhatsApp isn’t syncing" body="Last message arrived 13 hours ago. New promises won’t show up until your Mac syncs again." action={{ label: 'Open sources', onPress: () => {} }} />
          <Banner tone="info" title="Telegram not paired" body="Pair it to get Today’s items every morning at 07:30." />
          <Banner tone="success" title="LinkedIn imported" body="312 messages read and 4 promises found." />
          <Banner tone="danger" title="Import failed" body="We couldn’t read this file. Export it again as JSON, then try once more." />
        </Stack>
        <Row gap="sm" padX="xl" style={{ marginTop: t.space.lg }}>
          <Button label="Open sheet" onPress={() => setSheet(true)} />
          <Button label="Open dialog" onPress={() => setDialog(true)} />
          <Button label="Ask why" onPress={() => setWhy(true)} />
        </Row>
        <ReasonSheet open={why} title="Why isn’t it needed?" subtitle="Return Kabir’s tripod" reasons={REASONS}
                     onPick={() => setWhy(false)} onSkip={() => setWhy(false)} />
        <BottomSheet open={sheet} onClose={() => setSheet(false)} title="Snooze until" subtitle="It leaves Today and comes back then."
                     footer={<Button label="Snooze 3 days" variant="primary" onPress={() => setSheet(false)} />}>
          <NavList rows={[{ label: 'Tomorrow morning', onPress: () => setSheet(false) }, { label: 'This weekend', onPress: () => setSheet(false) }, { label: 'Next week', onPress: () => setSheet(false) }]} />
        </BottomSheet>
        <ConfirmDialog open={dialog} destructive title="Unlink WhatsApp?" body="soloyolo stops reading your chats. Promises already found stay on your list."
                       confirmLabel="Unlink WhatsApp" onCancel={() => setDialog(false)} onConfirm={() => setDialog(false)} />
      </Section>
      <Section title="Layout" note="SectionCard groups rows on the paper; KeyValueList and NavList are what goes inside. StepHeader for short setups.">
        <Stack gap="lg">
          <SectionCard title="WhatsApp" action={{ label: 'Unlink', onPress: () => {} }}>
            <KeyValueList items={[{ label: 'Messages', value: '5,602' }, { label: 'Last sync', value: '4 min ago', tone: 'success' }, { label: 'Group chats', value: 'Read as evidence' }]} />
          </SectionCard>
          <SectionCard title="Settings">
            <NavList rows={[{ icon: 'time-outline', label: 'Morning message', value: '07:30', onPress: () => {} }, { icon: 'link-outline', label: 'Linked sources', value: '2', onPress: () => {} }, { icon: 'settings-outline', label: 'Privacy log', onPress: () => {} }]} />
          </SectionCard>
          <View style={{ paddingHorizontal: t.space.xl }}><StepHeader step={2} total={3} label="Pair Telegram" /></View>
        </Stack>
      </Section>
      <Section title="Motion" note="Under 400ms, no bounce, off when the phone asks for reduced motion.">
        <Stack gap="md" padX="xl">
          <Row gap="lg"><CountUp key={replay} value={5602} format={(n) => n.toLocaleString('en-IN')} variant="display" /><Loader label="Reading your chats..." /></Row>
          <View key={`s${replay}`}><Stagger>{['Rohan Mehta', 'Ma', 'Priya Nair'].map((n) => <Row key={n} gap="sm" style={{ paddingVertical: 4 }}><Avatar name={n} size="sm" /><Text>{n}</Text></Row>)}</Stagger></View>
          <View style={{ alignSelf: 'flex-start' }}><Button label="Replay" size="sm" icon="refresh" onPress={() => setReplay((x) => x + 1)} /></View>
          <FadeIn><Text variant="small" tone="secondary">FadeIn, Stagger, CountUp, Loader</Text></FadeIn>
        </Stack>
      </Section>
      <Section title="Format" note="One way to write numbers and time. Screens never format by hand.">
        <View style={{ marginHorizontal: t.space.lg }}><SectionCard>
          <KeyValueList items={[{ label: 'formatINR(14500)', value: formatINR(14500) }, { label: 'formatCompact(15400)', value: formatCompact(15400) },
                                { label: 'formatRelative(4 min)', value: formatRelative(now - 240) }, { label: 'formatRelative(3 days)', value: formatRelative(now - 3 * 86400) },
                                { label: 'formatDate(2025)', value: formatDate(1744329600) }]} />
        </SectionCard></View>
      </Section>
      <Section title="Patterns" note="Result screens: success, error, pending, info. Shown here in frames; in the app they fill the screen.">
        <Stack gap="md" padX="lg">
          {(['success', 'error', 'pending', 'info'] as const).map((tone) => (
            <View key={tone} style={{ height: 360, borderRadius: t.radius.card, overflow: 'hidden', borderWidth: 1, borderColor: t.color.border }}>
              <StatusScreen tone={tone} title={{ success: 'Chats imported', error: 'Import failed', pending: 'Reading your chats', info: 'Telegram not paired' }[tone]}
                            body={{ success: '312 messages read and 4 promises found.', error: 'We couldn’t read this file. Export it again as JSON.', pending: 'This takes a minute or two.', info: 'Pair it to get Today’s items every morning.' }[tone]}
                            primary={tone === 'pending' ? undefined : { label: { success: 'Go to Today', error: 'Try again', info: 'Pair Telegram' }[tone], onPress: () => {} }} />
            </View>
          ))}
        </Stack>
      </Section>
      <Section title="Blocks" note="Whole patterns, imported as they are. Screens are made of these.">
        <Specimen name="TodayHeader"><View style={{ marginHorizontal: -t.space.xl }}><TodayHeader count={3} /></View></Specimen>
        <View style={{ marginHorizontal: 0 }}><Text variant="label" tone="tertiary" style={{ paddingHorizontal: t.space.xl, marginBottom: t.space.sm }}>PromiseCard (swipe it)</Text>
          <PromiseCard item={SAMPLE} onDone={() => {}} onDismiss={() => {}} /><PromiseCard item={WAITING} onDone={() => {}} onDismiss={() => {}} /></View>
        <Text variant="label" tone="tertiary" style={{ paddingHorizontal: t.space.xl, marginVertical: t.space.sm }}>PromiseRow · PersonRow</Text>
        <PromiseRow item={SAMPLE} state="today" /><PromiseRow item={WAITING} state="quiet" showPerson={false} /><PersonRow name="Ma" networks={['whatsapp']} youOwe={2} last={now - 2400} />
        <Text variant="label" tone="tertiary" style={{ paddingHorizontal: t.space.xl, marginVertical: t.space.sm }}>QuietPile</Text>
        <QuietPile names={['Kabir Anand', 'Arjun Sethi', 'Meera Iyer', 'Tanvi Rao', 'Ma']} />
        <Text variant="label" tone="tertiary" style={{ paddingHorizontal: t.space.xl, marginTop: t.space.lg }}>PersonHeader · TimelineEvent</Text>
        <PersonHeader name="Rohan Mehta" network="whatsapp" subtitle="last talked 3h ago" actions={[{ icon: 'chatbubble-outline', label: 'Open chat', onPress: () => {} }, { icon: 'notifications-off-outline', label: 'Mute', onPress: () => {} }]} />
        <TimelineEvent who="Rohan" text="Agreement ka scan bhej dena kal tak" ts={now - 2 * 86400} fromMe={false} isSource />
        <TimelineEvent who="Rohan" text="haan bhejta hoon" ts={now - 2 * 86400 + 600} fromMe />
        <Text variant="label" tone="tertiary" style={{ paddingHorizontal: t.space.xl, marginVertical: t.space.sm }}>SourceRow</Text>
        <View style={{ marginHorizontal: t.space.lg }}><Surface variant="outline" radius="xl" padded={false}><SourceRow icon="logo-whatsapp" name="WhatsApp" state="synced 4m ago" tone="on" note="5,602 messages" /><SourceRow icon="logo-slack" name="Slack" state="on hold" tone="hold" note="Waiting on your employer" last /></Surface></View>
      </Section>
    </View>
  )
}

export default function DesignScreen() {
  const outer = useTheme()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const [scheme, setScheme] = useState<Scheme>(outer.scheme)
  return (
    <ThemeProvider scheme={scheme}>
      <Themed scheme={scheme} setScheme={setScheme} top={insets.top} close={() => (router.canGoBack() ? router.back() : router.replace('/'))} />
    </ThemeProvider>
  )
}

function Themed({ scheme, setScheme, top, close }: { scheme: Scheme; setScheme: (s: Scheme) => void; top: number; close: () => void }) {
  const t = useTheme()
  return (
    <ScrollView style={{ backgroundColor: t.color.background }} contentContainerStyle={{ paddingTop: top + t.space.md, paddingBottom: 80 }}>
      <Row padX="lg" justify="space-between"><IconButton icon="chevron-down" label="Close" onPress={close} /></Row>
      <PageTitle title="Design system" subtitle="@soloyolo/design-system: tokens, components and blocks. Everything on every screen comes from here." />
      <View style={{ marginTop: t.space.md }}>
        <Tabs value={scheme} onChange={setScheme} items={[{ key: 'light', label: 'Light' }, { key: 'dark', label: 'Dark' }]} />
      </View>
      <Catalog />
    </ScrollView>
  )
}
