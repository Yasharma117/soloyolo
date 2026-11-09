import { Avatar } from '../components/Avatar/Avatar'
import { NetworkIcon } from '../components/Icon/Icon'
import { ListRow } from '../components/ListRow/ListRow'
import { Row } from '../components/Stack/Stack'
import { Text } from '../components/Text/Text'
import { ago } from './types'

/** A person in a list: who, which apps, what's open between you, when you last talked. */
export function PersonRow({ name, networks = [], youOwe = 0, theyOwe = 0, last, onPress }: {
  name: string; networks?: string[]; youOwe?: number; theyOwe?: number; last: number; onPress?: () => void
}) {
  return (
    <ListRow
      lead={<Avatar name={name} size="lg" />}
      onPress={onPress}
      title={<Row gap="xs"><Text variant="bodyStrong" numberOfLines={1} style={{ fontSize: 16, flexShrink: 1 }}>{name}</Text>{networks.slice(0, 2).map((n) => <NetworkIcon key={n} network={n} />)}</Row>}
      subtitle={
        <Text variant="small" tone="tertiary">
          {youOwe ? <Text variant="small" tone="accent" style={{ fontWeight: '600' }}>you owe {youOwe}</Text> : null}
          {youOwe && theyOwe ? ' · ' : ''}{theyOwe ? `owes you ${theyOwe}` : ''}{!youOwe && !theyOwe ? 'nothing open' : ''}
        </Text>
      }
      trailing={<Text variant="caption" tone="tertiary">{ago(last)}</Text>}
    />
  )
}
