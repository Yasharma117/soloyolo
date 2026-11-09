import { Button, Text, ThemeProvider as DSTheme, ToastProvider, useTheme } from '@soloyolo/design-system'
import { DarkTheme, DefaultTheme, Stack, ThemeProvider, type ErrorBoundaryProps } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { ScrollView } from 'react-native'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { ReasonProvider } from '../lib/reasons'

function Navigation() {
  const t = useTheme()
  const base = t.scheme === 'dark' ? DarkTheme : DefaultTheme
  return (
    <ThemeProvider value={{ ...base, colors: { ...base.colors, background: t.color.background, card: t.color.background, primary: t.color.accent, text: t.color.textPrimary } }}>
      <ToastProvider>
        <ReasonProvider>
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="person/[id]" options={{ presentation: 'modal' }} />
            <Stack.Screen name="design" options={{ presentation: 'modal' }} />
            <Stack.Screen name="screens" options={{ presentation: 'modal' }} />
            <Stack.Screen name="status" />
          </Stack>
        </ReasonProvider>
      </ToastProvider>
      <StatusBar style="auto" />
    </ThemeProvider>
  )
}

export default function Root() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <DSTheme>
          <Navigation />
        </DSTheme>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}

// If anything throws while rendering, show it instead of a blank screen, with a way to retry.
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  return (
    <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 80, gap: 12 }}>
      <Text variant="heading">soloyolo hit an error</Text>
      <Text variant="small" selectable>{error.message}</Text>
      <Text variant="caption" tone="tertiary" selectable>{(error.stack ?? '').slice(0, 1500)}</Text>
      <Button label="Try again" variant="primary" onPress={retry} />
    </ScrollView>
  )
}
