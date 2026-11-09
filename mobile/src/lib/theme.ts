import { useColorScheme } from 'react-native'

// iOS grouped style: a gray ground, white cards, one warm accent for what is urgent
// (a due date, someone chasing), the system green for Done.
const light = {
  ground: '#f2f2f7',
  card: '#ffffff',
  raised: '#e9e9ee',
  ink: '#111114',
  ink2: '#6e6e73',
  ink3: '#aeaeb2',
  line: '#e5e5ea',
  hot: '#a86300',
  hotSoft: '#fff1d6',
  done: '#34c759',
  dismiss: '#8e8e93',
  later: '#5e5ce6',
  accent: '#e39a0b',
  live: '#2e7d5b',
}

const dark: typeof light = {
  ground: '#000000',
  card: '#1c1c1e',
  raised: '#2c2c2e',
  ink: '#f5f5f7',
  ink2: '#a1a1a6',
  ink3: '#636366',
  line: '#38383a',
  hot: '#ffc15e',
  hotSoft: '#3a2a0e',
  done: '#30d158',
  dismiss: '#636366',
  later: '#7d7aff',
  accent: '#f2b33d',
  live: '#5cc08e',
}

export type Palette = typeof light

export function usePalette(): Palette {
  return useColorScheme() === 'dark' ? dark : light
}

// A muted, opaque color per name, like Contacts' monograms.
const HUES = ['#8c9ab0', '#c98f6e', '#7fa88e', '#a58cc0', '#c0a46a', '#6fa3b8', '#b98a9f', '#8fa36c']
export function nameColor(name: string): string {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return HUES[h % HUES.length]!
}
