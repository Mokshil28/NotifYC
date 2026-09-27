/**
 * Temporary inbound Photon check. Run this yourself.
 * Does not send the outbound test and does not read a phone number from code.
 */

import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Spectrum } from 'spectrum-ts'
import { imessage } from 'spectrum-ts/providers/imessage'

const REPLY = 'NotifYC Photon connection successful.'

function loadDevVars(): void {
  const path = join(dirname(fileURLToPath(import.meta.url)), '../../../.dev.vars')
  if (!existsSync(path)) return
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const splitAt = trimmed.indexOf('=')
    if (splitAt < 1) continue
    const key = trimmed.slice(0, splitAt).trim()
    const value = trimmed.slice(splitAt + 1).trim().replace(/^["']|["']$/g, '')
    if (process.env[key] === undefined) process.env[key] = value
  }
}

function required(name: 'PHOTON_PROJECT_ID' | 'PHOTON_PROJECT_SECRET'): string {
  const value = process.env[name]?.trim()
  if (!value) throw new Error(`${name} is not set.`)
  return value
}

async function main(): Promise<void> {
  loadDevVars()
  const projectId = required('PHOTON_PROJECT_ID')
  const projectSecret = required('PHOTON_PROJECT_SECRET')
  const app = await Spectrum({
    projectId,
    projectSecret,
    providers: [imessage.config()],
  })

  let stopping = false
  const shutdown = async () => {
    if (stopping) return
    stopping = true
    console.log('[Photon] Shutting down.')
    await app.stop().catch(() => undefined)
  }
  process.once('SIGINT', () => {
    void shutdown()
  })
  process.once('SIGTERM', () => {
    void shutdown()
  })

  console.log('[Photon] Listening for an inbound iMessage. Ctrl+C to stop.')
  try {
    for await (const [space, message] of app.messages) {
      if (stopping) break
      if (message.platform !== 'imessage' || message.direction !== 'inbound') continue
      console.log('[Photon] Inbound iMessage received.')
      try {
        await space.send(REPLY)
        console.log('[Photon] Reply sent in the same conversation.')
      } catch (error) {
        const text = error instanceof Error ? error.message : 'Reply failed.'
        console.error(`[Photon] Reply failed. ${text.split(projectSecret).join('[redacted]')}`)
      }
    }
  } catch (error) {
    if (!stopping) {
      const text = error instanceof Error ? error.message : 'Listener failed.'
      console.error(`[Photon] Listener stopped. ${text.split(projectSecret).join('[redacted]')}`)
      process.exitCode = 1
    }
  } finally {
    await shutdown()
  }
}

const entry = process.argv[1]
if (entry && resolve(entry) === fileURLToPath(import.meta.url)) {
  main().catch((error: unknown) => {
    const text = error instanceof Error ? error.message : 'Inbound test failed.'
    console.error(`[Photon] ${text}`)
    process.exitCode = 1
  })
}
