// An export being read. soloyolo on your Mac doesn't report import progress yet, so this screen shows sample
// numbers at three points (?at=start|half|end) for review; the block is ready for the real counts.
import { Button, ImportProgress, Screen, Text, useTheme, type ImportStage } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'

type At = 'start' | 'half' | 'end'
const SHOW: Record<At, { headline: string; detail: string; progress: number; stages: ImportStage[] }> = {
  start: { headline: 'Reading your LinkedIn export...', detail: '40 of 780 messages', progress: 0.05,
           stages: [{ label: 'Reading messages', state: 'now', value: '40' }, { label: 'Matching people', state: 'later' }, { label: 'Finding promises', state: 'later' }] },
  half: { headline: 'Found 2 promises so far', detail: '780 messages from 64 people', progress: 0.6,
          stages: [{ label: 'Reading messages', state: 'done', value: '780' }, { label: 'Matching people', state: 'done', value: '64' }, { label: 'Finding promises', state: 'now', value: '2' }] },
  end: { headline: 'Found 4 promises', detail: '780 messages from 64 people', progress: 1,
         stages: [{ label: 'Reading messages', state: 'done', value: '780' }, { label: 'Matching people', state: 'done', value: '64' }, { label: 'Finding promises', state: 'done', value: '4' }] },
}

export default function Import() {
  const t = useTheme()
  const router = useRouter()
  const { at = 'half' } = useLocalSearchParams<{ at?: At }>()
  const show = SHOW[at] ?? SHOW.half
  const back = () => (router.canGoBack() ? router.back() : router.replace('/sources'))
  return (
    <Screen>
      <Screen.Header title="LinkedIn import" onBack={back} />
      <Screen.Body>
        <ImportProgress network="linkedin" {...show} skipped="46 messages skipped. Sponsored messages and group threads aren’t read." />
        {at !== 'end' ? <Text variant="small" tone="tertiary" align="center" style={{ paddingHorizontal: t.space.xl }}>You can leave this screen. The import keeps going on your Mac.</Text> : null}
      </Screen.Body>
      <Screen.Footer>
        {at === 'end' ? <Button label="Go to Today" variant="primary" onPress={() => router.replace('/')} /> : <Button label="Close" variant="ghost" onPress={back} />}
      </Screen.Footer>
    </Screen>
  )
}
