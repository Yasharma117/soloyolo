import * as Haptics from 'expo-haptics'
import { useEffect, type ReactNode } from 'react'
import { Platform, Pressable, StyleSheet, View } from 'react-native'
import Animated, { FadeIn, FadeOut, Keyframe } from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { useTheme } from '../../theme'
import { Icon, type IconName } from '../Icon/Icon'
import { Overlay } from '../Overlay/Overlay'
import { Text } from '../Text/Text'

export type MenuAction = {
  /** Verb first, at most three words: "Mark done", "Snooze a day". */
  label: string
  icon: IconName
  onPress: () => void
  /** Red, for the one action that destroys something. Not needed is not destructive. */
  danger?: boolean
}

export type ActionMenuProps = {
  open: boolean
  onClose: () => void
  /** What was pressed, lifted above the menu so you can see what the actions apply to (Todoist's long-press). */
  preview?: ReactNode
  /** Actions in groups; a gap separates the groups. */
  groups: MenuAction[][]
}

// Grows from 95% like ConfirmDialog: it arrives, it doesn't explode.
const arrive = (ms: number) => new Keyframe({ 0: { opacity: 0, transform: [{ scale: 0.95 }] }, 100: { opacity: 1, transform: [{ scale: 1 }] } }).duration(ms)

/**
 * What a long-press opens: the pressed thing lifted, and its actions under it, near the thumb. A light haptic on
 * open. Picking an action closes the menu first, so a sheet the action opens (ReasonSheet) doesn't stack on it.
 */
export function ActionMenu({ open, onClose, preview, groups }: ActionMenuProps) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  useEffect(() => {
    if (open && Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {})
  }, [open])
  return (
    <Overlay open={open} onClose={onClose}>
      {open ? (
        <Animated.View entering={FadeIn.duration(t.motion.fast)} exiting={FadeOut.duration(t.motion.fast)}
                       style={{ flex: 1, justifyContent: 'flex-end', gap: t.space.md, backgroundColor: t.color.scrim,
                                paddingHorizontal: t.space.lg, paddingBottom: Math.max(insets.bottom, t.space.lg) + t.space.sm }}>
          <Pressable accessibilityLabel="Close" style={StyleSheet.absoluteFill} onPress={onClose} />
          {preview ? <Animated.View entering={arrive(t.motion.base)} pointerEvents="none">{preview}</Animated.View> : null}
          <Animated.View entering={arrive(t.motion.fast)} accessibilityViewIsModal accessibilityRole="menu"
                         style={{ backgroundColor: t.color.surface, borderRadius: t.radius.xl, overflow: 'hidden', shadowColor: t.color.shadow, ...t.shadow.floating }}>
            {groups.map((g, gi) => (
              <View key={gi} style={{ borderTopWidth: gi ? 6 : 0, borderTopColor: t.color.surfaceRaised }}>
                {g.map((a, i) => (
                  <Pressable key={a.label} accessibilityRole="menuitem" onPress={() => { onClose(); a.onPress() }}
                             style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: t.space.md, paddingHorizontal: t.space.lg, paddingVertical: t.space.md + 2,
                                                        backgroundColor: pressed ? t.color.surfaceRaised : 'transparent',
                                                        borderTopWidth: i ? StyleSheet.hairlineWidth : 0, borderTopColor: t.color.border })}>
                    <Icon name={a.icon} size="lg" tone={a.danger ? 'danger' : 'primary'} />
                    <Text variant="body" tone={a.danger ? 'danger' : 'primary'} style={{ fontSize: 16 }}>{a.label}</Text>
                  </Pressable>
                ))}
              </View>
            ))}
          </Animated.View>
        </Animated.View>
      ) : null}
    </Overlay>
  )
}
