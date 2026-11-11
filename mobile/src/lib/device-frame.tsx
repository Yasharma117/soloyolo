// On iOS and Android the app is the device. The web build draws a phone around it (device-frame.web.tsx).
import type { ReactNode } from 'react'
import { SafeAreaProvider } from 'react-native-safe-area-context'

export function DeviceFrame({ children }: { children: ReactNode }) {
  return <SafeAreaProvider>{children}</SafeAreaProvider>
}
