/**
 * Send one text through the already running established Photon conversation.
 * Does not open a new chat and does not call ElevenLabs.
 *
 *   node --experimental-strip-types src/integrations/photon/send-established-text.ts
 */

import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mask, requestEstablished, TEST_TEXT } from './established.ts'

async function main(): Promise<void> {
  const response = await requestEstablished({ text: TEST_TEXT })
  if (!response.ok || response.result?.text !== 'SENT') {
    console.log('[Photon] Established text: FAILED')
    console.log(mask(response.errors?.text || response.error || 'Text was not sent.'))
    process.exitCode = 1
    return
  }
  console.log('[Photon] Established text: SENT')
  console.log(TEST_TEXT)
}

const entry = process.argv[1]
if (entry && resolve(entry) === fileURLToPath(import.meta.url)) {
  main().catch((error: unknown) => {
    console.error(`[Photon] ${mask(error instanceof Error ? error.message : 'Text send failed.')}`)
    process.exitCode = 1
  })
}
