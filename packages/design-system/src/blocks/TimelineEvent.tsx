import { StyleSheet, View } from 'react-native'
import Svg, { Line } from 'react-native-svg'
import { Icon } from '../components/Icon/Icon'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'
import { ago } from './types'

/**
 * One message in a person's timeline, laid out like Markon's activity feed: a marker on a dotted rail, who and when,
 * then the message in a bubble cut square where it leaves the rail. `isSource` marks the message a promise came from.
 * Pass `last` on the final event so the rail stops there.
 */
export function TimelineEvent({ who, text, ts, fromMe, call, isSource, last }: {
  who: string; text: string; ts: number; fromMe: boolean; call?: boolean; isSource?: boolean; last?: boolean
}) {
  const t = useTheme()
  const name = fromMe ? 'You' : who
  return (
    <View style={{ flexDirection: 'row', gap: t.space.md, paddingHorizontal: t.space.xl }}>
      <View style={{ width: 24, alignItems: 'center' }}>
        <View style={{ width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
                       backgroundColor: isSource ? t.color.accentSoft : t.color.surfaceRaised,
                       borderWidth: StyleSheet.hairlineWidth, borderColor: isSource ? t.color.accent : t.color.border }}>
          <Icon name={call ? 'call' : fromMe ? 'arrow-up' : 'arrow-down'} size="xs" tone={isSource ? 'accent' : 'secondary'} />
        </View>
        {last ? null : (
          // drawn over the row, not inside its layout: an svg that sizes itself is 150 tall on web and stretches the row
          <View style={{ position: 'absolute', top: 28, bottom: 4, left: 11, width: 2 }}>
            <Svg width={2} height="100%">
              <Line x1={1} y1={1} x2={1} y2="100%" stroke={t.color.border} strokeWidth={2} strokeDasharray="0,6" strokeLinecap="round" />
            </Svg>
          </View>
        )}
      </View>
      <View style={{ flex: 1, gap: 6, paddingBottom: last ? t.space.md : t.space.xl }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.space.sm, minHeight: 24 }}>
          <Text variant="small" style={{ fontWeight: '600' }}>{name}</Text>
          <Text variant="caption" tone="tertiary">{ago(ts)}</Text>
          {isSource ? <Text variant="caption" tone="accent" style={{ marginLeft: 'auto', fontWeight: '700' }}>The promise</Text> : null}
        </View>
        {call ? (
          <Text variant="small" tone="tertiary">{fromMe ? 'You called' : `${who} called`}</Text>
        ) : (
          <View style={{ alignSelf: 'flex-start', maxWidth: '100%', paddingHorizontal: t.space.md, paddingVertical: t.space.sm + 1,
                         borderRadius: t.radius.lg, borderTopLeftRadius: 2,
                         backgroundColor: isSource ? t.color.accentSoft : t.color.surface,
                         borderWidth: isSource ? 1 : StyleSheet.hairlineWidth, borderColor: isSource ? t.color.accent : t.color.border }}>
            <Text variant="body" style={{ fontSize: 15, lineHeight: 21 }}>{text}</Text>
          </View>
        )}
      </View>
    </View>
  )
}
