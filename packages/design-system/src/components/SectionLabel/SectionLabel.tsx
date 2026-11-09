import type { ReactNode } from 'react'
import { View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

/** The small spaced uppercase label above a group of rows. */
export function SectionLabel({ children, trailing }: { children: string; trailing?: ReactNode }) {
  const t = useTheme()
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: t.space.xl, marginTop: t.space.xxl, marginBottom: t.space.md - 2 }}>
      <Text variant="label" tone="tertiary">{children}</Text>
      {trailing}
    </View>
  )
}
