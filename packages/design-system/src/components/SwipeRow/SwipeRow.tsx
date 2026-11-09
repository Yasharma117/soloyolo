// Swipe a row or card for an action, as Mail and HEY do. Left reveals the trailing action
// (Done), right reveals the leading one (Not needed). A light haptic confirms it on phones.
import * as Haptics from 'expo-haptics'
import type { ReactNode } from 'react'
import { Platform, View } from 'react-native'
import Swipeable, { SwipeDirection } from 'react-native-gesture-handler/ReanimatedSwipeable'
import { useTheme } from '../../theme'
import { Icon, type IconName } from '../Icon/Icon'
import { Text } from '../Text/Text'

export type SwipeAction = { label: string; icon: IconName; tone: 'success' | 'later' | 'neutralAction'; onAction: () => void }

function Panel({ action, side, radius }: { action: SwipeAction; side: 'left' | 'right'; radius: number }) {
  const t = useTheme()
  return (
    <View style={{ flex: 1, minWidth: 104, justifyContent: 'center', backgroundColor: t.color[action.tone], borderRadius: radius,
                   margin: radius ? 3 : 0, alignItems: side === 'left' ? 'flex-start' : 'flex-end' }}>
      <View style={{ width: 104, alignItems: 'center', gap: 4 }}>
        <Icon name={action.icon} size="xl" tone="onColor" />
        <Text variant="small" tone="onColor" style={{ fontWeight: '600' }}>{action.label}</Text>
      </View>
    </View>
  )
}

export function SwipeRow({ children, trailing, leading, radius = 0 }: { children: ReactNode; trailing?: SwipeAction; leading?: SwipeAction; radius?: number }) {
  const act = (a?: SwipeAction) => {
    if (!a) return
    if (Platform.OS !== 'web') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {})
    a.onAction()
  }
  return (
    <Swipeable friction={1} overshootFriction={8} rightThreshold={75} leftThreshold={75} containerStyle={{ borderRadius: radius }}
               renderRightActions={trailing ? () => <Panel action={trailing} side="right" radius={radius} /> : undefined}
               renderLeftActions={leading ? () => <Panel action={leading} side="left" radius={radius} /> : undefined}
               onSwipeableOpen={(d) => act(d === SwipeDirection.LEFT ? trailing : leading)}>
      {children}
    </Swipeable>
  )
}
