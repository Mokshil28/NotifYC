/**
 * Local handle for the established inbound Photon conversation.
 * The conversation object lives in conversation-service.ts.
 * Other commands reach it through 127.0.0.1. They never call space.create.
 */

import { existsSync, readFileSync } from 'node:fs'
import { connect } from 'node:net'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const TEST_TEXT = 'NotifYC established-conversation delivery test.'

export type EstablishedState = {
  port: number
  ready: boolean
}

export type EstablishedRequest = {
  text?: string
  audioPath?: string
  videoPath?: string
}

export type EstablishedResponse = {
  ok: boolean
  result?: Record<string, string>
  errors?: Record<string, string>
  error?: string
}

export function statePath(): string {
  return join(dirname(fileURLToPath(import.meta.url)), '../../../.photon-conversation.json')
}

export function devVarsPath(): string {
  return join(dirname(fileURLToPath(import.meta.url)), '../../../.dev.vars')
}

export function loadDevVars(): void {
  const path = devVarsPath()
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

export function mask(text: string, secret = ''): string {
  let next = text.replace(/\+\d{6,}/g, '+[redacted]')
  if (secret) next = next.split(secret).join('[redacted]')
  const eleven = process.env.ELEVENLABS_API_KEY?.trim()
  if (eleven) next = next.split(eleven).join('[redacted]')
  return next
}

export function readState(): EstablishedState | null {
  const path = statePath()
  if (!existsSync(path)) return null
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8')) as EstablishedState
    if (!parsed || typeof parsed.port !== 'number') return null
    return { port: parsed.port, ready: parsed.ready === true }
  } catch {
    return null
  }
}

export function requestEstablished(payload: EstablishedRequest): Promise<EstablishedResponse> {
  const state = readState()
  if (!state) {
    return Promise.resolve({
      ok: false,
      error: 'Photon conversation service is not running.',
    })
  }
  if (!state.ready && !payload.text && !payload.audioPath && !payload.videoPath) {
    return Promise.resolve({
      ok: false,
      error: 'Authorized Photon conversation is not ready.',
    })
  }
  return new Promise((resolve) => {
    const socket = connect({ host: '127.0.0.1', port: state.port })
    const chunks: Buffer[] = []
    let settled = false
    const finish = (response: EstablishedResponse) => {
      if (settled) return
      settled = true
      socket.destroy()
      resolve(response)
    }
    socket.setTimeout(20000, () => {
      finish({ ok: false, error: 'Photon conversation service did not respond.' })
    })
    socket.on('connect', () => {
      socket.end(`${JSON.stringify(payload)}\n`)
    })
    socket.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
    socket.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8').trim()
      try {
        finish(JSON.parse(raw) as EstablishedResponse)
      } catch {
        finish({ ok: false, error: raw ? mask(raw) : 'Photon conversation service returned no result.' })
      }
    })
    socket.on('error', (error) => {
      finish({ ok: false, error: mask(error.message) })
    })
  })
}
