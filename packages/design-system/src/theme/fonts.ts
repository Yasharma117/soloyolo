import { Newsreader_400Regular, Newsreader_500Medium, useFonts } from '@expo-google-fonts/newsreader'

/** Loads the bundled serif. Call once at the root and render nothing until it's true, so no headline flashes in
 *  a fallback face. True on a load error too: the system serif is better than a blank app. */
export function useDesignFonts(): boolean {
  const [loaded, error] = useFonts({ Newsreader_400Regular, Newsreader_500Medium })
  return loaded || !!error
}
