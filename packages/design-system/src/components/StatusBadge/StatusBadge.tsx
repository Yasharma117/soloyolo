import { View } from 'react-native'
import { useTheme } from '../../theme'
import type { ColorTokens } from '../../tokens'
import { Text } from '../Text/Text'

/**
 * The one place a promise's state gets its words and its colour (from Markon's status-badge: "single source of
 * truth for every status label; do not define local maps in pages"). Add a state here, never in a screen.
 */
export const STATUS = {
  today: { label: 'On today', color: 'accent' },
  quiet: { label: 'Quiet', color: 'textTertiary' },
  later: { label: 'Later', color: 'later' },
  done: { label: 'Done', color: 'success' },
  'not needed': { label: 'Not needed', color: 'neutralAction' },
  settled: { label: 'Looks settled', color: 'info' },
} as const satisfies Record<string, { label: string; color: keyof ColorTokens }>

export type Status = keyof typeof STATUS

/** Where an item stands, from the fields every item carries. Your own marks win, then a suggestion, then the nudge. */
export function statusOf(i: { dismissed?: boolean; snoozed?: boolean; status?: string; live?: boolean; suggestion?: string | null }): Status {
  if (i.dismissed) return 'not needed'
  if (i.snoozed) return 'later'
  if (i.status === 'done') return 'done'
  if (i.suggestion) return 'settled'
  return i.live ? 'today' : 'quiet'
}

/** A dot and the state's word, small enough for a list caption. */
export function StatusBadge({ status }: { status: Status }) {
  const t = useTheme()
  const s = STATUS[status]
  return (
    <View accessibilityLabel={s.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: t.color[s.color] }} />
      <Text variant="caption" style={{ color: t.color[s.color], fontWeight: '600' }}>{s.label}</Text>
    </View>
  )
}
