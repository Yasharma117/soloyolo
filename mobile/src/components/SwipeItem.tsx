// Things you can swipe. Left: Done (HEY's green). Right: Not needed. A quiet item swiped left is
// Still on: it comes back to Today for 3 days. Every swipe can be undone from the toast.
import Ionicons from '@expo/vector-icons/Ionicons'
import * as Haptics from 'expo-haptics'
import { useRouter } from 'expo-router'
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native'
import Swipeable, { SwipeDirection } from 'react-native-gesture-handler/ReanimatedSwipeable'
import { mark } from '../lib/api'
import { usePalette } from '../lib/theme'
import { ago, isOpen, type Item, type Mark } from '../lib/types'
import { Chips, NetIcon, Orb, Quote, Sentence } from './ui'
import { useToast } from './Toast'

const SAID: Record<Mark, string> = {
  done: 'Marked done', dismissed: 'Marked not needed', open: 'Kept on for 3 more days', snoozed: 'Snoozed for 3 days', clear: 'Undone',
}

function Action({ color, icon, label, side, radius = 0 }: { color: string; icon: keyof typeof Ionicons.glyphMap; label: string; side: 'left' | 'right'; radius?: number }) {
  return (
    <View style={[styles.action, { backgroundColor: color, borderRadius: radius, margin: radius ? 3 : 0, alignItems: side === 'left' ? 'flex-start' : 'flex-end' }]}>
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

function openPerson(router: ReturnType<typeof useRouter>, item: Item) {
  router.push({ pathname: '/person/[id]', params: { id: String(item.person_id), focus: String(item.source_message_id) } })
}

/** Today's card: the promise as a sentence, the message it came from, why it's here. */
export function PromiseCard({ item }: { item: Item }) {
  const c = usePalette()
  const router = useRouter()
  const act = useMark()
  return (
    <View style={styles.cardWrap}>
      <Swipeable
        friction={1}
        overshootFriction={8}
        rightThreshold={80}
        leftThreshold={80}
        containerStyle={{ borderRadius: 22 }}
        renderRightActions={() => <Action color={c.done} icon="checkmark" label="Done" side="right" radius={22} />}
        renderLeftActions={() => <Action color={c.dismiss} icon="close" label="Not needed" side="left" radius={22} />}
        onSwipeableOpen={(d) => act(item, d === SwipeDirection.LEFT ? 'done' : 'dismissed')}
      >
        <Pressable onPress={() => openPerson(router, item)} style={[styles.card, { backgroundColor: c.card, shadowColor: '#3b2f12' }]}>
          <View style={styles.who}>
            <Orb name={item.name} size={26} />
            <Text style={[styles.name, { color: c.ink }]} numberOfLines={1}>{item.name}</Text>
            {item.networks?.[0] ? <NetIcon network={item.networks[0]} /> : null}
            <Text style={[styles.when, { color: c.ink3 }]}>{ago(item.source_ts)}</Text>
          </View>
          <Sentence item={item} />
          <Quote text={item.source_text?.slice(0, 160)} />
          <Chips reasons={item.reasons} />
        </Pressable>
      </Swipeable>
    </View>
  )
}

/** A row on the paper, Mesh-style: orb, who, the promise, when. */
export function ItemRow({ item, showName = true, focus = false }: { item: Item; showName?: boolean; focus?: boolean }) {
  const c = usePalette()
  const router = useRouter()
  const act = useMark()
  const open = isOpen(item)
  const quiet = open && !item.live
  const state = item.dismissed ? 'not needed' : item.snoozed ? 'later' : item.status === 'done'
    ? item.resolved_by && item.resolved_by !== 'you' ? `done (${item.resolved_by})` : 'done'
    : item.live ? 'on today' : 'quiet'
  const row = (
    <Pressable onPress={() => showName && openPerson(router, item)}
               style={[styles.row, { backgroundColor: focus ? c.hotSoft : c.ground, borderBottomColor: c.line }]}>
      {showName ? <Orb name={item.name} size={34} /> : <View style={[styles.dot, { backgroundColor: !open ? c.ink3 : quiet ? c.line : c.accent }]} />}
      <View style={{ flex: 1, gap: 3 }}>
        {showName && <Text style={{ color: c.ink, fontSize: 15, fontWeight: '600' }} numberOfLines={1}>{item.name}</Text>}
        <Sentence item={item} size={16} style={!open ? { color: c.ink3, textDecorationLine: 'line-through' } : undefined} />
        <Text style={{ color: c.ink3, fontSize: 12 }}>{state} · said {ago(item.source_ts)} ago{item.due ? ` · due ${item.due}` : ''}</Text>
        {open && !quiet ? <Chips reasons={item.reasons} style={{ marginTop: 4 }} /> : null}
      </View>
    </Pressable>
  )
  if (!open) {
    return (
      <Swipeable friction={1} rightThreshold={70} renderRightActions={() => <Action color={c.dismiss} icon="arrow-undo" label="Undo" side="right" />}
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
        ? <Action color={c.later} icon="refresh" label="Still on" side="right" />
        : <Action color={c.done} icon="checkmark" label="Done" side="right" />}
      renderLeftActions={() => <Action color={c.dismiss} icon="close" label="Not needed" side="left" />}
      onSwipeableOpen={(d) => act(item, d === SwipeDirection.LEFT ? (quiet ? 'open' : 'done') : 'dismissed')}
    >
      {row}
    </Swipeable>
  )
}

const styles = StyleSheet.create({
  cardWrap: { marginHorizontal: 16, marginBottom: 14 },
  card: { borderRadius: 22, padding: 18, gap: 12, shadowOpacity: 0.07, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 2 },
  who: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  name: { fontSize: 14, fontWeight: '600', flexShrink: 1 },
  when: { marginLeft: 'auto', fontSize: 12 },
  action: { flex: 1, justifyContent: 'center', minWidth: 104 },
  actionMark: { width: 104, alignItems: 'center', gap: 4 },
  actionText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingHorizontal: 20, paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  dot: { width: 8, height: 8, borderRadius: 4, marginTop: 8 },
})
