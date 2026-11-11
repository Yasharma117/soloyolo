import { Redirect } from 'expo-router'

// Any address the app doesn't know (a hosted preview's own path, an old link) opens Today.
export default function NotFound() {
  return <Redirect href="/" />
}
