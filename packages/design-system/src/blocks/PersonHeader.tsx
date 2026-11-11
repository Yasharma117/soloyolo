import { View } from 'react-native'
import { Avatar } from '../components/Avatar/Avatar'
import { Button } from '../components/Button/Button'
import { NetworkIcon, type IconName } from '../components/Icon/Icon'
import { Row } from '../components/Stack/Stack'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

export type PersonAction = { icon: IconName; label: string; onPress: () => void; disabled?: boolean }

/** The top of a person's sheet: name in the serif and orb (Mesh), how recently you talked, then the actions as pills
 *  (Atoms): the first warm, the rest soft. `icon` is kept for callers; the pills are words only. */
export function PersonHeader({ name, network, subtitle, actions = [] }: { name: string; network?: string; subtitle: string; actions?: PersonAction[] }) {
  const t = useTheme()
  return (
    <View>
      <Row gap="lg" padX="xl" style={{ paddingTop: t.space.md + 2, paddingBottom: t.space.lg + 2 }}>
        <View style={{ flex: 1, gap: t.space.xs + 2 }}>
          <Text variant="title">{name}</Text>
          <Row gap="xs">{network ? <NetworkIcon network={network} size="sm" /> : null}<Text variant="body" tone="secondary" style={{ fontSize: 14 }}>{subtitle}</Text></Row>
        </View>
        <Avatar name={name} size="xl" />
      </Row>
      {actions.length ? (
        <Row gap="sm" padX="xl" style={{ paddingBottom: t.space.xs }}>
          {actions.map((a, i) => (
            <View key={a.label} style={{ flex: 1 }}>
              <Button label={a.label} variant={i === 0 ? 'warm' : 'soft'} disabled={a.disabled} onPress={a.onPress} />
            </View>
          ))}
        </Row>
      ) : null}
    </View>
  )
}
