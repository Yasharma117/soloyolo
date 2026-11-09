// The skeleton of a full screen (after Markon's Screen): a header with an optional back button and a
// title block, a scrolling body, and a footer that sticks to the bottom with the screen's one primary action.
import type { ReactNode } from 'react'
import { ScrollView, StyleSheet, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { IconButton } from '../components/Button/Button'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

function Root({ children }: { children: ReactNode }) {
  const t = useTheme()
  return <View style={{ flex: 1, backgroundColor: t.color.background }}>{children}</View>
}

/** Title at most four words, no end punctuation. Subtitle one sentence that says what the screen is for. */
function Header({ title, subtitle, onBack, backIcon = 'chevron-back', large, trailing, children }: {
  title: string; subtitle?: string; onBack?: () => void; backIcon?: 'chevron-back' | 'chevron-down'; large?: boolean; trailing?: ReactNode; children?: ReactNode
}) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  return (
    <View style={{ paddingTop: insets.top + t.space.sm, paddingHorizontal: t.space.xl, paddingBottom: t.space.md, gap: t.space.md }}>
      {onBack || trailing ? (
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginHorizontal: -t.space.xs }}>
          {onBack ? <IconButton icon={backIcon} label="Back" onPress={onBack} /> : <View />}
          {trailing}
        </View>
      ) : null}
      <View style={{ gap: t.space.xs }}>
        <Text variant={large ? 'title' : 'heading'}>{title}</Text>
        {subtitle ? <Text variant="body" tone="secondary">{subtitle}</Text> : null}
      </View>
      {children}
    </View>
  )
}

function Body({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  const t = useTheme()
  if (!scroll) return <View style={{ flex: 1, gap: t.space.lg }}>{children}</View>
  return <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: t.space.xxl, gap: t.space.lg }}>{children}</ScrollView>
}

/** Sticks to the bottom above the home indicator. Put one primary Button here; secondary actions above it. */
function Footer({ children }: { children: ReactNode }) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  return (
    <View style={{ paddingHorizontal: t.space.xl, paddingTop: t.space.md, paddingBottom: Math.max(insets.bottom, t.space.lg), gap: t.space.sm,
                   borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: t.color.border, backgroundColor: t.color.background }}>
      {children}
    </View>
  )
}

export const Screen = Object.assign(Root, { Header, Body, Footer })
