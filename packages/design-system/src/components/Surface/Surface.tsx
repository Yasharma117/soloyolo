import { Pressable, View, type PressableProps, type ViewProps } from 'react-native'
import { useTheme } from '../../theme'

export type SurfaceProps = ViewProps & {
  /** card: white on paper with a soft shadow. outline: hairline border, no shadow. raised: a tinted fill. */
  variant?: 'card' | 'outline' | 'raised' | 'dashed'
  radius?: 'lg' | 'xl' | 'card'
  padded?: boolean
  onPress?: PressableProps['onPress']
}

/** Anything that sits on the page as an object: cards, piles, grouped lists. */
export function Surface({ variant = 'card', radius = 'card', padded = true, onPress, style, ...rest }: SurfaceProps) {
  const t = useTheme()
  const look = [
    { borderRadius: t.radius[radius], padding: padded ? t.space.lg + 2 : 0 },
    variant === 'card' && { backgroundColor: t.color.surface, shadowColor: t.color.shadow, ...t.shadow.card },
    variant === 'outline' && { backgroundColor: t.color.surface, borderWidth: 0.5, borderColor: t.color.border },
    variant === 'raised' && { backgroundColor: t.color.surfaceRaised },
    variant === 'dashed' && { borderWidth: 1, borderStyle: 'dashed' as const, borderColor: t.color.border },
    style,
  ]
  if (onPress) return <Pressable onPress={onPress} style={look} {...(rest as PressableProps)} />
  return <View style={look} {...rest} />
}
