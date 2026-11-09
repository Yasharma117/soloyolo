import { Pressable, StyleSheet, View } from 'react-native'
import { Avatar } from '../components/Avatar/Avatar'
import { Icon, NetworkIcon, type IconName } from '../components/Icon/Icon'
import { Row } from '../components/Stack/Stack'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

export type PersonAction = { icon: IconName; label: string; onPress: () => void; disabled?: boolean }

/** The top of a person's sheet (Mesh): name and orb, how recently you talked, a strip of actions. */
export function PersonHeader({ name, network, subtitle, actions = [] }: { name: string; network?: string; subtitle: string; actions?: PersonAction[] }) {
  const t = useTheme()
  return (
    <View>
      <Row gap="lg" padX="xl" style={{ paddingTop: t.space.md + 2, paddingBottom: t.space.lg + 2 }}>
        <View style={{ flex: 1, gap: t.space.xs + 2 }}>
          <Text variant="title" style={{ fontSize: 28, lineHeight: 34 }}>{name}</Text>
          <Row gap="xs">{network ? <NetworkIcon network={network} size="sm" /> : null}<Text variant="body" tone="secondary" style={{ fontSize: 14 }}>{subtitle}</Text></Row>
        </View>
        <Avatar name={name} size="xl" />
      </Row>
      {actions.length ? (
        <View style={{ flexDirection: 'row', borderTopWidth: StyleSheet.hairlineWidth, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: t.color.border }}>
          {actions.map((a, i) => (
            <Pressable key={a.label} accessibilityRole="button" accessibilityLabel={a.label} disabled={a.disabled} onPress={a.onPress}
                       style={[{ flex: 1, alignItems: 'center', gap: t.space.xs + 2, paddingVertical: t.space.md, opacity: a.disabled ? 0.35 : 1 },
                               i > 0 && { borderLeftWidth: StyleSheet.hairlineWidth, borderLeftColor: t.color.border }]}>
              <Icon name={a.icon} size="lg" tone="primary" />
              <Text variant="label" tone="secondary" style={{ fontSize: 10, letterSpacing: 1 }}>{a.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  )
}
