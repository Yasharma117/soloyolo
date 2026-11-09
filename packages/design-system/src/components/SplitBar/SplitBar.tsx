import { LinearGradient } from 'expo-linear-gradient'
import { StyleSheet, View } from 'react-native'
import type { ColorTokens } from '../../tokens'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

export type Split = { label: string; value: number; color: keyof ColorTokens }

/**
 * A whole split into its parts: one bar with each part's share and count, then a row per part (from the Atoms
 * redesign's progress strip). Three parts at most; the order is the order you read them in.
 */
export function SplitBar({ parts }: { parts: Split[] }) {
  const t = useTheme()
  const total = parts.reduce((a, p) => a + p.value, 0)
  return (
    <View style={{ gap: t.space.sm }}>
      <View style={{ height: 64, flexDirection: 'row', borderRadius: t.radius.md, overflow: 'hidden', backgroundColor: t.color.surfaceRaised }}>
        {total ? parts.filter((p) => p.value).map((p) => (
          <View key={p.label} style={{ flex: p.value, minWidth: 28 }}>
            {/* solid at the top, fading out at the foot, as in the redesign */}
            <LinearGradient colors={[t.color[p.color], t.color[p.color], t.color.surfaceRaised]} locations={[0, 0.66, 1.2]} style={StyleSheet.absoluteFill} />
            <Text variant="small" tone="onColor" style={{ position: 'absolute', right: 8, bottom: 6, fontWeight: '700' }}>{p.value}</Text>
          </View>
        )) : null}
      </View>
      <View style={{ gap: 4 }}>
        {parts.map((p) => (
          <View key={p.label} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: t.space.md + 2,
                                       paddingVertical: t.space.sm + 1, borderRadius: t.radius.sm + 1, backgroundColor: t.color.surfaceRaised }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.space.sm }}>
              <View style={{ width: 9, height: 9, borderRadius: 5, backgroundColor: t.color[p.color] }} />
              <Text variant="sentenceSmall" tone="secondary" style={{ fontSize: 16 }}>{p.label}</Text>
            </View>
            <Text variant="body" tone="secondary">{p.value}</Text>
          </View>
        ))}
      </View>
    </View>
  )
}
