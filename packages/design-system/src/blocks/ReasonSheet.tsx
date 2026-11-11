import { StyleSheet, View } from 'react-native'
import { BottomSheet } from '../components/BottomSheet/BottomSheet'
import { Button } from '../components/Button/Button'
import { NavList } from '../components/SectionCard/SectionCard'
import type { IconName } from '../components/Icon/Icon'
import { useTheme } from '../theme'

export type Reason<K extends string = string> = { key: K; label: string; icon?: IconName }

export type ReasonSheetProps<K extends string> = {
  open: boolean
  /** A question, because it is one: "Why isn't it needed?" */
  title: string
  subtitle?: string
  reasons: Reason<K>[]
  onPick: (key: K) => void
  /** Skip, the X and a tap outside all land here. The action already happened; skipping only leaves the why blank. */
  onSkip: () => void
}

/**
 * Asks why after the action, never before it. The action is saved the moment it's taken, so the
 * question costs one tap or none. Markon guards an action behind a required reason for its audit
 * trail; here the reason is optional and feeds the record of what closes promises off the chat.
 */
export function ReasonSheet<K extends string>({ open, title, subtitle, reasons, onPick, onSkip }: ReasonSheetProps<K>) {
  const t = useTheme()
  return (
    <BottomSheet open={open} onClose={onSkip} title={title} subtitle={subtitle}
                 footer={<Button label="Skip" variant="ghost" onPress={onSkip} />}>
      <View style={{ backgroundColor: t.color.surface, borderRadius: t.radius.xl, borderWidth: StyleSheet.hairlineWidth,
                     borderColor: t.color.border, overflow: 'hidden' }}>
        <NavList rows={reasons.map((r) => ({ icon: r.icon, label: r.label, onPress: () => onPick(r.key) }))} />
      </View>
    </BottomSheet>
  )
}
