import { TextInput, View } from 'react-native'
import { useTheme } from '../../theme'
import { Icon } from '../Icon/Icon'

export function SearchField({ value, onChangeText, placeholder = 'Search' }: { value: string; onChangeText: (s: string) => void; placeholder?: string }) {
  const t = useTheme()
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.space.sm, height: 40, borderRadius: t.radius.md + 2,
                   paddingHorizontal: t.space.md, backgroundColor: t.color.surfaceRaised }}>
      <Icon name="search" size="md" tone="tertiary" />
      <TextInput value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={t.color.textTertiary}
                 accessibilityLabel={placeholder} style={{ flex: 1, color: t.color.textPrimary, fontSize: 16, paddingVertical: 0 }} />
    </View>
  )
}
