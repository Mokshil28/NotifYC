/**
 * One local process holds the inbound Photon conversation and later sends on it.
 *
 *   node --experimental-strip-types src/integrations/photon/conversation-service.ts
 *
 * Text the Photon number once, then keep this process running.
 * Does not call imessage.user() or space.create().
 */

import { existsSync, writeFileSync } from 'node:fs'
import { createServer, type Socket } from 'node:net'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Spectrum, attachment, type ContentInput } from 'spectrum-ts'
import { imessage } from 'spectrum-ts/providers/imessage'
import {
  loadDevVars,
  mask,
  statePath,
  type EstablishedRequest,
  type EstablishedResponse,
} from './established.ts'

type RetainedSpace = {
  send: (content: ContentInput) => Promise<unknown>
}

function required(name: 'PHOTON_PROJECT_ID' | 'PHOTON_PROJECT_SECRET'): string {
  const value = process.env[name]?.trim()
  if (!value) throw new Error(`${name} is not set.`)
  return value
}

function writeState(port: number, ready: boolean): void {
  writeFileSync(statePath(), `${JSON.stringify({ port, ready })}\n`)
}

async function deliver(space: RetainedSpace, payload: EstablishedRequest, secret: string): Promise<EstablishedResponse> {
  const result: Record<string, string> = { audio: 'SKIPPED', text: 'SKIPPED', video: 'SKIPPED' }
  const errors: Record<string, string> = {}
  const text = payload.text?.trim() ?? ''
  if (payload.audioPath) {
    if (!existsSync(payload.audioPath)) {
      result.audio = 'FAILED'
      errors.audio = 'Audio file was not found.'
    } else {
      try {
        await space.send(attachment(payload.audioPath, { mimeType: 'audio/mpeg', name: 'notifyc-briefing.mp3' }))
        result.audio = 'SENT'
      } catch (error) {
        result.audio = 'FAILED'
        errors.audio = mask(error instanceof Error ? error.message : 'Audio send failed.', secret)
      }
    }
  }
  if (text) {
    try {
      await space.send(text)
      result.text = 'SENT'
    } catch (error) {
      result.text = 'FAILED'
      errors.text = mask(error instanceof Error ? error.message : 'Text send failed.', secret)
    }
  }
  if (payload.videoPath) {
    if (!existsSync(payload.videoPath)) {
      result.video = 'FAILED'
      errors.video = 'Evidence video was not found.'
    } else {
      try {
        await space.send(attachment(payload.videoPath, { mimeType: 'video/mp4', name: 'notifyc-evidence.mp4' }))
        result.video = 'SENT'
      } catch (error) {
        result.video = 'FAILED'
        errors.video = mask(error instanceof Error ? error.message : 'Video send failed.', secret)
      }
    }
  }
  const ok = result.audio !== 'FAILED' && result.text !== 'FAILED' && result.video !== 'FAILED'
  return { ok, result, errors }
}

function handleConnection(socket: Socket, current: () => RetainedSpace | null, secret: string): void {
  let raw = ''
  socket.setEncoding('utf8')
  socket.on('data', (chunk) => {
    raw += chunk
  })
  socket.on('end', () => {
    void (async () => {
      let response: EstablishedResponse
      try {
        const payload = JSON.parse(raw) as EstablishedRequest
        const space = current()
        if (!space) {
          response = { ok: false, error: 'Authorized Photon conversation is not ready.' }
        } else if (!payload.text?.trim() && !payload.audioPath && !payload.videoPath) {
          response = { ok: false, error: 'Nothing to send.' }
        } else {
          response = await deliver(space, payload, secret)
        }
      } catch (error) {
        response = { ok: false, error: mask(error instanceof Error ? error.message : 'Photon delivery failed.', secret) }
      }
      socket.end(`${JSON.stringify(response)}\n`)
    })()
  })
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
  let space: RetainedSpace | null = null
  let announced = false
  let stopping = false

  const server = createServer((socket) => {
    handleConnection(socket, () => space, projectSecret)
  })
  await new Promise<void>((done, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => done())
  })
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Photon conversation service could not listen.')
  writeState(address.port, false)

  const shutdown = async () => {
    if (stopping) return
    stopping = true
    console.log('[Photon] Shutting down.')
    writeState(address.port, false)
    server.close()
    await app.stop().catch(() => undefined)
  }
  process.once('SIGINT', () => {
    void shutdown()
  })
  process.once('SIGTERM', () => {
    void shutdown()
  })

  console.log('[Photon] Listening for an inbound iMessage. Keep this process running.')
  try {
    for await (const [incoming, message] of app.messages) {
      if (stopping) break
      if (message.platform !== 'imessage' || message.direction !== 'inbound') continue
      space = incoming
      writeState(address.port, true)
      console.log('[Photon] Inbound iMessage received.')
      if (!announced) {
        announced = true
        console.log('[Photon] Authorized Photon conversation: READY')
      }
    }
  } catch (error) {
    if (!stopping) {
      console.error(`[Photon] Listener stopped. ${mask(error instanceof Error ? error.message : 'Listener failed.', projectSecret)}`)
      process.exitCode = 1
    }
  } finally {
    await shutdown()
  }
}

const entry = process.argv[1]
if (entry && resolve(entry) === fileURLToPath(import.meta.url)) {
  main().catch((error: unknown) => {
    console.error(`[Photon] ${mask(error instanceof Error ? error.message : 'Conversation service failed.')}`)
    process.exitCode = 1
  })
}
