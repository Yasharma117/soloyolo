import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { useColorScheme } from 'react-native'
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
              <Stack.Screen name="person/[id]" options={{ title: '', headerBackTitle: 'Back' }} />
            </Stack>
          </ToastProvider>
          <StatusBar style="auto" />
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}
