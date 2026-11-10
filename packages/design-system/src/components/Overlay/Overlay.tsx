import type { ReactNode } from 'react'
import { Modal } from 'react-native'

export type OverlayProps = { open: boolean; onClose: () => void; children?: ReactNode }

/** The layer sheets and dialogs sit on: a transparent Modal on iOS and Android. The web build has its own (Overlay.web.tsx). */
export function Overlay({ open, onClose, children }: OverlayProps) {
  return (
    <Modal visible={open} transparent animationType="none" onRequestClose={onClose} statusBarTranslucent>
      {children}
    </Modal>
  )
}
