import { StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'

/** A hairline between sections that are actually different. Never decoration. */
export function Divider({ vertical, inset = 0 }: { vertical?: boolean; inset?: number }) {
  const t = useTheme()
  return vertical
    ? <View style={{ width: StyleSheet.hairlineWidth, alignSelf: 'stretch', backgroundColor: t.color.border }} />
    : <View style={{ height: StyleSheet.hairlineWidth, marginLeft: inset, backgroundColor: t.color.border }} />
}
