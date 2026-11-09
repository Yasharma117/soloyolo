import { ScrollView, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { ItemRow } from '../../components/SwipeItem'
import { Label, Title } from '../../components/ui'
import { useData } from '../../lib/api'
import { usePalette } from '../../lib/theme'
import { keyOf, type Item } from '../../lib/types'

export default function All() {
  const c = usePalette()
  const insets = useSafeAreaInsets()
  const { data } = useData<Item[]>('/api/all')
  const live = (data ?? []).filter((x) => x.live)
  const quiet = (data ?? []).filter((x) => !x.live)
  return (
    <ScrollView style={{ backgroundColor: c.ground }} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}>
      <Title title="All open" subtitle="Everything still open. Quiet ones are assumed done; swipe one left if it isn’t." />
      <Label>{`On today · ${live.length}`}</Label>
      {live.length ? live.map((it) => <ItemRow key={keyOf(it)} item={it} />) : <Text style={{ color: c.ink3, paddingHorizontal: 20 }}>Nothing.</Text>}
      <Label>{`Quiet · ${quiet.length}`}</Label>
      {quiet.map((it) => <ItemRow key={keyOf(it)} item={it} />)}
      <View style={{ height: 8 }} />
    </ScrollView>
  )
}
