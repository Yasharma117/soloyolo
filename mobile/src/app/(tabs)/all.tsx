import { PageTitle, PromiseRow, SectionLabel, Text, useTheme } from '@soloyolo/design-system'
import { useRouter } from 'expo-router'
import { ScrollView } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { useData } from '../../lib/api'
import { useMarks } from '../../lib/marks'
import { keyOf, type Item } from '../../lib/types'

export default function All() {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const marks = useMarks()
  const { data } = useData<Item[]>('/api/all')
  const live = (data ?? []).filter((x) => x.live)
  const quiet = (data ?? []).filter((x) => !x.live)
  const open = (it: Item) => router.push({ pathname: '/person/[id]', params: { id: String(it.person_id), focus: String(it.source_message_id) } })
  return (
    <ScrollView style={{ backgroundColor: t.color.background }} contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}>
      <PageTitle title="All open" subtitle="Everything still open. Quiet ones are assumed done; swipe one left if it isn’t." />
      <SectionLabel>{`On today · ${live.length}`}</SectionLabel>
      {live.length ? live.map((it) => (
        <PromiseRow key={keyOf(it)} item={it} state="today" onPress={() => open(it)}
                    trailing={{ label: 'Done', icon: 'checkmark', tone: 'success', onAction: () => marks.done(it) }}
                    leading={{ label: 'Not needed', icon: 'close', tone: 'neutralAction', onAction: () => marks.dismiss(it) }} />
      )) : <Text variant="small" tone="tertiary" style={{ paddingHorizontal: t.space.xl }}>Nothing.</Text>}
      <SectionLabel>{`Quiet · ${quiet.length}`}</SectionLabel>
      {quiet.map((it) => (
        <PromiseRow key={keyOf(it)} item={it} state="quiet" onPress={() => open(it)}
                    trailing={{ label: 'Still on', icon: 'refresh', tone: 'later', onAction: () => marks.keep(it) }}
                    leading={{ label: 'Not needed', icon: 'close', tone: 'neutralAction', onAction: () => marks.dismiss(it) }} />
      ))}
    </ScrollView>
  )
}
