import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { ItemRow } from '../../components/SwipeItem'
import { LargeTitle, SectionTitle } from '../../components/ui'
import { useData } from '../../lib/api'
import { usePalette } from '../../lib/theme'
import { keyOf, type Item } from '../../lib/types'

export default function All() {
  const c = usePalette()
  const insets = useSafeAreaInsets()
  const { data } = useData<Item[]>('/api/all')
  const live = (data ?? []).filter((x) => x.live)
  const quiet = (data ?? []).filter((x) => !x.live)
  const group = (list: Item[]) => list.length
    ? <View style={[styles.group, { backgroundColor: c.card }]}>{list.map((it, i) => <ItemRow key={keyOf(it)} item={it} showName last={i === list.length - 1} />)}</View>
    : <Text style={{ color: c.ink3, paddingHorizontal: 20 }}>Nothing.</Text>
  return (
    <ScrollView style={{ backgroundColor: c.ground }} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 40 }}>
      <LargeTitle title="All open" subtitle="Everything still open, and why it ranks where it does" />
      <SectionTitle>{`On today’s list · ${live.length}`}</SectionTitle>
      {group(live)}
      <SectionTitle>{`Quiet · ${quiet.length}`}</SectionTitle>
      <Text style={{ color: c.ink2, fontSize: 13, paddingHorizontal: 20, marginTop: -2, marginBottom: 8 }}>
        Assumed done. Swipe left on anything that isn’t, to keep it on.
      </Text>
      {group(quiet)}
    </ScrollView>
  )
}

const styles = StyleSheet.create({ group: { marginHorizontal: 16, borderRadius: 14, overflow: 'hidden' } })
