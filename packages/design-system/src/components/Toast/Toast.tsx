import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { Pressable, StyleSheet } from 'react-native'
import Animated, { FadeInDown, FadeOutDown } from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

type Toast = { text: string; undo?: () => unknown; id: number }
const Ctx = createContext<{ show: (text: string, undo?: () => unknown) => void }>({ show: () => {} })

/** `const toast = useToast(); toast.show('Marked done', undo)`. One at a time, gone after 4.5s. */
export const useToast = () => useContext(Ctx)

export function ToastProvider({ children, offset = 70 }: { children: ReactNode; offset?: number }) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const [toast, setToast] = useState<Toast | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const show = useCallback((text: string, undo?: () => unknown) => {
    if (timer.current) clearTimeout(timer.current)
    const id = Date.now()
    setToast({ text, undo, id })
    timer.current = setTimeout(() => setToast((x) => (x?.id === id ? null : x)), 4500)
  }, [])
  return (
    <Ctx.Provider value={{ show }}>
      {children}
      {toast && (
        <Animated.View key={toast.id} entering={FadeInDown.duration(t.motion.fast + 20)} exiting={FadeOutDown.duration(t.motion.fast)}
                       pointerEvents="box-none"
                       style={[styles.toast, { backgroundColor: t.color.inverse, bottom: Math.max(insets.bottom, 12) + offset, borderRadius: t.radius.lg }]}>
          <Text variant="body" tone="inverse" style={{ flexShrink: 1 }}>{toast.text}</Text>
          {toast.undo && (
            <Pressable accessibilityRole="button" hitSlop={10} onPress={() => { const u = toast.undo!; setToast(null); u() }}>
              <Text variant="bodyStrong" style={{ color: t.color.accent, fontWeight: '700' }}>Undo</Text>
            </Pressable>
          )}
        </Animated.View>
      )}
    </Ctx.Provider>
  )
}

const styles = StyleSheet.create({
  toast: { position: 'absolute', left: 16, right: 16, paddingHorizontal: 16, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
})
