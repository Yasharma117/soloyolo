import type { ReactNode } from 'react'
import { StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

/** A number with its label above and a hint below (from Markon's stat-tile). `plain` drops the card, for use inside one. */
export function StatTile({ label, value, hint, tone = 'primary', plain }: {
  label: string; value: string; hint?: string; tone?: 'primary' | 'accent' | 'success' | 'danger'; plain?: boolean
}) {
  const t = useTheme()
  return (
    <View style={[{ flex: 1, minWidth: 0, gap: 2 },
                  !plain && { backgroundColor: t.color.surface, borderRadius: t.radius.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border,
                              paddingHorizontal: t.space.md, paddingVertical: t.space.sm + 2 }]}>
      <Text variant="caption" tone="tertiary" numberOfLines={1}>{label}</Text>
      <Text variant="heading" tone={tone === 'accent' ? 'accent' : tone} numberOfLines={1} style={{ fontSize: 20, lineHeight: 26 }}>{value}</Text>
      {hint ? <Text variant="caption" tone="tertiary" numberOfLines={1}>{hint}</Text> : null}
    </View>
  )
}

/** Tiles of equal width in one row. Three at most on a phone. */
export function StatRow({ children }: { children: ReactNode }) {
  const t = useTheme()
  return <View style={{ flexDirection: 'row', gap: t.space.sm, paddingHorizontal: t.space.lg }}>{children}</View>
}
