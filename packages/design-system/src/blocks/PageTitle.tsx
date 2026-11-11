import type { ReactNode } from 'react'
import { View } from 'react-native'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

/** A screen's title and one plain line saying what it's for. */
export function PageTitle({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  const t = useTheme()
  return (
    <View style={{ paddingHorizontal: t.space.xl, paddingTop: t.space.md, paddingBottom: t.space.xs, gap: t.space.xs }}>
      <Text variant="title">{title}</Text>
      {subtitle ? <Text variant="body" tone="secondary">{subtitle}</Text> : null}
      {children}
    </View>
  )
}
