import { Modal, Pressable, View } from 'react-native'
import Animated, { FadeIn, FadeOut, Keyframe } from 'react-native-reanimated'
import { useTheme } from '../../theme'
import { Button } from '../Button/Button'
import { Text } from '../Text/Text'

export type ConfirmDialogProps = {
  open: boolean
  /** Verb + object; a question only when it destroys something: "Unlink WhatsApp?" */
  title: string
  /** What happens, then the consequence: "soloyolo stops reading your chats. Promises already found stay." */
  body: string
  /** Repeat the object: "Unlink WhatsApp", never "Yes" or "Confirm". */
  confirmLabel: string
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}

// Grows from 95%, not from nothing: a dialog should arrive, not explode.
const arrive = (ms: number) => new Keyframe({ 0: { opacity: 0, transform: [{ scale: 0.95 }] }, 100: { opacity: 1, transform: [{ scale: 1 }] } }).duration(ms)

export function ConfirmDialog({ open, title, body, confirmLabel, destructive, onConfirm, onCancel }: ConfirmDialogProps) {
  const t = useTheme()
  return (
    <Modal visible={open} transparent animationType="none" onRequestClose={onCancel} statusBarTranslucent>
      {open ? (
        <Animated.View entering={FadeIn.duration(t.motion.fast)} exiting={FadeOut.duration(t.motion.fast)}
                       style={{ flex: 1, backgroundColor: t.color.scrim, justifyContent: 'center', padding: t.space.xxl }}>
          <Pressable accessibilityLabel="Cancel" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={onCancel} />
          <Animated.View entering={arrive(t.motion.fast)} accessibilityViewIsModal
                         style={{ backgroundColor: t.color.surface, borderRadius: t.radius.card, padding: t.space.xl, gap: t.space.md, shadowColor: t.color.shadow, ...t.shadow.floating }}>
            <Text variant="heading" style={{ fontSize: 20, lineHeight: 26 }}>{title}</Text>
            <Text variant="body" tone="secondary">{body}</Text>
            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: t.space.sm, marginTop: t.space.sm }}>
              <Button label="Cancel" variant="ghost" onPress={onCancel} />
              <Button label={confirmLabel} variant={destructive ? 'danger' : 'primary'} onPress={onConfirm} />
            </View>
          </Animated.View>
        </Animated.View>
      ) : null}
    </Modal>
  )
}
