import { createContext, useContext, type ReactNode } from 'react'
import { useColorScheme } from 'react-native'
import { colors, font, iconSize, motion, radius, shadow, space, type, type ColorTokens } from '../tokens'

export type Scheme = 'light' | 'dark'

export type Theme = {
  scheme: Scheme
  color: ColorTokens
  space: typeof space
  radius: typeof radius
  type: typeof type
  shadow: typeof shadow
  motion: typeof motion
  iconSize: typeof iconSize
  serif: string
  serifMedium: string
}

function build(scheme: Scheme): Theme {
  return { scheme, color: colors[scheme], space, radius, type, shadow, motion, iconSize,
           serif: font.serif, serifMedium: font.serifMedium }
}

const themes = { light: build('light'), dark: build('dark') }
const Ctx = createContext<Scheme | null>(null)

/** Follows the device's light or dark setting unless `scheme` pins one (the catalog uses that). */
export function ThemeProvider({ scheme, children }: { scheme?: Scheme; children: ReactNode }) {
  const device = useColorScheme() === 'dark' ? 'dark' : 'light'
  return <Ctx.Provider value={scheme ?? device}>{children}</Ctx.Provider>
}

export function useTheme(): Theme {
  const pinned = useContext(Ctx)
  const device = useColorScheme() === 'dark' ? 'dark' : 'light'
  return themes[pinned ?? device]
}
