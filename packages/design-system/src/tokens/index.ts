// The one source of truth for how soloyolo looks. Components read semantic tokens through
// useTheme(); nothing outside this folder writes a hex value (scripts/check.mjs enforces it).
//
// Two layers, as in most design systems:
//   palette  raw scales, named by hue and step. Never used directly by components.
//   semantic what a color is FOR (background, text, the urgent accent), per theme.

export const palette = {
  paper: { 0: '#ffffff', 50: '#f6f4ef', 100: '#ece9e2', 200: '#e6e2d9', 300: '#d9d4c8', 500: '#a8a399', 700: '#6b675e', 900: '#16150f' },
  night: { 0: '#0e0d0b', 50: '#1a1916', 100: '#26241f', 200: '#2c2a25', 300: '#24221d', 500: '#6a665d', 700: '#a19c91', 900: '#f2efe8' },
  marigold: { 50: '#fbf1dc', 100: '#fbeccb', 300: '#f2b33d', 500: '#e8a317', 700: '#a35c00', 900: '#3a2b10', 950: '#ffc35a' },
  leaf: { 500: '#2fa864', 600: '#35c272', 700: '#2e7d5b', 400: '#5cc08e' },
  violet: { 500: '#6a5acd', 400: '#8b7dff' },
  stone: { 500: '#8a857a', 600: '#6a665d' },
  ember: { 100: '#fbe3e1', 500: '#d64545', 400: '#ff6b6b', 700: '#a32a2a', 900: '#3d1715' },
  sky: { 100: '#e1effa', 400: '#7cb8f2', 500: '#2f7fd1', 700: '#1f5f9e', 900: '#122a3d' },
  leafSoft: { 100: '#e2f1e9', 900: '#11261c' },
  white: '#ffffff',
  shadow: '#2b2310',
} as const

const light = {
  background: palette.paper[50], // warm paper, never pure white as a page
  wash: palette.marigold[50], // the warm tint at the top of a screen, fading into the paper (Markon's wash)
  surface: palette.paper[0], // cards sit on the paper
  surfaceRaised: palette.paper[100], // chips, search fields, pressed rows
  surfaceFloating: 'rgba(255,255,255,0.92)', // the tab bar over content
  textPrimary: palette.paper[900],
  textSecondary: palette.paper[700],
  textTertiary: palette.paper[500],
  border: palette.paper[200],
  texture: palette.paper[300], // the dot grid
  accent: palette.marigold[500], // what's urgent; the owed words in a sentence
  accentText: palette.marigold[700],
  accentSoft: palette.marigold[100],
  success: palette.leaf[500], // Done
  successText: palette.leaf[700],
  later: palette.violet[500], // Still on / Later
  neutralAction: palette.stone[500], // Not needed
  danger: palette.ember[500],
  dangerText: palette.ember[700],
  dangerSoft: palette.ember[100],
  successSoft: palette.leafSoft[100],
  info: palette.sky[500],
  infoText: palette.sky[700],
  infoSoft: palette.sky[100],
  scrim: 'rgba(22,21,15,0.32)', // behind sheets and dialogs
  inverse: palette.paper[900], // the selected tab, primary buttons
  onInverse: palette.paper[50],
  onColor: palette.white, // text on a colored fill
  shadow: palette.shadow,
}

export type ColorTokens = { [K in keyof typeof light]: string }

const dark: ColorTokens = {
  background: palette.night[0],
  wash: palette.night[100],
  surface: palette.night[50],
  surfaceRaised: palette.night[100],
  surfaceFloating: 'rgba(32,30,26,0.94)',
  textPrimary: palette.night[900],
  textSecondary: palette.night[700],
  textTertiary: palette.night[500],
  border: palette.night[200],
  texture: palette.night[300],
  accent: palette.marigold[300],
  accentText: palette.marigold[950],
  accentSoft: palette.marigold[900],
  success: palette.leaf[600],
  successText: palette.leaf[400],
  later: palette.violet[400],
  neutralAction: palette.stone[600],
  danger: palette.ember[400],
  dangerText: palette.ember[400],
  dangerSoft: palette.ember[900],
  successSoft: palette.leafSoft[900],
  info: palette.sky[400],
  infoText: palette.sky[400],
  infoSoft: palette.sky[900],
  scrim: 'rgba(0,0,0,0.55)',
  inverse: palette.night[900],
  onInverse: palette.night[0],
  onColor: palette.white,
  shadow: '#000000',
}

export const colors = { light, dark }

/** Avatar orbs: two hues per person, chosen from the name so a person keeps their colors. */
export const orbs: readonly [string, string][] = [
  ['#ffb36b', '#f0567a'], ['#7fd1c7', '#4f7cf0'], ['#ffd36b', '#ff8a3d'], ['#b9a3ff', '#ff86c8'],
  ['#8fe3a1', '#2fa8a0'], ['#ffc9a8', '#c879ff'], ['#9ad0ff', '#6a5acd'], ['#ffe08a', '#7fd17a'],
]

/** 4-point grid. Use the names, not numbers, in components. */
export const space = { none: 0, xxs: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 28, xxxl: 40 } as const

export const radius = { sm: 6, md: 10, lg: 14, xl: 18, card: 22, pill: 999 } as const

export const font = {
  /** The platform's own faces: nothing to download, native on every device. */
  sans: undefined as string | undefined,
  /** Editorial serif for promise sentences (Georgia on iOS and web, the system serif on Android). */
  serif: { ios: 'Georgia', android: 'serif', default: 'Georgia, "Times New Roman", serif' },
} as const

/** Type scale: size / line height / weight. Hierarchy comes from size and weight, one step at a time. */
export const type = {
  display: { fontSize: 52, lineHeight: 56, fontWeight: '800', letterSpacing: -2 },
  title: { fontSize: 32, lineHeight: 38, fontWeight: '800', letterSpacing: -0.6 },
  heading: { fontSize: 24, lineHeight: 30, fontWeight: '700', letterSpacing: -0.4 },
  subheading: { fontSize: 17, lineHeight: 22, fontWeight: '600', letterSpacing: 0 },
  body: { fontSize: 15, lineHeight: 21, fontWeight: '400', letterSpacing: 0 },
  bodyStrong: { fontSize: 15, lineHeight: 21, fontWeight: '600', letterSpacing: 0 },
  small: { fontSize: 13, lineHeight: 18, fontWeight: '400', letterSpacing: 0 },
  caption: { fontSize: 12, lineHeight: 16, fontWeight: '500', letterSpacing: 0 },
  label: { fontSize: 11, lineHeight: 14, fontWeight: '600', letterSpacing: 1.2 }, // uppercase section labels
  sentence: { fontSize: 21, lineHeight: 28, fontWeight: '400', letterSpacing: 0 }, // serif
  sentenceSmall: { fontSize: 16, lineHeight: 21, fontWeight: '400', letterSpacing: 0 }, // serif
} as const

export type TypeVariant = keyof typeof type

export const shadow = {
  card: { shadowOpacity: 0.07, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 2 },
  floating: { shadowOpacity: 0.12, shadowRadius: 20, shadowOffset: { width: 0, height: 8 }, elevation: 6 },
} as const

export const motion = {
  fast: 160, // toasts, presses
  base: 220, // cards leaving, tabs
  slow: 400, // sheets
} as const

export const iconSize = { xs: 12, sm: 14, md: 16, lg: 20, xl: 24, xxl: 32 } as const
