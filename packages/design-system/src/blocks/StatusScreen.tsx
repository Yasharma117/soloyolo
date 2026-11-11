// A result: an import finished, a sync failed, pairing is waiting. Never hand-build a centred icon and title.
import { View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Button } from '../components/Button/Button'
import { Icon, type IconName } from '../components/Icon/Icon'
import { FadeIn, Loader } from '../components/Motion/Motion'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

export type StatusTone = 'success' | 'error' | 'pending' | 'info'
const LOOK: Record<Exclude<StatusTone, 'pending'>, { icon: IconName; fill: 'successSoft' | 'dangerSoft' | 'infoSoft'; ink: 'success' | 'danger' | 'info' }> = {
  success: { icon: 'checkmark', fill: 'successSoft', ink: 'success' },
  error: { icon: 'alert-circle', fill: 'dangerSoft', ink: 'danger' },
  info: { icon: 'information-circle', fill: 'infoSoft', ink: 'info' },
}

type Action = { label: string; onPress: () => void }

/** Title is the object and its state ("Chats imported", "Sync stopped"). Body is the outcome and, for errors, the next step. */
export function StatusScreen({ tone, title, body, primary, secondary }: { tone: StatusTone; title: string; body?: string; primary?: Action; secondary?: Action }) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const look = tone === 'pending' ? null : LOOK[tone]
  return (
    <View style={{ flex: 1, backgroundColor: t.color.background, paddingTop: insets.top, paddingBottom: Math.max(insets.bottom, t.space.lg) }}>
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: t.space.xxl, gap: t.space.lg }}>
        <FadeIn>
          {look ? (
            <View style={{ width: 88, height: 88, borderRadius: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: t.color[look.fill] }}>
              <Icon name={look.icon} size="xxl" tone={look.ink} />
            </View>
          ) : <View style={{ height: 88, justifyContent: 'center' }}><Loader /></View>}
        </FadeIn>
        <Text variant="heading" align="center">{title}</Text>
        {body ? <Text variant="body" tone="secondary" align="center">{body}</Text> : null}
      </View>
      {primary || secondary ? (
        <View style={{ paddingHorizontal: t.space.xl, gap: t.space.sm }}>
          {primary ? <Button label={primary.label} variant="primary" onPress={primary.onPress} /> : null}
          {secondary ? <Button label={secondary.label} variant="ghost" onPress={secondary.onPress} /> : null}
        </View>
      ) : null}
    </View>
  )
}
