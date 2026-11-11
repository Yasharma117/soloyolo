import { Pressable, StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

/**
 * A quiet line under something soloyolo isn't sure of, with a coloured bar on the left and one action (from Markon's
 * review-banner, which sits under an extracted value that needs a person to check it). Here: a bank SMS or a group
 * chat suggests a promise is settled, but only you close it.
 */
export function ReviewStrip({ message, actionLabel, onAction, tone = 'info' }: {
  message: string; actionLabel?: string; onAction?: () => void; tone?: 'info' | 'success' | 'danger' | 'accent'
}) {
  const t = useTheme()
  return (
    <View accessibilityRole="summary" style={{ flexDirection: 'row', alignItems: 'center', gap: t.space.md, overflow: 'hidden', borderRadius: t.radius.md,
                                               backgroundColor: t.color.surfaceRaised, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border,
                                               paddingLeft: t.space.md + 2, paddingRight: t.space.md, paddingVertical: t.space.sm }}>
      <View style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, backgroundColor: t.color[tone] }} />
      <Text variant="small" tone="secondary" style={{ flex: 1 }} numberOfLines={2}>{message}</Text>
      {actionLabel && onAction ? (
        <Pressable accessibilityRole="button" onPress={onAction} hitSlop={10}>
          <Text variant="small" tone="accent" style={{ fontWeight: '700' }}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  )
}
