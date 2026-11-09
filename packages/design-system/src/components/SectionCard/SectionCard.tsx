import type { ReactNode } from 'react'
import { Pressable, StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'
import { Icon, type IconName } from '../Icon/Icon'
import { Text } from '../Text/Text'

/** A titled group on the paper: settings, a person's details, an import summary. */
export function SectionCard({ title, action, children }: { title?: string; action?: { label: string; onPress: () => void }; children: ReactNode }) {
  const t = useTheme()
  return (
    <View style={{ marginHorizontal: t.space.lg, gap: t.space.sm }}>
      {title || action ? (
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: t.space.xs }}>
          {title ? <Text variant="label" tone="tertiary">{title}</Text> : <View />}
          {action ? <Pressable accessibilityRole="button" onPress={action.onPress} hitSlop={8}><Text variant="small" tone="accent" style={{ fontWeight: '600' }}>{action.label}</Text></Pressable> : null}
        </View>
      ) : null}
      <View style={{ backgroundColor: t.color.surface, borderRadius: t.radius.xl, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border, overflow: 'hidden' }}>
        {children}
      </View>
    </View>
  )
}

/** Label and value pairs inside a SectionCard: "Messages 5,602", "Last sync 4 min ago". */
export function KeyValueList({ items }: { items: { label: string; value: string; tone?: 'primary' | 'accent' | 'success' | 'danger' }[] }) {
  const t = useTheme()
  return (
    <View>
      {items.map((it, i) => (
        <View key={it.label} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: t.space.md, paddingHorizontal: t.space.lg, paddingVertical: t.space.md,
                                      borderTopWidth: i ? StyleSheet.hairlineWidth : 0, borderTopColor: t.color.border }}>
          <Text variant="body" tone="secondary">{it.label}</Text>
          <Text variant="bodyStrong" tone={it.tone ?? 'primary'} style={{ flexShrink: 1, textAlign: 'right' }}>{it.value}</Text>
        </View>
      ))}
    </View>
  )
}

/** A row that goes somewhere: icon, label, optional value, chevron. */
export function NavRow({ icon, label, value, onPress, first }: { icon?: IconName; label: string; value?: string; onPress?: () => void; first?: boolean }) {
  const t = useTheme()
  return (
    <Pressable accessibilityRole="button" onPress={onPress} disabled={!onPress}
               style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: t.space.md, paddingHorizontal: t.space.lg, paddingVertical: t.space.md + 1,
                                          backgroundColor: pressed ? t.color.surfaceRaised : 'transparent',
                                          borderTopWidth: first ? 0 : StyleSheet.hairlineWidth, borderTopColor: t.color.border })}>
      {icon ? <Icon name={icon} size="lg" tone="secondary" /> : null}
      <Text variant="body" style={{ flex: 1 }}>{label}</Text>
      {value ? <Text variant="body" tone="tertiary">{value}</Text> : null}
      {onPress ? <Icon name="chevron-forward" size="md" tone="tertiary" /> : null}
    </Pressable>
  )
}

export function NavList({ rows }: { rows: { icon?: IconName; label: string; value?: string; onPress?: () => void }[] }) {
  return <View>{rows.map((r, i) => <NavRow key={r.label} {...r} first={i === 0} />)}</View>
}
