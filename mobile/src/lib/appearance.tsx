// Light, dark, or whatever the phone is set to. Remembered on the device; the phone's setting until you pick one.
import AsyncStorage from '@react-native-async-storage/async-storage'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useColorScheme } from 'react-native'

export type Appearance = 'system' | 'light' | 'dark'

const KEY = 'soloyolo.appearance'
const Ctx = createContext<{ appearance: Appearance; scheme: 'light' | 'dark'; set: (a: Appearance) => void }>({
  appearance: 'system', scheme: 'light', set: () => {},
})

export function AppearanceProvider({ children }: { children: (scheme: 'light' | 'dark') => ReactNode }) {
  const device = useColorScheme() === 'dark' ? 'dark' : 'light'
  const [appearance, setAppearance] = useState<Appearance>('system')
  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((v) => { if (v === 'light' || v === 'dark' || v === 'system') setAppearance(v) })
      .catch(() => {}) // storage unavailable: keep following the phone
  }, [])
  const set = (a: Appearance) => {
    setAppearance(a)
    AsyncStorage.setItem(KEY, a).catch(() => {}) // lasts this session if it can't be saved
  }
  const scheme = appearance === 'system' ? device : appearance
  return <Ctx.Provider value={{ appearance, scheme, set }}>{children(scheme)}</Ctx.Provider>
}

export const useAppearance = () => useContext(Ctx)
