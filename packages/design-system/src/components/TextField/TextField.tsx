import { useState } from 'react'
import { TextInput, View, type TextInputProps } from 'react-native'
import { useTheme } from '../../theme'
import { Text } from '../Text/Text'

export type TextFieldProps = Pick<TextInputProps, 'value' | 'onChangeText' | 'placeholder' | 'autoFocus' | 'keyboardType' | 'returnKeyType'
  | 'onSubmitEditing' | 'autoCapitalize' | 'maxLength' | 'multiline' | 'secureTextEntry' | 'autoComplete'> & {
  /** Sentence case, a noun: "Note", "Name". Also what a screen reader says. */
  label: string
  /** One line under the field: "Only you see notes." Replaced by the error when there is one. */
  hint?: string
  /** Name the problem and the next step: "Add a name, or go back." */
  error?: string
}

/** Type a few words or a note. Paper-white on the page, a firm edge while you type. Multiline grows to a note's size. */
export function TextField({ label, hint, error, multiline, maxLength, value, ...rest }: TextFieldProps) {
  const t = useTheme()
  const [focused, setFocused] = useState(false)
  const edge = error ? t.color.danger : focused ? t.color.textPrimary : t.color.border
  return (
    <View style={{ gap: t.space.xs + 2 }}>
      <Text variant="small" tone="secondary" style={{ fontWeight: '600', paddingHorizontal: t.space.xs }}>{label}</Text>
      <TextInput value={value} multiline={multiline} maxLength={maxLength} accessibilityLabel={label}
                 placeholderTextColor={t.color.textTertiary} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
                 textAlignVertical={multiline ? 'top' : 'center'} {...rest}
                 style={{ minHeight: multiline ? 104 : 48, paddingHorizontal: t.space.md + 2, paddingTop: multiline ? t.space.md : 0, paddingBottom: multiline ? t.space.md : 0,
                          borderRadius: t.radius.lg, borderWidth: focused || error ? 1 : 0.5, borderColor: edge, backgroundColor: t.color.surface,
                          color: t.color.textPrimary, fontSize: 16, lineHeight: multiline ? 22 : undefined }} />
      {error || hint || (multiline && maxLength) ? (
        <View style={{ flexDirection: 'row', gap: t.space.md, paddingHorizontal: t.space.xs }}>
          <Text variant="caption" tone={error ? 'danger' : 'tertiary'} style={{ flex: 1 }}>{error ?? hint ?? ''}</Text>
          {multiline && maxLength ? <Text variant="caption" tone="tertiary">{`${value?.length ?? 0}/${maxLength}`}</Text> : null}
        </View>
      ) : null}
    </View>
  )
}
