// First run: the three things that make soloyolo work, in order. Each is done on your Mac, so this screen only
// shows where you are (from /api/status) and what to run next. ?state=new previews it with nothing set up.
import { Button, OnboardingStep, Screen, StepHeader, Text, formatCount, useTheme, type StepState } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { refresh, useData } from '../lib/api'
import { NETWORK_NAMES, type Status } from '../lib/types'

export default function Welcome() {
  const t = useTheme()
  const router = useRouter()
  const { state: preview } = useLocalSearchParams<{ state?: 'new' }>()
  const live = useData<Status>('/api/status').data
  const s = preview === 'new' ? { networks: [], telegram: false } : live
  const has = Object.fromEntries((s?.networks ?? []).map((n) => [n.network, n]))
  const exports = ['linkedin', 'instagram', 'x'].filter((n) => has[n])
  const done = [!!has.whatsapp, !!s?.telegram, exports.length > 0]
  const at = done.indexOf(false) // the first one not done is the one you're on
  const state = (i: number): StepState => (done[i] ? 'done' : i === at ? 'now' : 'later')
  const check = { label: 'Check again', onPress: refresh }
  const leave = () => router.replace('/')
  return (
    <Screen>
      <Screen.Header title="Set up soloyolo" subtitle="Three steps, each done on your Mac. This screen updates as they finish." onBack={router.canGoBack() ? router.back : undefined}>
        <StepHeader step={done.filter(Boolean).length} total={3} label={at < 0 ? 'All set' : undefined} />
      </Screen.Header>
      <Screen.Body>
        <OnboardingStep n={1} icon="logo-whatsapp" title="Link WhatsApp" state={state(0)} action={check}
                        body="soloyolo reads your chats to find what you said you’d do, and what people said they’d do for you."
                        how="connectord link --phone 91…" doneNote={has.whatsapp ? `${formatCount(has.whatsapp.messages)} messages read` : undefined} />
        <OnboardingStep n={2} icon="paper-plane-outline" title="Pair Telegram" state={state(1)} action={check}
                        body="Each morning at 07:30 you get the one to three things that matter today, with Done and Not needed under each."
                        how="python -m spike telegram pair" doneNote="Morning message at 07:30" />
        <OnboardingStep n={3} icon="cloud-upload-outline" title="Import your other chats" state={state(2)} action={check}
                        body="LinkedIn, Instagram and X come from their data exports. You can skip this and add them later from Sources."
                        how="python -m spike import-linkedin <folder>" doneNote={exports.map((n) => NETWORK_NAMES[n]).join(', ')} />
        {at === 2 ? <Text variant="small" tone="tertiary" style={{ paddingHorizontal: t.space.xl }}>The last step is optional.</Text> : null}
      </Screen.Body>
      <Screen.Footer>
        <Button label={done[0] ? 'Go to Today' : 'Skip for now'} variant={done[0] ? 'primary' : 'ghost'} onPress={leave} />
      </Screen.Footer>
    </Screen>
  )
}
