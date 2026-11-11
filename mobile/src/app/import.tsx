// An export being read. With ?file= it follows the real job in /api/setup (spike/setup.py), which knows the stage
// it's at and what it found, not a percentage; the bar moves a stage at a time. Without it, ?at=start|half|end
// shows sample numbers for review.
import { Button, ImportProgress, InlineError, Loader, Screen, Text, useTheme, type ImportStage, type StepState } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect } from 'react'
import { refresh, setupAct, useData } from '../lib/api'
import { NETWORK_NAMES, type ImportJob, type SetupStatus } from '../lib/types'

type At = 'start' | 'half' | 'end'
type Show = { headline: string; detail?: string; progress: number; stages: ImportStage[]; skipped?: string }
const SKIPPED = '46 messages skipped. Sponsored messages and group threads aren’t read.'
const SHOW: Record<At, Show> = {
  start: { headline: 'Reading your LinkedIn export...', detail: '40 of 780 messages', progress: 0.05, skipped: SKIPPED,
           stages: [{ label: 'Reading messages', state: 'now', value: '40' }, { label: 'Matching people', state: 'later' }, { label: 'Finding promises', state: 'later' }] },
  half: { headline: 'Found 2 promises so far', detail: '780 messages from 64 people', progress: 0.6, skipped: SKIPPED,
          stages: [{ label: 'Reading messages', state: 'done', value: '780' }, { label: 'Matching people', state: 'done', value: '64' }, { label: 'Finding promises', state: 'now', value: '2' }] },
  end: { headline: 'Found 4 promises', detail: '780 messages from 64 people', progress: 1, skipped: SKIPPED,
         stages: [{ label: 'Reading messages', state: 'done', value: '780' }, { label: 'Matching people', state: 'done', value: '64' }, { label: 'Finding promises', state: 'done', value: '4' }] },
}

// The job has two stages. Promises are found later, by the reading pass, so this screen doesn't claim them.
function fromJob(job: ImportJob): Show {
  const name = NETWORK_NAMES[job.network] ?? job.network
  const saved = job.state === 'done'
  const stage = (after: ImportJob['state'][], now: ImportJob['state']): StepState => (after.includes(job.state) ? 'done' : job.state === now ? 'now' : 'later')
  return {
    headline: saved ? `${name} export read` : job.state === 'saving' ? 'Saving what’s new...' : `Reading your ${name} export...`,
    detail: saved ? job.summary ?? undefined : job.found ? `Found ${job.found}` : undefined,
    progress: saved ? 1 : job.state === 'saving' ? 0.6 : 0.15,
    stages: [{ label: 'Reading the export', state: stage(['saving', 'done'], 'reading'), value: job.found ?? undefined },
             { label: 'Saving what’s new', state: stage(['done'], 'saving') }],
    skipped: saved ? 'Promises show up on Today once soloyolo has read these chats.' : undefined,
  }
}

export default function Import() {
  const t = useTheme()
  const router = useRouter()
  const { at = 'half', file } = useLocalSearchParams<{ at?: At; file?: string }>()
  const setup = useData<SetupStatus>('/api/setup')
  const job = file ? setup.data?.exports.find((f) => f.file === file)?.job ?? null : null
  const running = !!file && (!job || job.state === 'reading' || job.state === 'saving') && !setup.error
  useEffect(() => {
    if (!running) return
    const id = setInterval(refresh, 1500)
    return () => clearInterval(id)
  }, [running])
  const back = () => (router.canGoBack() ? router.back() : router.replace('/sources'))
  const show = file ? (job && job.state !== 'error' ? fromJob(job) : null) : SHOW[at] ?? SHOW.half
  const finished = file ? job?.state === 'done' : at === 'end'
  return (
    <Screen>
      <Screen.Header title={`${NETWORK_NAMES[job?.network ?? 'linkedin']} import`} onBack={back} />
      <Screen.Body>
        {show ? <ImportProgress network={job?.network ?? 'linkedin'} {...show} /> : null}
        {file && job?.state === 'error' ? <InlineError title="We couldn’t read this export." body={`${job.error} Download the export again, then try once more.`}
                                                       onRetry={() => setupAct('import', { file }).catch(() => {})} /> : null}
        {file && setup.error ? <InlineError title="We couldn’t check the import." body="soloyolo on your Mac didn’t answer. Check it’s running, then try again." onRetry={refresh} /> : null}
        {file && !job && !setup.error ? <Loader label="Starting..." /> : null}
        {show && !finished ? <Text variant="small" tone="tertiary" align="center" style={{ paddingHorizontal: t.space.xl }}>You can leave this screen. The import keeps going on your Mac.</Text> : null}
      </Screen.Body>
      <Screen.Footer>
        {finished ? <Button label="Go to Today" variant="primary" onPress={() => router.replace('/')} /> : <Button label="Close" variant="ghost" onPress={back} />}
      </Screen.Footer>
    </Screen>
  )
}
