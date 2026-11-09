// Result screens, one route, the state in ?tone= (as Markon drives state variants by search param).
import { StatusScreen, type StatusTone } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'

const COPY: Record<StatusTone, { title: string; body: string; primary?: string }> = {
  success: { title: 'Chats imported', body: 'We read 312 LinkedIn messages and found 4 promises. They’re on Today when they matter.', primary: 'Go to Today' },
  error: { title: 'Import failed', body: 'We couldn’t read this file. Export it again as JSON, then try once more.', primary: 'Try again' },
  pending: { title: 'Reading your chats', body: 'This takes a minute or two. You can leave this screen.' },
  info: { title: 'Telegram not paired', body: 'Pair it to get Today’s items every morning at 07:30.', primary: 'Pair Telegram' },
}

export default function Status() {
  const router = useRouter()
  const { tone = 'success' } = useLocalSearchParams<{ tone?: StatusTone }>()
  const c = COPY[tone] ?? COPY.success
  const back = () => (router.canGoBack() ? router.back() : router.replace('/'))
  return <StatusScreen tone={tone} title={c.title} body={c.body} primary={c.primary ? { label: c.primary, onPress: back } : undefined} secondary={{ label: 'Close', onPress: back }} />
}
