// https://docs.expo.dev/guides/using-eslint/
// Design gates (the same idea as Ema's adherence rules): screens are built from
// @soloyolo/design-system, so the look can't drift screen by screen. These are errors, so CI fails.
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

const USE_DS = 'Use @soloyolo/design-system instead (Text, Button, IconButton, SearchField, Icon, Avatar, SwipeRow...).';

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', 'scripts/*'],
  },
  {
    files: ['src/app/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': ['error', {
        paths: [
          { name: 'react-native', importNames: ['Text', 'TextInput', 'Pressable', 'TouchableOpacity', 'TouchableHighlight', 'Button', 'Switch'], message: USE_DS },
          { name: '@expo/vector-icons', message: 'Use <Icon> from @soloyolo/design-system (its icon set is the allow-list).' },
          { name: '@expo/vector-icons/Ionicons', message: 'Use <Icon> from @soloyolo/design-system (its icon set is the allow-list).' },
          { name: 'expo-linear-gradient', message: 'Gradients belong to the design system (Avatar, DotGrid).' },
          { name: 'react-native-gesture-handler/ReanimatedSwipeable', message: 'Use <SwipeRow> from @soloyolo/design-system.' },
        ],
        patterns: [{ group: ['@soloyolo/design-system/*'], message: 'Import from @soloyolo/design-system itself, never from inside it.' }],
      }],
      'no-restricted-syntax': ['error',
        { selector: 'Literal[value=/^#[0-9a-fA-F]{3,8}$/]', message: 'Raw hex color. Use a theme token: useTheme().color.*' },
        { selector: 'Literal[value=/^rgba?\\(/]', message: 'Raw color. Use a theme token: useTheme().color.*' },
        { selector: 'Property[key.name="fontFamily"]', message: 'Fonts come from <Text variant>. The serif is the sentence variants.' },
      ],
    },
  },
]);
