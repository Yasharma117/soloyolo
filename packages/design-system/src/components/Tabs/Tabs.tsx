import { Pressable, StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

/** Underline tabs for switching views inside a screen. */
export function Tabs<K extends string>({ items, value, onChange }: { items: { key: K; label: string }[]; value: K; onChange: (k: K) => void }) {
  const t = useTheme()
  return (
    <View style={{ flexDirection: 'row', gap: t.space.xl + 2, paddingHorizontal: t.space.xl, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: t.color.border }}>
      {items.map((it) => {
        const on = it.key === value
        return (
          <Pressable key={it.key} accessibilityRole="tab" accessibilityState={{ selected: on }} onPress={() => onChange(it.key)}
                     style={{ paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: on ? t.color.accent : 'transparent', marginBottom: -StyleSheet.hairlineWidth }}>
            <Text variant="body" tone={on ? 'primary' : 'tertiary'} style={{ fontWeight: on ? '600' : '500' }}>{it.label}</Text>
          </Pressable>
        )
      })}
    </View>
  )
}
