import { View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

/** What an empty list says: what's not here, and what happens next. */
export function EmptyState({ title, body }: { title: string; body?: string }) {
  const t = useTheme()
  return (
    <View style={{ marginHorizontal: t.space.lg, borderRadius: t.radius.card, borderWidth: 1, borderStyle: 'dashed', borderColor: t.color.border, padding: t.space.xl, gap: t.space.xs + 2 }}>
      <Text variant="sentence" style={{ fontSize: 20, lineHeight: 27 }}>{title}</Text>
      {body ? <Text variant="small" tone="secondary" style={{ fontSize: 14, lineHeight: 20 }}>{body}</Text> : null}
    </View>
  )
}
