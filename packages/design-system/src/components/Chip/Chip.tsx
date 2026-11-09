import { View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

export type ChipTone = 'neutral' | 'hot' | 'success' | 'danger' | 'info'

const FILL = { neutral: 'surfaceRaised', hot: 'accentSoft', success: 'successSoft', danger: 'dangerSoft', info: 'infoSoft' } as const
const INK = { neutral: 'secondary', hot: 'accent', success: 'success', danger: 'danger', info: 'info' } as const

/** A short reason or status, at most two words for a status ("Synced", "On hold").
 *  hot: urgent (a date, someone chasing). success / danger / info: the state of a source or import. */
export function Chip({ label, tone = 'neutral' }: { label: string; tone?: ChipTone }) {
  const t = useTheme()
  return (
    <View style={{ alignSelf: 'flex-start', paddingHorizontal: 9, paddingVertical: 4, borderRadius: t.radius.pill, backgroundColor: t.color[FILL[tone]] }}>
      <Text variant="caption" tone={INK[tone]} style={tone !== 'neutral' ? { fontWeight: '600' } : undefined}>{label}</Text>
    </View>
  )
}

const HOT = /^(due|overdue)|again|chased/i
/** Reasons an item is showing, urgent ones marked. */
export function ReasonChips({ reasons, max = 3 }: { reasons?: string[]; max?: number }) {
  const t = useTheme()
  if (!reasons?.length) return null
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: t.space.xs + 2 }}>
      {reasons.slice(0, max).map((r) => <Chip key={r} label={r} tone={HOT.test(r) ? 'hot' : 'neutral'} />)}
    </View>
  )
}
