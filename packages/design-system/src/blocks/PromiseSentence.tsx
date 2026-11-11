import type { TextStyle } from 'react-native'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import type { PromiseItem } from './types'

const lower = (s: string) => (s.length > 1 && s[1] === s[1]!.toLowerCase() ? s[0]!.toLowerCase() + s.slice(1) : s)

/** The core of the product: who owes what, said as a sentence, the owed part underlined. */
export function promiseLead(item: Pick<PromiseItem, 'name' | 'owner' | 'kind'>): string {
  const first = item.name.split(' ')[0]!
  if (item.owner === 'me') return item.kind === 'ask' ? `${first} asked you to ` : 'You said you’d '
  return item.kind === 'ask' ? `You asked ${first} to ` : `Waiting on ${first} to `
}

export function PromiseSentence({ item, size = 'large', struck, style }: { item: PromiseItem; size?: 'large' | 'small'; struck?: boolean; style?: TextStyle }) {
  const t = useTheme()
  return (
    <Text variant={size === 'large' ? 'sentence' : 'sentenceSmall'} tone={struck ? 'tertiary' : 'primary'}
          style={[struck && { textDecorationLine: 'line-through' }, style]}>
      <Text variant={size === 'large' ? 'sentence' : 'sentenceSmall'} tone={struck ? 'tertiary' : 'secondary'}>{promiseLead(item)}</Text>
      <Text variant={size === 'large' ? 'sentence' : 'sentenceSmall'} tone={struck ? 'tertiary' : 'primary'}
            style={{ textDecorationLine: struck ? 'line-through' : 'underline', textDecorationColor: t.color.accent }}>{lower(item.action)}</Text>
    </Text>
  )
}
