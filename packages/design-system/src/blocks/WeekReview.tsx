import { LinearGradient } from 'expo-linear-gradient'
import { StyleSheet, View } from 'react-native'
import { SplitBar } from '../components/SplitBar/SplitBar'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']
const word = (n: number) => WORDS[n] ?? String(n)
const cap = (s: string) => s[0]!.toUpperCase() + s.slice(1)

/** The week in a sentence: "You closed five things. Two went quiet." Numbers as words, as in the greeting. */
export function weekSentence(closed: number, quiet: number): string {
  const first = closed ? `You closed ${word(closed)} ${closed === 1 ? 'thing' : 'things'}.` : 'Nothing closed this week.'
  return quiet ? `${first} ${cap(word(quiet))} went quiet.` : first
}

/**
 * Sunday's review, at the top of the week screen: the dates, the week as one serif sentence, and the split behind
 * it. Closed counts what you marked done and what settled without you. It reads like a friend's recap, not a
 * score: no streaks, no goals (after How We Feel and Gentler Streak).
 */
export function WeekReview({ range, done, settled, quiet }: { /** "3 to 9 November" */ range: string; done: number; settled: number; quiet: number }) {
  const t = useTheme()
  return (
    <View style={{ marginHorizontal: t.space.lg, borderRadius: t.radius.card + 2, overflow: 'hidden', borderWidth: 1, borderColor: t.color.surface,
                   shadowColor: t.color.shadow, ...t.shadow.card }}>
      <LinearGradient colors={[t.color.cardWarmFrom, t.color.cardWarmTo]} start={{ x: 0.9, y: 0.1 }} end={{ x: 0.1, y: 0.9 }} style={StyleSheet.absoluteFill} />
      <View style={{ padding: t.space.lg, gap: t.space.lg }}>
        <View style={{ gap: t.space.sm }}>
          <Text variant="label" tone="tertiary" upper>{range}</Text>
          <Text variant="headline" accessibilityRole="header">{weekSentence(done + settled, quiet)}</Text>
        </View>
        <SplitBar parts={[{ label: 'Done by you', value: done, color: 'series1' }, { label: 'Settled without you', value: settled, color: 'series2' },
                          { label: 'Went quiet', value: quiet, color: 'series3' }]} />
      </View>
    </View>
  )
}
