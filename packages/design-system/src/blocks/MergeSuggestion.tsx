import { View } from 'react-native'
import { Avatar } from '../components/Avatar/Avatar'
import { Button } from '../components/Button/Button'
import { Chip } from '../components/Chip/Chip'
import { Icon, NetworkIcon } from '../components/Icon/Icon'
import { Row } from '../components/Stack/Stack'
import { Surface } from '../components/Surface/Surface'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

export type MergePerson = { name: string; networks?: string[]; /** What tells them apart: a number, a company. */ detail?: string | null; messages?: number }

function Side({ p }: { p: MergePerson }) {
  const t = useTheme()
  return (
    <View style={{ flex: 1, alignItems: 'center', gap: t.space.xs }}>
      <Avatar name={p.name} size="lg" />
      <Text variant="bodyStrong" align="center" numberOfLines={2} style={{ marginTop: t.space.xs }}>{p.name}</Text>
      {p.networks?.length ? <Row gap="xs">{p.networks.slice(0, 3).map((n) => <NetworkIcon key={n} network={n} size="sm" />)}</Row> : null}
      {p.detail ? <Text variant="small" tone="secondary" align="center" numberOfLines={1}>{p.detail}</Text> : null}
      {p.messages != null ? <Text variant="caption" tone="tertiary">{p.messages === 1 ? '1 message' : `${p.messages.toLocaleString()} messages`}</Text> : null}
    </View>
  )
}

/**
 * "Are these the same person?" Two chats side by side with what tells them apart, why soloyolo asks (its reasons,
 * as it wrote them), and the two answers. soloyolo suggests, you decide: nothing merges without Same person, and
 * Different people is remembered so it isn't asked again.
 */
export function MergeSuggestion({ a, b, reasons, onSame, onDifferent, busy }: {
  a: MergePerson; b: MergePerson; reasons: string[]; onSame?: () => void; onDifferent?: () => void; busy?: boolean
}) {
  const t = useTheme()
  return (
    <View style={{ marginHorizontal: t.space.lg }}>
      <Surface style={{ gap: t.space.lg }}>
        <Row gap="sm" align="flex-start">
          <Side p={a} />
          <View style={{ width: 32, height: 32, borderRadius: 16, marginTop: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: t.color.surfaceRaised }}>
            <Icon name="link-outline" size="md" tone="secondary" />
          </View>
          <Side p={b} />
        </Row>
        {reasons.length ? (
          <View style={{ gap: t.space.sm }}>
            <Text variant="label" tone="tertiary" upper>Why soloyolo asks</Text>
            <Row gap="xs" wrap>{reasons.map((r) => <Chip key={r} label={r} />)}</Row>
          </View>
        ) : null}
        <Row gap="sm">
          <View style={{ flex: 1 }}><Button label="Different people" onPress={onDifferent} disabled={busy} /></View>
          <View style={{ flex: 1 }}><Button label="Same person" variant="primary" onPress={onSame} loading={busy} /></View>
        </Row>
      </Surface>
    </View>
  )
}
