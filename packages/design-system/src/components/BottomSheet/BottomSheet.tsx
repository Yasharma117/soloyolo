import type { ReactNode } from 'react'
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native'
import Animated, { FadeIn, FadeOut, SlideInDown, SlideOutDown } from 'react-native-reanimated'
import { useSafeAreaFrame, useSafeAreaInsets } from 'react-native-safe-area-context'
import { useTheme } from '../../theme'
import { IconButton } from '../Button/Button'
import { Overlay } from '../Overlay/Overlay'
import { Text } from '../Text/Text'

export type BottomSheetProps = {
  open: boolean
  onClose: () => void
  /** Verb first, at most four words: "Snooze until", "Why this is here". */
  title: string
  subtitle?: string
  children?: ReactNode
  /** The sheet's one action, usually a primary Button. Stays put while the body scrolls. */
  footer?: ReactNode
}

/**
 * For secondary choices and pickers that shouldn't take a whole screen. Closes on the X, a tap on the scrim,
 * or the Android back button. Never taller than 88% of the screen: longer content scrolls, the footer stays.
 */
export function BottomSheet({ open, onClose, title, subtitle, children, footer }: BottomSheetProps) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const { height } = useSafeAreaFrame()
  const bottom = Math.max(insets.bottom, t.space.lg) + t.space.sm
  return (
    <Overlay open={open} onClose={onClose}>
      {open ? (
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, justifyContent: 'flex-end' }}>
          <Animated.View entering={FadeIn.duration(t.motion.fast)} exiting={FadeOut.duration(t.motion.fast)}
                         style={[StyleSheet.absoluteFill, { backgroundColor: t.color.scrim }]}>
            <Pressable accessibilityLabel="Close" style={{ flex: 1 }} onPress={onClose} />
          </Animated.View>
          <Animated.View entering={SlideInDown.duration(t.motion.base + 60)} exiting={SlideOutDown.duration(t.motion.base)}
                         accessibilityViewIsModal
                         style={{ maxHeight: height * 0.88, backgroundColor: t.color.background,
                                  borderTopLeftRadius: t.radius.card, borderTopRightRadius: t.radius.card }}>
            <View style={{ alignSelf: 'center', width: 36, height: 5, borderRadius: 3, backgroundColor: t.color.border, marginTop: t.space.sm }} />
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: t.space.md, paddingHorizontal: t.space.xl,
                           paddingTop: t.space.md, paddingBottom: t.space.lg }}>
              <View style={{ flex: 1, gap: t.space.xs }}>
                <Text variant="heading" style={{ fontSize: 20, lineHeight: 26 }} accessibilityRole="header">{title}</Text>
                {subtitle ? <Text variant="body" tone="secondary">{subtitle}</Text> : null}
              </View>
              <IconButton icon="close" label="Close" onPress={onClose} />
            </View>
            {children ? (
              <ScrollView showsVerticalScrollIndicator={false} style={{ flexShrink: 1 }} contentContainerStyle={{ paddingHorizontal: t.space.xl, paddingBottom: footer ? t.space.lg : bottom, gap: t.space.lg }}
                          keyboardShouldPersistTaps="handled" bounces={false}>
                {children}
              </ScrollView>
            ) : null}
            {footer ? (
              <View style={{ paddingHorizontal: t.space.xl, paddingTop: t.space.md, paddingBottom: bottom, gap: t.space.sm,
                             borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: t.color.border }}>
                {footer}
              </View>
            ) : null}
          </Animated.View>
        </KeyboardAvoidingView>
      ) : null}
    </Overlay>
  )
}
