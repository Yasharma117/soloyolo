// An item you can swipe: left for Done (green, as iOS does for completing), right for Not needed.
// A quiet item swiped left is Still on instead: it comes back to Today for 3 days.
import Ionicons from '@expo/vector-icons/Ionicons'
import * as Haptics from 'expo-haptics'
import { useRouter } from 'expo-router'
import { useRef } from 'react'
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native'
import Swipeable, { SwipeDirection, type SwipeableMethods } from 'react-native-gesture-handler/ReanimatedSwipeable'
import { mark } from '../lib/api'
import { usePalette } from '../lib/theme'
import { ago, isOpen, type Item, type Mark } from '../lib/types'
import { Apps, Avatar, Chips, Quote } from './ui'
import { useToast } from './Toast'

const SAID: Record<Mark, string> = {
  done: 'Marked done', dismissed: 'Marked not needed', open: 'Kept on for 3 more days', snoozed: 'Snoozed for 3 days', clear: 'Undone',
}

function Action({ color, icon, label, align }: { color: string; icon: keyof typeof Ionicons.glyphMap; label: string; align: 'left' | 'right' }) {
  return (
    <View style={[styles.action, { backgroundColor: color, alignItems: align === 'left' ? 'flex-start' : 'flex-end' }]}>
      <View style={styles.actionMark}>
        <Ionicons name={icon} size={22} color="#fff" />
        <Text style={styles.actionText}>{label}</Text>
      </View>
    </View>
  )
}

function useMark() {
  const toast = useToast()
  return async (c: Item, state: Mark) => {
    if (Platform.OS !== 'web') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {})
    try {
      await mark(c, state)
      toast.show(SAID[state], state === 'clear' ? undefined : () => mark(c, 'clear'))
    } catch {
      toast.show('Couldn’t save that. Is soloyolo running on your Mac?')
    }
  }
}

/** Today's card: who, what's owed, the message it came from, why it's here. */
export function TodayCard({ item }: { item: Item }) {
  const c = usePalette()
  const router = useRouter()
  const ref = useRef<SwipeableMethods>(null)
  const act = useMark()
  return (
    <View style={styles.cardWrap}>
      <Swipeable
        ref={ref}
        friction={1}
        overshootFriction={8}
        rightThreshold={80}
        leftThreshold={80}
        containerStyle={{ borderRadius: 16 }}
        renderRightActions={() => <Action color={c.done} icon="checkmark" label="Done" align="right" />}
        renderLeftActions={() => <Action color={c.dismiss} icon="close" label="Not needed" align="left" />}
        onSwipeableOpen={(d) => act(item, d === SwipeDirection.LEFT ? 'done' : 'dismissed')}
      >
        <Pressable onPress={() => router.push({ pathname: '/person/[id]', params: { id: String(item.person_id), focus: String(item.source_message_id) } })}
                   style={[styles.card, { backgroundColor: c.card }]}>
          <View style={styles.who}>
            <Avatar name={item.name} />
            <Text style={[styles.name, { color: c.ink }]} numberOfLines={1}>{item.name}</Text>
            <Apps networks={item.networks} label />
            <Text style={[styles.when, { color: c.ink3 }]}>{ago(item.source_ts)}</Text>
          </View>
          <View style={styles.body}>
            {item.owner === 'them' && <Text style={[styles.owes, { color: c.ink3 }]}>{item.name.split(' ')[0]!.toUpperCase()} OWES YOU</Text>}
            <Text style={[styles.what, { color: c.ink }]}>{item.action}</Text>
            <Quote text={item.source_text?.slice(0, 160)} />
            <Chips reasons={item.reasons} />
          </View>
        </Pressable>
      </Swipeable>
    </View>
  )
}

