import { View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

/** A short reason or status. `hot` is for what's urgent: a date, someone chasing. */
export function Chip({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'hot' }) {
  const t = useTheme()
  const hot = tone === 'hot'
  return (
    <View style={{ paddingHorizontal: 9, paddingVertical: 4, borderRadius: t.radius.pill, backgroundColor: hot ? t.color.accentSoft : t.color.surfaceRaised }}>
      <Text variant="caption" tone={hot ? 'accent' : 'secondary'} style={hot ? { fontWeight: '600' } : undefined}>{label}</Text>
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
