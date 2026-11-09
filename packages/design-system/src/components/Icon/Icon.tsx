import Ionicons from '@expo/vector-icons/Ionicons'
import { useTheme } from '../../theme'
import type { iconSize } from '../../tokens'

/** The icons the product uses (Ionicons). Add a name here before using it, so the set stays small and consistent. */
export const ICONS = [
  'sunny', 'sunny-outline', 'people', 'people-outline', 'albums', 'albums-outline', 'git-network', 'git-network-outline',
  'checkmark', 'close', 'refresh', 'arrow-undo', 'arrow-up', 'arrow-down', 'call', 'search', 'chevron-forward', 'chevron-down',
  'chatbubble-outline', 'notifications-outline', 'notifications-off-outline', 'flask-outline', 'paper-plane-outline',
  'reader-outline', 'color-palette-outline', 'logo-whatsapp', 'logo-linkedin', 'logo-instagram', 'logo-x', 'logo-slack',
  'chatbubble', 'chatbox', 'paper-plane', 'chatbubble-ellipses',
] as const
export type IconName = (typeof ICONS)[number]

type Tone = 'primary' | 'secondary' | 'tertiary' | 'accent' | 'onColor' | 'inverse'
const TONE = { primary: 'textPrimary', secondary: 'textSecondary', tertiary: 'textTertiary', accent: 'accentText', onColor: 'onColor', inverse: 'onInverse' } as const

export function Icon({ name, size = 'md', tone = 'secondary' }: { name: IconName; size?: keyof typeof iconSize; tone?: Tone }) {
  const t = useTheme()
  return <Ionicons name={name} size={t.iconSize[size]} color={t.color[TONE[tone]]} />
}

/** The app glyph for a messaging network. */
export const NETWORK_ICON: Record<string, IconName> = {
  whatsapp: 'logo-whatsapp', linkedin: 'logo-linkedin', instagram: 'logo-instagram', x: 'logo-x', slack: 'logo-slack',
  imessage: 'chatbubble', sms: 'chatbox', telegram: 'paper-plane',
}
export const NETWORK_NAME: Record<string, string> = {
  whatsapp: 'WhatsApp', linkedin: 'LinkedIn', instagram: 'Instagram', x: 'X', slack: 'Slack', imessage: 'iMessage', sms: 'SMS', telegram: 'Telegram',
}
export function NetworkIcon({ network, size = 'xs' }: { network: string; size?: keyof typeof iconSize }) {
  return <Icon name={NETWORK_ICON[network] ?? 'chatbubble-ellipses'} size={size} tone="tertiary" />
}
