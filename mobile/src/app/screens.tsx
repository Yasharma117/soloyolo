// Every screen and state in one list, for testing and handoff. Add new routes here.
import { NavList, Screen, SectionCard } from '@soloyolo/design-system'
import { useRouter, type Href } from 'expo-router'

const GROUPS: { title: string; rows: { label: string; href: Href; value?: string }[] }[] = [
  { title: 'Every day', rows: [
    { label: 'Today', href: '/' }, { label: 'People', href: '/people' }, { label: 'All open', href: '/all' }, { label: 'Sources', href: '/sources' },
  ] },
  { title: 'States (?state=, from Markon’s page-state)', rows: [
    { label: 'Today, loading', href: '/?state=loading' }, { label: 'Today, nothing owed', href: '/?state=empty' }, { label: 'Today, failed to load', href: '/?state=error' },
    { label: 'All open, loading', href: '/all?state=loading' }, { label: 'All open, failed to load', href: '/all?state=error' },
    { label: 'People, loading', href: '/people?state=loading' }, { label: 'People, failed to load', href: '/people?state=error' },
  ] },
  { title: 'A person', rows: [
    { label: 'Person, promises', href: '/person/1', value: 'demo' }, { label: 'Person, with a promise in focus', href: '/person/1?focus=101', value: 'demo' },
    { label: 'Person, waiting on them', href: '/person/3', value: 'demo' },
  ] },
  { title: 'Setup and review', rows: [
    { label: 'Set up, where you are', href: '/welcome' }, { label: 'Set up, nothing done yet', href: '/welcome?state=new' },
    { label: 'Import, starting', href: '/import?at=start', value: 'sample' }, { label: 'Import, halfway', href: '/import?at=half', value: 'sample' }, { label: 'Import, finished', href: '/import?at=end', value: 'sample' },
    { label: 'Same person?', href: '/merges' }, { label: 'Same person?, none', href: '/merges?state=empty' }, { label: 'Same person?, failed to load', href: '/merges?state=error' },
    { label: 'This week', href: '/week' }, { label: 'This week, nothing', href: '/week?state=empty' },
    { label: 'Person, with connections', href: '/person/3', value: 'demo' },
  ] },
  { title: 'Results', rows: [
    { label: 'Import finished', href: '/status?tone=success' }, { label: 'Import failed', href: '/status?tone=error' },
    { label: 'Reading chats', href: '/status?tone=pending' }, { label: 'Telegram not paired', href: '/status?tone=info' },
  ] },
  { title: 'For builders', rows: [{ label: 'Design system', href: '/design' }] },
]

export default function Screens() {
  const router = useRouter()
  return (
    <Screen>
      <Screen.Header title="Every screen" subtitle="Each screen and state in the app, for testing and handoff." onBack={() => (router.canGoBack() ? router.back() : router.replace('/'))} backIcon="chevron-down" />
      <Screen.Body>
        {GROUPS.map((g) => (
          <SectionCard key={g.title} title={g.title}>
            <NavList rows={g.rows.map((r) => ({ label: r.label, value: r.value, onPress: () => router.push(r.href) }))} />
          </SectionCard>
        ))}
      </Screen.Body>
    </Screen>
  )
}
