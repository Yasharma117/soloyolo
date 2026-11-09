import { LinearGradient } from 'expo-linear-gradient'
import { View } from 'react-native'
import { orbs } from '../../tokens'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

export const AVATAR_SIZE = { xs: 22, sm: 26, md: 34, lg: 40, xl: 76 } as const

export function initials(name: string): string {
  const words = name.replace(/[\uD800-\uDFFF()[\]{}.,!?'"@#*_~-]/g, '').trim().split(/\s+/)
  return ((words[0]?.[0] ?? '') + (words.length > 1 ? words[words.length - 1]![0] : '')).toUpperCase() || '?'
}

export function orbFor(name: string): readonly [string, string] {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return orbs[h % orbs.length]!
}

/** A person: a gradient orb with their initials. The same name always gets the same colors. */
export function Avatar({ name, size = 'md' }: { name: string; size?: keyof typeof AVATAR_SIZE }) {
  const px = AVATAR_SIZE[size]
  const [a, b] = orbFor(name)
  return (
    <LinearGradient colors={[a, b]} start={{ x: 0.15, y: 0.1 }} end={{ x: 0.9, y: 0.95 }}
                    style={{ width: px, height: px, borderRadius: px / 2, alignItems: 'center', justifyContent: 'center' }}>
      <Text tone="onColor" style={{ fontSize: Math.round(px * 0.38), lineHeight: Math.round(px * 0.5), fontWeight: '700' }}>{initials(name)}</Text>
    </LinearGradient>
  )
}

/** Overlapping avatars for a group. */
export function Facepile({ names, size = 'md', max = 4 }: { names: string[]; size?: keyof typeof AVATAR_SIZE; max?: number }) {
  const t = useTheme()
  return (
    <View style={{ flexDirection: 'row' }}>
      {names.slice(0, max).map((n, i) => (
        <View key={`${n}${i}`} style={{ marginLeft: i ? -10 : 0, borderRadius: 99, borderWidth: 2, borderColor: t.color.surface }}>
          <Avatar name={n} size={size} />
        </View>
      ))}
    </View>
  )
}
