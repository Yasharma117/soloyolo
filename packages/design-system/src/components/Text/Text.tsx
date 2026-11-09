import { Text as RNText, type TextProps, type TextStyle } from 'react-native'
import { useTheme } from '../../theme'
import type { TypeVariant } from '../../tokens'

type Tone = 'primary' | 'secondary' | 'tertiary' | 'accent' | 'success' | 'inverse' | 'onColor' | 'danger'

export type TextPropsDS = TextProps & {
  /** The type scale step. `sentence` and `sentenceSmall` are the serif. */
  variant?: TypeVariant
  tone?: Tone
  /** Uppercase with tracking; on by default for `label`. */
  upper?: boolean
  align?: TextStyle['textAlign']
}

const TONE = { primary: 'textPrimary', secondary: 'textSecondary', tertiary: 'textTertiary', accent: 'accentText',
               success: 'successText', inverse: 'onInverse', onColor: 'onColor', danger: 'danger' } as const

/** All text in the app. Never use react-native's Text directly in screens (lint enforces it). */
export function Text({ variant = 'body', tone = 'primary', upper, align, style, children, ...rest }: TextPropsDS) {
  const t = useTheme()
  const serif = variant === 'sentence' || variant === 'sentenceSmall'
  const isLabel = variant === 'label'
  return (
    <RNText
      {...rest}
      style={[t.type[variant], { color: t.color[TONE[tone]], textAlign: align, fontFamily: serif ? t.serif : undefined },
              (upper ?? isLabel) && { textTransform: 'uppercase' }, style]}
    >
      {children}
    </RNText>
  )
}
