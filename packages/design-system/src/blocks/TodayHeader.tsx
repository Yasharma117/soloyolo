import { View } from 'react-native'
import { DotGrid } from '../components/DotGrid/DotGrid'
import { Row } from '../components/Stack/Stack'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

const WORDS = ['nothing', 'one thing', 'two things', 'three things']

function greeting(d: Date) {
  const h = d.getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

/** The top of Today (Atoms): the date as a small label, then a serif greeting that says how much is owed. */
export function TodayHeader({ count, now = new Date() }: { count: number | null; now?: Date }) {
  const t = useTheme()
  const what = count === null ? '…' : WORDS[count] ?? `${count} things`
  const date = now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
  return (
    <View>
      <DotGrid />
      <View style={{ paddingHorizontal: t.space.xl, paddingTop: t.space.xl, marginBottom: t.space.xl + 2, gap: t.space.md }}>
        <Row gap="sm">
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: t.color.accent }} />
          <Text variant="label" tone="secondary">{date}</Text>
        </Row>
        <Text variant="headline">
          {greeting(now)},{'\n'}
          {count === null
            ? <Text variant="headline" tone="tertiary">reading your promises...</Text>
            : <Text variant="headline" tone="tertiary">you have <Text variant="headline">{what}</Text> {count ? 'to do today.' : 'owed today.'}</Text>}
        </Text>
      </View>
    </View>
  )
}
