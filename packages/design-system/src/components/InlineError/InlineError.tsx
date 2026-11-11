import { StyleSheet, View } from 'react-native'
import { useTheme } from '../../theme'
import { Button } from '../Button/Button'
import { Icon } from '../Icon/Icon'
import { Text } from '../Text/Text'

/**
 * A section that failed to load (from Markon's inline-error): name what failed, say why in plain words, give the next
 * step. The rest of the screen keeps working; a whole failed screen is a StatusScreen.
 */
export function InlineError({ title, body, onRetry, retryLabel = 'Try again' }: { title: string; body: string; onRetry?: () => void; retryLabel?: string }) {
  const t = useTheme()
  return (
    <View accessibilityRole="alert" style={{ marginHorizontal: t.space.lg, alignItems: 'center', gap: t.space.sm, paddingVertical: t.space.xl, paddingHorizontal: t.space.lg,
                                             backgroundColor: t.color.surface, borderRadius: t.radius.xl, borderWidth: StyleSheet.hairlineWidth, borderColor: t.color.border }}>
      <Icon name="alert-circle" size="lg" tone="danger" />
      <Text variant="bodyStrong" align="center">{title}</Text>
      <Text variant="small" tone="tertiary" align="center">{body}</Text>
      {onRetry ? <View style={{ marginTop: t.space.xs }}><Button label={retryLabel} icon="refresh" size="sm" onPress={onRetry} /></View> : null}
    </View>
  )
}
