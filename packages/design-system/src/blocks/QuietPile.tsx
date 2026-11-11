import { View } from 'react-native'
import { Facepile } from '../components/Avatar/Avatar'
import { Icon } from '../components/Icon/Icon'
import { Row } from '../components/Stack/Stack'
import { Surface } from '../components/Surface/Surface'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

/** Everything assumed done, gathered into one pile (HEY's Reply Later stack). */
export function QuietPile({ names, onPress }: { names: string[]; onPress?: () => void }) {
  const t = useTheme()
  const firsts = [...new Set(names.map((n) => n.split(' ')[0]!))]
  return (
    <View style={{ marginHorizontal: t.space.lg }}>
      <Surface variant="outline" radius="xl" onPress={onPress} style={{ padding: t.space.md + 2 }}>
        <Row gap="md">
          <Facepile names={names} size="sm" />
          <View style={{ flex: 1 }}>
            <Text variant="bodyStrong">{names.length} quiet {names.length === 1 ? 'thing' : 'things'}</Text>
            <Text variant="small" tone="secondary" numberOfLines={1}>{firsts.slice(0, 3).join(', ')}{firsts.length > 3 ? ' and others' : ''}</Text>
          </View>
          <Icon name="chevron-forward" size="lg" tone="tertiary" />
        </Row>
      </Surface>
    </View>
  )
}
