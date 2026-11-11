import { View } from 'react-native'
import { useTheme } from '../../theme'
import { Button } from '../Button/Button'
import { Icon, type IconName } from '../Icon/Icon'
import { Text } from '../Text/Text'

export type BannerTone = 'info' | 'warning' | 'success' | 'danger'
const LOOK: Record<BannerTone, { fill: 'infoSoft' | 'accentSoft' | 'successSoft' | 'dangerSoft'; ink: 'info' | 'accent' | 'success' | 'danger'; icon: IconName }> = {
  info: { fill: 'infoSoft', ink: 'info', icon: 'information-circle' },
  warning: { fill: 'accentSoft', ink: 'accent', icon: 'warning' },
  success: { fill: 'successSoft', ink: 'success', icon: 'checkmark-circle' },
  danger: { fill: 'dangerSoft', ink: 'danger', icon: 'alert-circle' },
}

/** A state worth knowing before reading the screen. Body is the state and its impact, in one sentence:
 *  "WhatsApp hasn't synced for 12 hours. New promises won't show up until it does." */
export function Banner({ tone = 'info', title, body, action }: { tone?: BannerTone; title: string; body?: string; action?: { label: string; onPress: () => void } }) {
  const t = useTheme()
  const l = LOOK[tone]
  return (
    <View accessibilityRole="alert" style={{ flexDirection: 'row', gap: t.space.md, padding: t.space.md + 2, borderRadius: t.radius.xl, backgroundColor: t.color[l.fill] }}>
      <View style={{ paddingTop: 1 }}><Icon name={l.icon} size="lg" tone={l.ink} /></View>
      <View style={{ flex: 1, gap: t.space.xs }}>
        <Text variant="bodyStrong" tone={l.ink}>{title}</Text>
        {body ? <Text variant="small" tone="secondary">{body}</Text> : null}
        {action ? <View style={{ alignSelf: 'flex-start', marginTop: t.space.xs }}><Button label={action.label} size="sm" onPress={action.onPress} /></View> : null}
      </View>
    </View>
  )
}
