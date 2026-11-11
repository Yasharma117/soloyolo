import { Pressable, StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'
import { Icon } from '../Icon/Icon'
import { Text } from '../Text/Text'

export type Option<T extends string> = {
  value: T
  label: string
  /** Under the label: what picking it means. */
  description?: string
  /** On the right: a date, a count. */
  trailing?: string
  disabled?: boolean
  /** soloyolo's pick, with why underneath. At most one per list. */
  suggested?: string
}

/**
 * One choice from a short list, one per line inside one card, a radio on the left (from Markon's
 * option-radio-group). Use it when the options need a word of explanation; when they don't, use ChipGroup.
 */
export function OptionList<T extends string>({ options, value, onChange, label }: {
  options: Option<T>[]; value: T; onChange: (v: T) => void; label: string
}) {
  const t = useTheme()
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label}
          style={{ backgroundColor: t.color.surface, borderRadius: t.radius.xl, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border, overflow: 'hidden' }}>
      {options.map((o, i) => {
        const on = o.value === value
        return (
          <Pressable key={o.value} accessibilityRole="radio" accessibilityState={{ checked: on, disabled: o.disabled }} disabled={o.disabled}
                     onPress={() => onChange(o.value)}
                     style={({ pressed }) => ({
                       flexDirection: 'row', alignItems: 'flex-start', gap: t.space.md, paddingHorizontal: t.space.lg, paddingVertical: t.space.md,
                       backgroundColor: pressed ? t.color.surfaceRaised : 'transparent', opacity: o.disabled ? 0.45 : 1,
                       borderTopWidth: i ? StyleSheet.hairlineWidth : 0, borderTopColor: t.color.border,
                     })}>
            <View style={{ width: 20, height: 20, borderRadius: 10, marginTop: 1, alignItems: 'center', justifyContent: 'center',
                           backgroundColor: on ? t.color.inverse : 'transparent', borderWidth: on ? 0 : 1.5, borderColor: t.color.border }}>
              {on ? <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: t.color.onInverse }} /> : null}
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Text variant="bodyStrong" style={{ flexShrink: 1 }}>{o.label}</Text>
                {o.suggested ? <Icon name="sparkles" size="xs" tone="accent" /> : null}
              </View>
              {o.description ? <Text variant="small" tone="tertiary">{o.description}</Text> : null}
              {o.suggested ? <Text variant="small" tone="accent">{o.suggested}</Text> : null}
            </View>
            {o.trailing ? <Text variant="small" tone="tertiary">{o.trailing}</Text> : null}
          </Pressable>
        )
      })}
    </View>
  )
}
