import { StyleSheet, View } from 'react-native'
import { Icon } from '../components/Icon/Icon'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import { ago } from './types'

/** One message in a person's timeline. `isSource` marks the message a promise came from. */
export function TimelineEvent({ who, text, ts, fromMe, call, isSource }: { who: string; text: string; ts: number; fromMe: boolean; call?: boolean; isSource?: boolean }) {
  const t = useTheme()
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingHorizontal: t.space.xl, paddingVertical: 11,
                   borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: t.color.border, backgroundColor: isSource ? t.color.accentSoft : undefined }}>
      <View style={{ width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center', marginTop: 1, backgroundColor: t.color.surfaceRaised }}>
        <Icon name={call ? 'call' : fromMe ? 'arrow-up' : 'arrow-down'} size="xs" tone="secondary" />
      </View>
      <Text variant="body" tone="secondary" style={{ flex: 1, fontSize: 14, lineHeight: 20 }}>
        <Text variant="body" tone="tertiary" style={{ fontSize: 14 }}>{call ? 'A call' : fromMe ? 'You: ' : `${who}: `}</Text>
        {call ? '' : <Text variant="body" style={{ fontSize: 14 }}>{text}</Text>}
        {isSource ? <Text variant="body" tone="accent" style={{ fontSize: 14, fontWeight: '600' }}>{'  · the promise'}</Text> : null}
      </Text>
      <Text variant="caption" tone="tertiary">{ago(ts)}</Text>
    </View>
  )
}
