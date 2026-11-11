import { LinearGradient } from 'expo-linear-gradient'
import { ActivityIndicator, Pressable, StyleSheet } from 'react-native'
import { useTheme } from '../../theme'
import { Icon, type IconName } from '../Icon/Icon'
import { Text } from '../Text/Text'

export type ButtonProps = {
  label: string
  onPress?: () => void
  /** One primary per screen. Secondary for the rest; ghost for low-stakes actions. `warm` is the Atoms-style gradient pill
   *  for the single action a card exists for (Still on, Adjust habit); never more than one on screen. */
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'warm' | 'soft'
  size?: 'sm' | 'md'
  icon?: IconName
  disabled?: boolean
  loading?: boolean
}

export function Button({ label, onPress, variant = 'secondary', size = 'md', icon, disabled, loading }: ButtonProps) {
  const t = useTheme()
  const h = size === 'sm' ? 34 : 44
  const fill = variant === 'primary' ? t.color.inverse : variant === 'secondary' ? t.color.surface : variant === 'soft' ? t.color.surfaceRaised : 'transparent'
  const textTone = variant === 'primary' ? 'inverse' : variant === 'danger' ? 'danger' : 'primary'
  return (
    <Pressable
      accessibilityRole="button" accessibilityLabel={label} disabled={disabled || loading} onPress={onPress}
      style={({ pressed }) => ({
        height: h, paddingHorizontal: size === 'sm' ? t.space.md : t.space.lg, borderRadius: t.radius.pill, flexDirection: 'row',
        alignItems: 'center', justifyContent: 'center', gap: t.space.xs + 2, backgroundColor: fill, opacity: disabled ? 0.4 : pressed ? 0.8 : 1, overflow: 'hidden',
        borderWidth: variant === 'secondary' ? 0.5 : 0, borderColor: t.color.border,
      })}
    >
      {variant === 'warm' ? <LinearGradient colors={[t.color.warmFrom, t.color.warmTo]} start={{ x: 0.45, y: 0 }} end={{ x: 0.55, y: 1 }} style={StyleSheet.absoluteFill} /> : null}
      {loading ? <ActivityIndicator size="small" color={variant === 'primary' ? t.color.onInverse : t.color.textSecondary} />
        : icon ? <Icon name={icon} size="md" tone={variant === 'primary' ? 'inverse' : 'primary'} /> : null}
      <Text variant={size === 'sm' ? 'small' : 'bodyStrong'} tone={textTone} style={[{ fontWeight: '600' }, variant === 'warm' && { color: t.color.onWarm }]}>{label}</Text>
    </Pressable>
  )
}

export function IconButton({ icon, label, onPress }: { icon: IconName; label: string; onPress?: () => void }) {
  const t = useTheme()
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} hitSlop={8}
               style={({ pressed }) => ({ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center',
                                          backgroundColor: t.color.surface, borderWidth: 0.5, borderColor: t.color.border, opacity: pressed ? 0.7 : 1 })}>
      <Icon name={icon} size="lg" tone="primary" />
    </Pressable>
  )
}
