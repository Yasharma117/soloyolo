import { View } from 'react-native'
import { useTheme } from '../../theme'

/** A placeholder line at a real line's size while data loads. */
export function Skeleton({ width = '60%', height = 12 }: { width?: number | `${number}%`; height?: number }) {
  const t = useTheme()
  return <View style={{ width, height, borderRadius: height / 2, backgroundColor: t.color.surfaceRaised }} />
}
