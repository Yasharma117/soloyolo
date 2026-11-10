import { Text as RNText, type TextProps, type TextStyle } from 'react-native'
import { useTheme } from '../../theme'
import { serifVariants, type TypeVariant } from '../../tokens'

type Tone = 'primary' | 'secondary' | 'tertiary' | 'accent' | 'success' | 'inverse' | 'onColor' | 'danger' | 'info'

export type TextPropsDS = TextProps & {
  /** The type scale step. display, title, headline and the sentences are the serif (serifVariants). */
  variant?: TypeVariant
  tone?: Tone
  /** Uppercase with tracking; on by default for `label`. */
  upper?: boolean
  align?: TextStyle['textAlign']
}

const TONE = { primary: 'textPrimary', secondary: 'textSecondary', tertiary: 'textTertiary', accent: 'accentText',
               success: 'successText', inverse: 'onInverse', onColor: 'onColor', danger: 'dangerText', info: 'infoText' } as const

/** All text in the app. Never use react-native's Text directly in screens (lint enforces it). */
export function Text({ variant = 'body', tone = 'primary', upper, align, style, children, ...rest }: TextPropsDS) {
  const t = useTheme()
  const step = t.type[variant]
  // A bundled face carries its weight in the file, so the serif picks Regular or Medium and drops fontWeight
  // (Android falls back to the system font when a custom family is asked for a weight it doesn't have).
  const serif = serifVariants.includes(variant)
    ? { fontFamily: Number(step.fontWeight) >= 500 ? t.serifMedium : t.serif, fontWeight: 'normal' as const } : null
  const isLabel = variant === 'label'
  return (
    <RNText
      {...rest}
      style={[step, { color: t.color[TONE[tone]], textAlign: align }, serif,
              (upper ?? isLabel) && { textTransform: 'uppercase' }, style]}
    >
      {children}
    </RNText>
  )
}
