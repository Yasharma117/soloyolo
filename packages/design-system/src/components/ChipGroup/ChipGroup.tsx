import { Pressable, ScrollView, StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

export type ChipOption<T extends string> = { value: T; label: string; count?: number; disabled?: boolean }

/**
 * Pick one of a few. The chosen chip is filled, the rest outlined (from Markon's chip-group). `scroll` keeps it to
 * one line that slides sideways, for filters above a list; without it the chips wrap.
 */
export function ChipGroup<T extends string>({ options, value, onChange, scroll, label }: {
  options: ChipOption<T>[]; value: T; onChange: (v: T) => void; scroll?: boolean; label: string
}) {
  const t = useTheme()
  const chips = options.map((o) => {
    const on = o.value === value
    return (
      <Pressable key={o.value} accessibilityRole="radio" accessibilityState={{ selected: on, disabled: o.disabled }} disabled={o.disabled}
                 onPress={() => onChange(o.value)} hitSlop={4}
                 style={({ pressed }) => ({
                   flexDirection: 'row', alignItems: 'center', gap: 6, height: 34, paddingHorizontal: t.space.md + 2, borderRadius: t.radius.pill,
                   backgroundColor: on ? t.color.inverse : t.color.surface, borderWidth: on ? 0 : StyleSheet.hairlineWidth, borderColor: t.color.border,
                   opacity: o.disabled ? 0.4 : pressed ? 0.8 : 1,
                 })}>
        <Text variant="small" tone={on ? 'inverse' : 'primary'} style={{ fontWeight: '600' }}>{o.label}</Text>
        {o.count != null ? <Text variant="caption" tone={on ? 'inverse' : 'tertiary'} style={{ opacity: on ? 0.7 : 1 }}>{o.count}</Text> : null}
      </Pressable>
    )
  })
  return scroll ? (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} accessibilityRole="radiogroup" accessibilityLabel={label}
                contentContainerStyle={{ gap: t.space.sm, paddingHorizontal: t.space.xl }}>{chips}</ScrollView>
  ) : (
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: t.space.sm }}>{chips}</View>
  )
}
