import { LinearGradient } from 'expo-linear-gradient'
import { View } from 'react-native'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import type { PromiseItem } from './types'

const lower = (s: string) => (s.length > 1 && s[1] === s[1]!.toLowerCase() ? s[0]!.toLowerCase() + s.slice(1) : s)

function Orb({ n }: { n: number }) {
  const t = useTheme()
  return (
    <View style={{ width: 20, height: 20, borderRadius: 10, overflow: 'hidden', alignItems: 'center', justifyContent: 'center', marginRight: 5 }}>
      <LinearGradient colors={[t.color.warmFrom, t.color.warmTo]} style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} />
      <Text variant="caption" style={{ color: t.color.onWarm, fontWeight: '700', fontSize: 10 }}>{`0${n}`}</Text>
    </View>
  )
}

/** One numbered part: the orb, the words, and the gradient line under them. */
function Part({ n, words, after }: { n: number; words: string; after?: string }) {
  const t = useTheme()
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', maxWidth: '100%' }}>
      <Orb n={n} />
      <View style={{ flexShrink: 1 }}>
        {/* punctuation sits inside the words, so a wrap never strands or floats a comma */}
        <Text variant="sentence">{words}{after ? <Text variant="sentence" tone="tertiary">{after}</Text> : null}</Text>
        <LinearGradient colors={[t.color.underlineFrom, t.color.underlineTo]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }}
                        style={{ height: 1.5, marginTop: -3, borderRadius: 1 }} />
      </View>
    </View>
  )
}

const Gap = ({ words }: { words: string }) => <Text variant="sentence" tone="tertiary">{words}</Text>

/**
 * A promise taken apart, as the Atoms redesign sets "I will (1) meditate for 5 mins, (2) when I wake up, so that I can
 * become (3) a mindful person": the connecting words quiet, the parts numbered and underlined. 01 is what, 02 when,
 * 03 who, so a missing date reads as a gap you can see.
 */
export function PromiseParts({ item }: { item: PromiseItem }) {
  const t = useTheme()
  const first = item.name.split(' ')[0]!
  const action = lower(item.action)
  const by = <Part n={2} words={item.due ? `by ${item.due}` : 'no date said'} />
  const who = <Part n={3} words={first} />
  // "send Rohan the scan ... for Rohan" says it twice: when the action names them, 03 is already in 01
  const named = action.toLowerCase().includes(first.toLowerCase())
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: 6, rowGap: t.space.sm }}>
      {item.owner === 'me'
        ? item.kind === 'ask'
          ? <>{who}<Gap words="asked you to" /><Part n={1} words={action} after="," />{by}</>
          : <><Gap words="You said you’d" /><Part n={1} words={action} after="," />{by}{named ? null : <><Gap words="for" />{who}</>}</>
        : <><Gap words={item.kind === 'ask' ? 'You asked' : 'Waiting on'} />{who}<Gap words="to" /><Part n={1} words={action} after="," />{by}</>}
    </View>
  )
}
