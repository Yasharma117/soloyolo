import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { View, type ViewStyle } from 'react-native'
import type { OverlayProps } from './Overlay'

/**
 * On the web a Modal portals to <body>, which on a desktop preview puts sheets outside the phone frame. This portals
 * into the frame's overlay layer (`[data-overlay-host]`) when there is one, else <body>. Esc closes, like the back button.
 */
export function Overlay({ open, onClose, children }: OverlayProps) {
  useEffect(() => {
    if (!open) return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [open, onClose])

  if (!open) return null
  const host = document.querySelector('[data-overlay-host]')
  // Fixed fills the viewport on a phone; inside the frame (contain: paint) it fills the frame instead.
  const fill = { position: host ? 'absolute' : 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 1000 } as unknown as ViewStyle
  return createPortal(<View pointerEvents="auto" style={fill}>{children}</View>, host ?? document.body)
}
