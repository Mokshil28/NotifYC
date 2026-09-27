/**
 * Manual Photon check. Run this yourself. Automated tests do not import it.
 *
 * Sends only the integration-test text, and only to PHOTON_TEST_PHONE.
 */

import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { sendToTestPhone } from './client.ts'

const TEST_TEXT = [
  'NotifYC Integration Test',
  '',
  'Photon Spectrum connection successful.',
  '',
  'This is a simulated traffic incident notification from the NotifYC demo environment.',
].join('\n')

function loadDevVars(): void {
  const path = join(dirname(fileURLToPath(import.meta.url)), '../../../.dev.vars')
  if (!existsSync(path)) return
  const lines = readFileSync(path, 'utf8').split('\n')
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const splitAt = trimmed.indexOf('=')
    if (splitAt < 1) continue
    const key = trimmed.slice(0, splitAt).trim()
    const value = trimmed.slice(splitAt + 1).trim().replace(/^["']|["']$/g, '')
    if (process.env[key] === undefined) process.env[key] = value
  }
}

async function main(): Promise<void> {
  loadDevVars()
  const result = await sendToTestPhone(TEST_TEXT)
  if (!result.ok) {
    console.error(`[Photon] Not sent. ${result.error}`)
    process.exitCode = 1
    return
  }
  console.log(`[Photon] Test message sent. id=${result.messageId ?? 'none'}`)
}

const entry = process.argv[1]
if (entry && resolve(entry) === fileURLToPath(import.meta.url)) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : 'Photon test failed.'
    console.error(`[Photon] Not sent. ${message}`)
    process.exitCode = 1
  })
}
