import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import Animated, { FadeInDown, FadeOutDown } from 'react-native-reanimated'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { usePalette } from '../lib/theme'

type Toast = { text: string; undo?: () => unknown; id: number }
const Ctx = createContext<{ show: (text: string, undo?: () => unknown) => void }>({ show: () => {} })

export const useToast = () => useContext(Ctx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const c = usePalette()
  const insets = useSafeAreaInsets()
  const [toast, setToast] = useState<Toast | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const show = useCallback((text: string, undo?: () => unknown) => {
    if (timer.current) clearTimeout(timer.current)
    const id = Date.now()
    setToast({ text, undo, id })
    timer.current = setTimeout(() => setToast((t) => (t?.id === id ? null : t)), 4500)
  }, [])
  return (
    <Ctx.Provider value={{ show }}>
      {children}
      {toast && (
        <Animated.View key={toast.id} entering={FadeInDown.duration(180)} exiting={FadeOutDown.duration(160)}
                       style={[styles.toast, { backgroundColor: c.ink, bottom: insets.bottom + 64 }]} pointerEvents="box-none">
          <Text style={{ color: c.ground, fontSize: 15, flexShrink: 1 }}>{toast.text}</Text>
          {toast.undo && (
            <Pressable hitSlop={10} onPress={() => { const u = toast.undo!; setToast(null); u() }}>
              <Text style={{ color: c.accent, fontSize: 15, fontWeight: '700' }}>Undo</Text>
            </Pressable>
          )}
        </Animated.View>
      )}
    </Ctx.Provider>
  )
}

const styles = StyleSheet.create({
  toast: { position: 'absolute', left: 16, right: 16, borderRadius: 14, paddingHorizontal: 16, paddingVertical: 12,
           flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
})

export const Spacer = () => <View style={{ height: 40 }} />
