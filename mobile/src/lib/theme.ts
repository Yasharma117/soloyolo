import { Platform, useColorScheme } from 'react-native'

// soloyolo's look, from its references (Mobbin): Atoms' warm paper and serif sentences, Mesh's
// gradient orbs and quiet uppercase labels, HEY's plain-spoken titles and swipe-to-done.
// One accent, marigold, for what's urgent and for the words that matter in a sentence.
const light = {
  ground: '#f6f4ef', // warm paper
  card: '#ffffff',
  raised: '#ece9e2',
  ink: '#16150f',
  ink2: '#6b675e',
  ink3: '#a8a399',
  line: '#e6e2d9',
  dot: '#d9d4c8',
  hot: '#a35c00',
  hotSoft: '#fbeccb',
  accent: '#e8a317',
  done: '#2fa864',
  later: '#6a5acd',
  dismiss: '#8a857a',
  live: '#2e7d5b',
  pill: 'rgba(255,255,255,0.92)',
  black: '#16150f',
  onBlack: '#f6f4ef',
}

const dark: typeof light = {
  ground: '#0e0d0b',
  card: '#1a1916',
  raised: '#26241f',
  ink: '#f2efe8',
  ink2: '#a19c91',
  ink3: '#6a665d',
  line: '#2c2a25',
  dot: '#24221d',
  hot: '#ffc35a',
  hotSoft: '#3a2b10',
  accent: '#f2b33d',
  done: '#35c272',
  later: '#8b7dff',
  dismiss: '#6a665d',
  live: '#5cc08e',
  pill: 'rgba(32,30,26,0.94)',
  black: '#f2efe8',
  onBlack: '#0e0d0b',
}

export type Palette = typeof light

export function usePalette(): Palette {
  return useColorScheme() === 'dark' ? dark : light
}

/** The editorial face for sentences (Atoms): the platform's own serif, nothing to download. */
export const serif = Platform.select({ ios: 'Georgia', android: 'serif', default: 'Georgia, "Times New Roman", serif' })

// Mesh-style orbs: two warm or cool hues per person, picked from the name so it never changes.
const ORBS: [string, string][] = [
  ['#ffb36b', '#f0567a'], ['#7fd1c7', '#4f7cf0'], ['#ffd36b', '#ff8a3d'], ['#b9a3ff', '#ff86c8'],
  ['#8fe3a1', '#2fa8a0'], ['#ffc9a8', '#c879ff'], ['#9ad0ff', '#6a5acd'], ['#ffe08a', '#7fd17a'],
]
export function orbColors(name: string): [string, string] {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return ORBS[h % ORBS.length]!
}
