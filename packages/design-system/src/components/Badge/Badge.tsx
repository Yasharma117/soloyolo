import { View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

/** A dot (something new) or a small count. */
export function Badge({ count }: { count?: number }) {
  const t = useTheme()
  if (!count) return <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: t.color.accent }} />
  return (
    <View style={{ minWidth: 18, height: 18, paddingHorizontal: 5, borderRadius: 9, backgroundColor: t.color.accent, alignItems: 'center', justifyContent: 'center' }}>
      <Text variant="caption" tone="onColor" style={{ fontWeight: '700' }}>{count}</Text>
    </View>
  )
}
