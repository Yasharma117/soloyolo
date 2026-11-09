import { Pressable, StyleSheet, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Icon, type IconName } from '../components/Icon/Icon'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

export type TabItem = { key: string; label: string; icon: IconName; iconActive: IconName; dot?: boolean }

/** Mesh's floating pill: icons only, the current tab dark with its name. */
export function FloatingTabBar({ items, active, onSelect }: { items: TabItem[]; active: string; onSelect: (key: string) => void }) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  return (
    <View pointerEvents="box-none" style={{ position: 'absolute', left: 0, right: 0, alignItems: 'center', bottom: Math.max(insets.bottom, 12) + 4 }}>
      <View style={{ flexDirection: 'row', gap: 4, padding: 6, borderRadius: t.radius.pill, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border,
                     backgroundColor: t.color.surfaceFloating, shadowColor: t.color.shadow, ...t.shadow.floating }}>
        {items.map((it) => {
          const on = it.key === active
          return (
            <Pressable key={it.key} accessibilityRole="tab" accessibilityLabel={it.label} accessibilityState={{ selected: on }}
                       onPress={() => !on && onSelect(it.key)}
                       style={{ flexDirection: 'row', alignItems: 'center', gap: 6, height: 44, minWidth: 48, paddingHorizontal: 14,
                                borderRadius: t.radius.pill, justifyContent: 'center', backgroundColor: on ? t.color.inverse : 'transparent' }}>
              <Icon name={on ? it.iconActive : it.icon} size="lg" tone={on ? 'inverse' : 'secondary'} />
              {on ? <Text variant="small" tone="inverse" style={{ fontWeight: '600' }}>{it.label}</Text> : null}
              {it.dot && !on ? <View style={{ position: 'absolute', top: 9, right: 12, width: 7, height: 7, borderRadius: 4, backgroundColor: t.color.accent }} /> : null}
            </Pressable>
          )
        })}
      </View>
    </View>
  )
}
