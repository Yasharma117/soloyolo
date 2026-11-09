import { DarkTheme, DefaultTheme, Stack, ThemeProvider, type ErrorBoundaryProps } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { Pressable, ScrollView, Text, useColorScheme } from 'react-native'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { ToastProvider } from '../components/Toast'
import { usePalette } from '../lib/theme'

export default function Root() {
  const scheme = useColorScheme()
  const c = usePalette()
  const base = scheme === 'dark' ? DarkTheme : DefaultTheme
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider value={{ ...base, colors: { ...base.colors, background: c.ground, card: c.ground, primary: c.accent, text: c.ink } }}>
          <ToastProvider>
            <Stack screenOptions={{ headerShadowVisible: false, headerStyle: { backgroundColor: c.ground }, headerTintColor: c.ink }}>
              <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
              <Stack.Screen name="person/[id]" options={{ headerShown: false, presentation: 'modal' }} />
            </Stack>
          </ToastProvider>
          <StatusBar style="auto" />
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}

// If anything throws while rendering, show it instead of a blank screen, with a way to retry.
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  return (
    <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 80, gap: 12 }} style={{ backgroundColor: '#fff' }}>
      <Text style={{ fontSize: 22, fontWeight: '700', color: '#111' }}>soloyolo hit an error</Text>
      <Text selectable style={{ fontSize: 14, color: '#333', fontFamily: 'Menlo' }}>{error.message}</Text>
      <Text selectable style={{ fontSize: 11, color: '#666', fontFamily: 'Menlo' }}>{(error.stack ?? '').slice(0, 1500)}</Text>
      <Pressable onPress={retry} style={{ alignSelf: 'flex-start', backgroundColor: '#111', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 10 }}>
        <Text style={{ color: '#fff', fontSize: 16, fontWeight: '600' }}>Try again</Text>
      </Pressable>
    </ScrollView>
  )
}
