import { StyleSheet, View } from 'react-native'
import { Icon, type IconName } from '../components/Icon/Icon'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

/** A place soloyolo reads from, and whether it's working. */
export function SourceRow({ icon, name, state, tone, note, last }: { icon: IconName; name: string; state: string; tone: 'on' | 'off' | 'hold'; note: string; last?: boolean }) {
  const t = useTheme()
  const color = tone === 'on' ? t.color.successText : tone === 'hold' ? t.color.accentText : t.color.textTertiary
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', paddingLeft: 14, gap: t.space.md }}>
      <View style={{ marginTop: 12 }}><Icon name={icon} size="lg" tone="secondary" /></View>
      <View style={{ flex: 1, paddingVertical: 11, paddingRight: 14, borderBottomWidth: last ? 0 : StyleSheet.hairlineWidth, borderBottomColor: t.color.border }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: t.space.sm }}>
          <Text variant="subheading" style={{ fontWeight: '400' }}>{name}</Text>
          <Text variant="small" style={{ color, fontSize: 14 }}>{state}</Text>
        </View>
        <Text variant="small" tone="secondary" style={{ marginTop: 2 }}>{note}</Text>
      </View>
    </View>
  )
}
