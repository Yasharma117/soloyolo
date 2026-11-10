import { View } from 'react-native'
import { Button } from '../components/Button/Button'
import { Icon, type IconName } from '../components/Icon/Icon'
import { Row } from '../components/Stack/Stack'
import { Surface } from '../components/Surface/Surface'
import { Text } from '../components/Text/Text'
import { useTheme } from '../theme'

/** done: finished, shown small with what it gave you. now: the one to do, open. later: waiting its turn. */
export type StepState = 'done' | 'now' | 'later'

/**
 * One step of first run: link WhatsApp, pair Telegram, import an export. Only the step you're on is open, with
 * what it does for you, how to do it (`how`: the line to run on your Mac, selectable) and at most one action.
 * A done step says what it brought in ("5,602 messages"), not "Completed".
 */
export function OnboardingStep({ n, icon, title, body, state, how, doneNote, action }: {
  n: number; icon: IconName; title: string; body: string; state: StepState; how?: string; doneNote?: string
  action?: { label: string; onPress: () => void }
}) {
  const t = useTheme()
  const now = state === 'now'
  const mark = state === 'done' ? t.color.success : now ? t.color.inverse : 'transparent'
  return (
    <View style={{ marginHorizontal: t.space.lg }}>
      <Surface variant={now ? 'card' : 'outline'} style={{ gap: t.space.md, opacity: state === 'later' ? 0.6 : 1 }}>
        <Row gap="md">
          <View accessibilityLabel={state === 'done' ? 'Done' : `Step ${n}`}
                style={{ width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: mark,
                         borderWidth: state === 'later' ? 1 : 0, borderColor: t.color.border }}>
            {state === 'done' ? <Icon name="checkmark" size="md" tone="onColor" />
              : <Text variant="small" tone={now ? 'inverse' : 'tertiary'} style={{ fontWeight: '700' }}>{n}</Text>}
          </View>
          <Text variant="sentenceSmall" style={{ flex: 1, fontSize: now ? 20 : 17, lineHeight: now ? 26 : 22 }}>{title}</Text>
          <Icon name={icon} size="lg" tone={state === 'done' ? 'success' : 'tertiary'} />
        </Row>
        {state === 'done' && doneNote ? <Text variant="small" tone="success" style={{ fontWeight: '600' }}>{doneNote}</Text> : null}
        {state !== 'done' ? <Text variant={now ? 'body' : 'small'} tone="secondary" numberOfLines={now ? undefined : 2}>{body}</Text> : null}
        {now && how ? (
          <View style={{ backgroundColor: t.color.surfaceRaised, borderRadius: t.radius.md, paddingHorizontal: t.space.md, paddingVertical: t.space.sm + 2, gap: 2 }}>
            <Text variant="label" tone="tertiary" upper>On your Mac</Text>
            <Text variant="small" selectable style={{ fontWeight: '600' }}>{how}</Text>
          </View>
        ) : null}
        {now && action ? <Button label={action.label} variant="primary" onPress={action.onPress} /> : null}
      </Surface>
    </View>
  )
}