/** A row in a grouped list (a person's items, everything open). */
export function ItemRow({ item, showName = false, last = false }: { item: Item; showName?: boolean; last?: boolean }) {
  const c = usePalette()
  const router = useRouter()
  const act = useMark()
  const open = isOpen(item)
  const quiet = open && !item.live
  const state = item.dismissed ? 'not needed' : item.snoozed ? 'later' : item.status === 'done'
    ? item.resolved_by && item.resolved_by !== 'you' ? `done (${item.resolved_by})` : 'done'
    : item.live ? 'on today’s list' : 'quiet, assumed done'
  const row = (
    <Pressable
      onPress={() => showName && router.push({ pathname: '/person/[id]', params: { id: String(item.person_id), focus: String(item.source_message_id) } })}
      style={[styles.row, { backgroundColor: c.card }]}
    >
      <View style={[styles.dot, { backgroundColor: !open || quiet ? c.line : item.owner === 'me' ? c.accent : 'transparent', borderColor: item.owner === 'me' || !open || quiet ? 'transparent' : c.ink3 }]} />
      <View style={[styles.rowBody, !last && { borderBottomColor: c.line, borderBottomWidth: StyleSheet.hairlineWidth }]}>
        <Text style={[styles.rowWhat, { color: open ? c.ink : c.ink3, textDecorationLine: open ? 'none' : 'line-through' }]}>
          {showName ? <Text style={{ fontWeight: '600' }}>{item.name}: </Text> : null}
          {item.owner === 'them' && showName ? 'owes you · ' : ''}{item.action}
        </Text>
        <Text style={[styles.rowMeta, { color: c.ink2 }]}>{state} · said {ago(item.source_ts)} ago{item.due ? ` · due ${item.due}` : ''}</Text>
        {open && !quiet ? <View style={{ marginTop: 6 }}><Chips reasons={item.reasons} /></View> : null}
      </View>
    </Pressable>
  )
  if (!open) {
    return (
      <Swipeable friction={1} rightThreshold={70} renderRightActions={() => <Action color={c.dismiss} icon="arrow-undo" label="Undo" align="right" />}
                 onSwipeableOpen={() => act(item, item.status === 'done' && item.resolved_by && item.resolved_by !== 'you' ? 'open' : 'clear')}>
        {row}
      </Swipeable>
    )
  }
  return (
    <Swipeable
      friction={1}
      rightThreshold={70}
      leftThreshold={70}
      renderRightActions={() => quiet
        ? <Action color={c.later} icon="refresh" label="Still on" align="right" />
        : <Action color={c.done} icon="checkmark" label="Done" align="right" />}
      renderLeftActions={() => <Action color={c.dismiss} icon="close" label="Not needed" align="left" />}
      onSwipeableOpen={(d) => act(item, d === SwipeDirection.LEFT ? (quiet ? 'open' : 'done') : 'dismissed')}
    >
      {row}
    </Swipeable>
  )
}

const styles = StyleSheet.create({
  cardWrap: { marginHorizontal: 16, marginBottom: 12 },
  card: { borderRadius: 16, padding: 16, gap: 8 },
  who: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  name: { fontSize: 15, fontWeight: '600', flexShrink: 1 },
  when: { marginLeft: 'auto', fontSize: 13 },
  body: { marginLeft: 36, gap: 8 },
  owes: { fontSize: 12, fontWeight: '600', letterSpacing: 0.6, marginBottom: -4 },
  what: { fontSize: 19, fontWeight: '600', lineHeight: 24, letterSpacing: -0.2 },
  action: { flex: 1, justifyContent: 'center', borderRadius: 16, minWidth: 96 },
  actionMark: { width: 96, alignItems: 'center', gap: 4 },
  actionText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  row: { flexDirection: 'row', paddingLeft: 16 },
  dot: { width: 9, height: 9, borderRadius: 5, marginTop: 18, marginRight: 12, borderWidth: 1.5 },
  rowBody: { flex: 1, paddingVertical: 12, paddingRight: 16 },
  rowWhat: { fontSize: 16, lineHeight: 21 },
  rowMeta: { fontSize: 13, marginTop: 2 },
})
