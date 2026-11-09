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

/** The top of Today: the date, and a greeting that says how much is owed. */
export function TodayHeader({ count, now = new Date() }: { count: number | null; now?: Date }) {
  const t = useTheme()
  const what = count === null ? '…' : WORDS[count] ?? `${count} things`
  return (
    <View>
      <DotGrid />
      <Row padX="xl" style={{ paddingTop: t.space.lg + 2 }}>
        <Text variant="display">{now.getDate()}</Text>
        <View style={{ width: 14, height: 14, borderRadius: 7, marginLeft: 10, marginTop: 6, backgroundColor: t.color.accent }} />
        <View style={{ flex: 1 }} />
        <View style={{ alignItems: 'flex-end' }}>
          <Text variant="bodyStrong" tone="secondary">{now.toLocaleDateString(undefined, { weekday: 'long' })}</Text>
          <Text variant="body" tone="tertiary">{now.toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}</Text>
        </View>
      </Row>
      <View style={{ paddingHorizontal: t.space.xl, marginBottom: t.space.xl + 2 }}>
        <Text variant="heading">{greeting(now)},</Text>
        {count === null
          ? <Text variant="heading" tone="tertiary">reading your promises...</Text>
          : <Text variant="heading" tone="tertiary">you have <Text variant="heading">{what}</Text> {count ? 'to do today.' : 'owed today.'}</Text>}
      </View>
    </View>
  )
}
