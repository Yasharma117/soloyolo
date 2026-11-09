import { LinearGradient } from 'expo-linear-gradient'
import { StyleSheet, View } from 'react-native'
import Svg, { Circle, Defs, Pattern, Rect } from 'react-native-svg'
import { useTheme } from '../../theme'

/** The dotted paper behind a page's header, fading into the background. */
export function DotGrid({ height = 260 }: { height?: number }) {
  const t = useTheme()
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { height }]}>
      <Svg width="100%" height={height}>
        <Defs>
          <Pattern id="ds-dots" width={10} height={10} patternUnits="userSpaceOnUse">
            <Circle cx={2} cy={2} r={1.1} fill={t.color.texture} />
          </Pattern>
        </Defs>
        <Rect width="100%" height={height} fill="url(#ds-dots)" />
      </Svg>
      <LinearGradient colors={['transparent', t.color.background]} style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: height * 0.7 }} />
    </View>
  )
}
