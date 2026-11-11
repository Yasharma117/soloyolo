import MaskedViewClass from '@react-native-masked-view/masked-view'
import type { ComponentType, ReactElement, ReactNode } from 'react'
import { LinearGradient } from 'expo-linear-gradient'
import { Platform, type TextStyle } from 'react-native'
import { Text, type TextPropsDS } from '../Text/Text'

// the package's class typings predate React 19's JSX types; its runtime is fine
const MaskedView = MaskedViewClass as unknown as ComponentType<{ maskElement: ReactElement; children: ReactNode }>

/**
 * Words filled with a gradient, as the Atoms redesign sets its headlines ("Never Miss Twice"). One phrase per screen
 * at most: it's for the line you want stopped on. Native draws the gradient through a text mask; web clips it to the
 * text with CSS, since the mask is a no-op there.
 */
export function GradientText({ colors, children, style, ...rest }: Omit<TextPropsDS, 'tone'> & { colors: [string, string] }) {
  if (Platform.OS === 'web') {
    const clip = { backgroundImage: `linear-gradient(135deg, ${colors[0]}, ${colors[1]})`, backgroundClip: 'text', WebkitBackgroundClip: 'text',
                   color: 'transparent' } as unknown as TextStyle
    return <Text {...rest} style={[style, clip]}>{children}</Text>
  }
  return (
    <MaskedView maskElement={<Text {...rest} style={style}>{children}</Text>}>
      <LinearGradient colors={colors} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}>
        <Text {...rest} style={[style, { opacity: 0 }]}>{children}</Text>
      </LinearGradient>
    </MaskedView>
  )
}
