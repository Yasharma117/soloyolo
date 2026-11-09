import type { ReactNode } from 'react'
import { Pressable, StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

export type ListRowProps = {
  lead?: ReactNode
  title?: ReactNode
  subtitle?: ReactNode
  trailing?: ReactNode
  children?: ReactNode
  onPress?: () => void
  highlighted?: boolean
  divider?: boolean
}

/** Every list is made of these: lead (an avatar or dot), the words, a trailing time or chevron. */
export function ListRow({ lead, title, subtitle, trailing, children, onPress, highlighted, divider = true }: ListRowProps) {
  const t = useTheme()
  return (
    <Pressable onPress={onPress} disabled={!onPress}
               style={({ pressed }) => ({
                 flexDirection: 'row', alignItems: 'flex-start', gap: t.space.md, paddingHorizontal: t.space.xl, paddingVertical: t.space.md + 2,
                 backgroundColor: highlighted ? t.color.accentSoft : pressed ? t.color.surfaceRaised : t.color.background,
                 borderBottomWidth: divider ? StyleSheet.hairlineWidth : 0, borderBottomColor: t.color.border,
               })}>
      {lead ? <View style={{ paddingTop: 1 }}>{lead}</View> : null}
      <View style={{ flex: 1, gap: 3 }}>
        {typeof title === 'string' ? <Text variant="bodyStrong" numberOfLines={1}>{title}</Text> : title}
        {typeof subtitle === 'string' ? <Text variant="small" tone="tertiary">{subtitle}</Text> : subtitle}
        {children}
      </View>
      {trailing}
    </Pressable>
  )
}
