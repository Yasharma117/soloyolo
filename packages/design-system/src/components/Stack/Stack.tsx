import { View, type ViewProps, type ViewStyle } from 'react-native'
import { space } from '../../tokens'

type Space = keyof typeof space

export type StackProps = ViewProps & {
  direction?: 'row' | 'column'
  gap?: Space
  align?: ViewStyle['alignItems']
  justify?: ViewStyle['justifyContent']
  wrap?: boolean
  /** Padding on all sides, or horizontal / vertical. */
  pad?: Space
  padX?: Space
  padY?: Space
  flex?: number
}

/** Layout. Space between children comes from `gap`, never from margins on the children. */
export function Stack({ direction = 'column', gap = 'none', align, justify, wrap, pad, padX, padY, flex, style, ...rest }: StackProps) {
  return (
    <View
      {...rest}
      style={[{ flexDirection: direction, gap: space[gap], alignItems: align, justifyContent: justify, flexWrap: wrap ? 'wrap' : undefined, flex },
              pad !== undefined && { padding: space[pad] }, padX !== undefined && { paddingHorizontal: space[padX] },
              padY !== undefined && { paddingVertical: space[padY] }, style]}
    />
  )
}

export const Row = (p: Omit<StackProps, 'direction'>) => <Stack direction="row" align="center" {...p} />
