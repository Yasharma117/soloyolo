import { View } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

/** Where you are in a short setup: "Step 2 of 3" and a segmented bar. */
export function StepHeader({ step, total, label }: { step: number; total: number; label?: string }) {
  const t = useTheme()
  return (
    <View style={{ gap: t.space.sm }}>
      <Text variant="caption" tone="tertiary">{`Step ${step} of ${total}`}{label ? ` · ${label}` : ''}</Text>
      <View style={{ flexDirection: 'row', gap: t.space.xs }}>
        {Array.from({ length: total }, (_, i) => (
          <View key={i} style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: i < step ? t.color.accent : t.color.surfaceRaised }} />
        ))}
      </View>
    </View>
  )
}
