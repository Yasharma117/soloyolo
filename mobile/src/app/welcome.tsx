// First run: the three things that make soloyolo work, in order. WhatsApp links from here (your number, then the
// code WhatsApp gives, typed on your phone) and exports found in Downloads are read from here (spike/setup.py);
// Your own Telegram chats link here (code, then password if set). Reading the chats for promises starts here too, and says when it sends text to Claude. Telegram is still paired on the Mac. With a soloyolo too old for /api/setup, each step shows what to run instead.
// ?state=new previews it with nothing set up.
import { Banner, Button, InlineError, Loader, NavList, Row, Stack, Text, NetworkIcon, OnboardingStep, PairingCode, Screen, SectionCard, StepHeader, TextField, formatCount, formatRelative, plural, useTheme, useToast, type StepState } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect, useState } from 'react'
import { View } from 'react-native'
import { liveToken, refresh, setupAct, useData } from '../lib/api'
import { NETWORK_NAMES, type LiveStatus, type SetupStatus, type Status } from '../lib/types'

const ON_PHONE = ['On your phone, open WhatsApp, then Linked devices.', 'Tap Link a device, then Link with phone number instead.', 'Type this code. It works for a few minutes.']

export default function Welcome() {
  const t = useTheme()
  const router = useRouter()
  const toast = useToast()
  const { state: preview } = useLocalSearchParams<{ state?: 'new' }>()
  const live = useData<Status>('/api/status').data
  const setup = useData<SetupStatus>('/api/setup').data
  const [phone, setPhone] = useState('')
  const [asking, setAsking] = useState(false)
  const [tgPhone, setTgPhone] = useState('')
  const [tgCode, setTgCode] = useState('')
  const extension = useData<LiveStatus>('/api/live/status').data
  const [token, setToken] = useState<string | null>(null)
  // a token alone isn't pairing: until the extension has reported once, keep showing how to pair it
  const heard = Object.values(extension?.networks ?? {}).some((x) => x && (x.enabled !== null || x.ok || x.error))
  const s = preview === 'new' ? { networks: [], telegram: false } : live
  const has = Object.fromEntries((s?.networks ?? []).map((n) => [n.network, n]))
  const wa = setup?.whatsapp
  const exports = ['linkedin', 'instagram', 'x'].filter((n) => has[n])
  const files = setup?.exports ?? []
  const linked = !!has.whatsapp || !!wa?.linked || wa?.state === 'linked'
  const done = [linked, !!s?.telegram, exports.length > 0]
  const at = done.indexOf(false) // the first one not done is the one you're on
  const state = (i: number): StepState => (done[i] ? 'done' : i === at ? 'now' : 'later')
  const check = { label: 'Check again', onPress: refresh }
  // while WhatsApp is being asked for a code, or waiting for you to type it, look again every two seconds
  const read = preview === 'new' ? undefined : setup?.read
  const unread = preview === 'new' ? 0 : setup?.unread ?? 0
  const tg = setup?.telegram
  const tgAsks = tg?.state === 'code' || tg?.state === 'password' || tg?.state === 'checking'
  const waiting = wa?.state === 'starting' || wa?.state === 'code' || read?.state === 'reading' || tg?.state === 'starting' || tg?.state === 'checking'
  useEffect(() => {
    if (!waiting) return
    const id = setInterval(refresh, 2000)
    return () => clearInterval(id)
  }, [waiting])
  const act = async (what: 'whatsapp' | 'sync' | 'import' | 'read' | 'telegram' | 'telegram-code', body = {}) => {
    setAsking(true)
    try {
      await setupAct(what, body)
    } catch (e) {
      toast.show(e instanceof Error && e.message ? e.message : 'Couldn’t reach soloyolo on your Mac. Check it’s running, then try again.')
    } finally {
      setAsking(false)
    }
  }
  return (
    <Screen>
      <Screen.Header title="Set up soloyolo" subtitle="Three steps. This screen updates as each one finishes." onBack={router.canGoBack() ? router.back : undefined}>
        <StepHeader step={done.filter(Boolean).length} total={3} label={at < 0 ? 'All set' : undefined} />
      </Screen.Header>
      <Screen.Body>
        {wa?.linked && !wa.syncing && wa.state !== 'starting' ? (
          <View style={{ paddingHorizontal: t.space.lg }}>
            <Banner tone="warning" title="WhatsApp isn’t syncing" body="It’s linked, but nothing is reading new messages right now."
                    action={{ label: 'Start syncing', onPress: () => act('sync') }} />
          </View>
        ) : null}
        <OnboardingStep n={1} icon="logo-whatsapp" title="Link WhatsApp" state={state(0)}
                        body="soloyolo reads your chats to find what you said you’d do, and what people said they’d do for you."
                        how={setup ? undefined : 'connectord link --phone 91…'}
                        doneNote={has.whatsapp ? `${formatCount(has.whatsapp.messages)} messages read` : 'Linked. Your chats are coming in.'}
                        action={!setup ? check : wa?.state === 'code' || wa?.state === 'starting' ? undefined
                          : { label: 'Get code', onPress: () => act('whatsapp', { phone }), loading: asking, disabled: phone.replace(/\D/g, '').length < 8 }}>
          {setup && wa?.state === 'error' && wa.message ? <View style={{ marginHorizontal: -t.space.lg }}><InlineError title="WhatsApp didn’t link." body={wa.message} /></View> : null}
          {setup && wa?.state === 'starting' ? <Loader label="Asking WhatsApp for a code..." /> : null}
          {setup && wa?.state === 'code' && wa.code ? <PairingCode code={wa.code} steps={ON_PHONE} /> : null}
          {setup && wa?.state !== 'code' && wa?.state !== 'starting' ? (
            <TextField label="Your WhatsApp number" value={phone} onChangeText={setPhone} placeholder="919800000000" keyboardType="phone-pad"
                       hint="With the country code. WhatsApp shows soloyolo as a linked device, like WhatsApp Web." />
          ) : null}
        </OnboardingStep>
        {read && (unread || read.state !== 'idle') ? (
          <SectionCard title="Find your promises">
            <Stack pad="lg" gap="md">
              {read.state === 'reading' ? (
                <Loader label={read.total ? `Reading chat ${Math.min(read.done + 1, read.total)} of ${read.total}...` : 'Looking for chats with new messages...'} />
              ) : (
                <>
                  {read.state === 'done' ? (
                    <Text variant="bodyStrong">{read.done ? `Read ${plural(read.done, 'chat')}. ${read.new ? `${plural(read.new, 'new promise')} found.` : 'Nothing new in them.'}` : 'Nothing new to read.'}</Text>
                  ) : null}
                  {read.state === 'error' ? <View style={{ marginHorizontal: -t.space.lg }}><InlineError title="Your chats weren’t read." body={read.message ?? 'Try again.'} /></View> : null}
                  {unread ? (
                    <>
                      <Text variant="body" tone="secondary">
                        {`${plural(unread, 'chat has', 'chats have')} messages soloyolo hasn’t read${read.state === 'done' ? ' yet. It reads 15 at a time' : ''}. Claude reads best, and that sends the text of those chats to Claude through your Claude login. Reading on this Mac sends nothing and misses more.`}
                      </Text>
                      {setup?.claude ? null : <Text variant="small" tone="tertiary">Claude Code isn’t installed on this Mac. Install it and log in to read with Claude.</Text>}
                      <Row gap="sm" wrap>
                        <Button label="Read with Claude" variant="primary" disabled={!setup?.claude || asking} onPress={() => act('read', { extractor: 'claude-code' })} />
                        <Button label="Read on Mac" disabled={asking} onPress={() => act('read', { extractor: 'heuristic' })} />
                      </Row>
                    </>
                  ) : null}
                </>
              )}
            </Stack>
          </SectionCard>
        ) : null}
        <OnboardingStep n={2} icon="paper-plane-outline" title="Morning message on Telegram" state={state(1)} action={check}
                        body="Each morning at 07:30 you get the one to three things that matter today, with Done and Not needed under each."
                        how="python -m spike telegram pair" doneNote="Morning message at 07:30" />
        <OnboardingStep n={3} icon="cloud-upload-outline" title="Import your other chats" state={state(2)} action={files.length ? undefined : check}
                        body={files.length ? 'These exports are in Downloads on your Mac. Pick one to read it.'
                          : 'LinkedIn, Instagram and X come from their data exports. Request one, save it to Downloads on your Mac, and it shows up here.'}
                        how={setup ? undefined : 'python -m spike import-linkedin <folder>'} doneNote={exports.map((n) => NETWORK_NAMES[n]).join(', ')} />
        {tg && preview !== 'new' ? (
          <SectionCard title="Telegram chats">
            <Stack pad="lg" gap="md">
              {tg.linked || tg.state === 'linked' ? <Text variant="bodyStrong">Linked. Your Telegram chats are coming in.</Text>
                : !tg.ready ? (
                  <Text variant="body" tone="secondary">Reading your Telegram chats needs your own api_id and api_hash from my.telegram.org. docs/TELEGRAM.md has the steps.</Text>
                ) : tg.state === 'starting' ? <Loader label="Asking Telegram for a code..." />
                : tgAsks ? (
                  <>
                    <TextField label={tg.state === 'password' ? 'Two-step password' : 'Code from Telegram'} value={tgCode} onChangeText={setTgCode}
                               keyboardType={tg.state === 'password' ? 'default' : 'number-pad'} secureTextEntry={tg.state === 'password'} autoComplete="off"
                               error={tg.message ?? undefined}
                               hint={tg.state === 'password' ? (tg.hint ? `Your hint: ${tg.hint}` : 'The one you set in Telegram.') : 'Telegram sent it to your Telegram app.'} />
                    <Button label="Link" variant="primary" loading={tg.state === 'checking'} disabled={!tgCode.trim()}
                            onPress={async () => { await act('telegram-code', { code: tgCode }); setTgCode('') }} />
                  </>
                ) : (
                  <>
                    {tg.state === 'error' && tg.message ? <View style={{ marginHorizontal: -t.space.lg }}><InlineError title="Telegram didn’t link." body={tg.message} /></View> : null}
                    <Text variant="body" tone="secondary">soloyolo reads your one-to-one Telegram chats too. It never sends or marks anything read.</Text>
                    <TextField label="Your Telegram number" value={tgPhone} onChangeText={setTgPhone} placeholder="919800000000" keyboardType="phone-pad" hint="With the country code." />
                    <Button label="Get code" variant="primary" loading={asking} disabled={tgPhone.replace(/\D/g, '').length < 8} onPress={() => act('telegram', { phone: tgPhone })} />
                  </>
                )}
            </Stack>
          </SectionCard>
        ) : null}
        {extension && preview !== 'new' ? (
          <SectionCard title="Browser extension">
            {heard ? (
              <NavList rows={(['linkedin', 'instagram', 'x'] as const).map((n) => {
                const x = extension.networks[n]
                return {
                  key: n, lead: <NetworkIcon network={n} size="lg" />, label: NETWORK_NAMES[n],
                  description: !x?.enabled ? 'Off. Switch it on in the extension’s options.'
                    : x.error ? `Stopped: ${x.error}` : x.ok ? `Synced ${formatRelative(x.ok)}${x.summary ? `. ${x.summary}` : ''}` : 'Waiting for its first sync',
                  value: !x?.enabled ? 'Off' : x.error ? 'Stopped' : x.ok ? 'On' : undefined,
                }
              })} />
            ) : (
              <Stack pad="lg" gap="md">
                <Text variant="body" tone="secondary">
                  The soloyolo extension for Chrome keeps LinkedIn, and if you switch them on Instagram and X, in sync using the session already open in your browser. It only reads.
                </Text>
                {token ? (
                  <>
                    <View style={{ backgroundColor: t.color.surfaceRaised, borderRadius: t.radius.md, paddingHorizontal: t.space.md, paddingVertical: t.space.sm + 2, gap: 2 }}>
                      <Text variant="label" tone="tertiary" upper>Pairing token</Text>
                      <Text variant="small" selectable style={{ fontWeight: '600' }}>{token}</Text>
                    </View>
                    <Text variant="small" tone="tertiary">In Chrome, load the extension folder from chrome://extensions, paste this token in its options, then Save and Sync now. This card updates after the first sync.</Text>
                    <Button label="Check again" onPress={refresh} />
                  </>
                ) : (
                  <Button label="Show token" variant="primary" disabled={asking} onPress={async () => {
                    try { setToken(await liveToken()) } catch { toast.show('Couldn’t reach soloyolo on your Mac. Check it’s running, then try again.') }
                  }} />
                )}
              </Stack>
            )}
          </SectionCard>
        ) : null}
        {files.length ? (
          <SectionCard title="Exports in Downloads">
            <NavList rows={files.map((f) => ({
              key: f.file, lead: <NetworkIcon network={f.network} size="lg" />, label: `${NETWORK_NAMES[f.network] ?? f.network} export`,
              description: f.job?.state === 'done' ? f.job.summary ?? 'Read' : f.job?.state === 'error' ? 'Couldn’t be read. Tap to see why.' : `Saved ${formatRelative(f.modified)}`,
              value: f.job?.state === 'done' ? 'Read' : f.job && f.job.state !== 'error' ? 'Reading' : undefined,
              onPress: async () => {
                if (!f.job || f.job.state === 'error') await act('import', { file: f.file })
                router.push({ pathname: '/import', params: { file: f.file } })
              },
            }))} />
          </SectionCard>
        ) : null}
      </Screen.Body>
      <Screen.Footer>
        <Button label={done[0] ? 'Go to Today' : 'Skip for now'} variant={done[0] ? 'primary' : 'ghost'} onPress={() => router.replace('/')} />
      </Screen.Footer>
    </Screen>
  )
}
