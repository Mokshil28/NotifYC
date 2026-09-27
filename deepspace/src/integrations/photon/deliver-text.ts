/**
 * Deliver one already formatted text to the authorized test conversation.
 * stdin: { "text": "...", "source": "grok" | "fallback" }
 */

import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mask, requestEstablished } from './established.ts'
import { briefingIsSendable, formatPhotonBriefing, type BriefingContract } from './format-briefing.ts'

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

async function main(): Promise<void> {
  loadDevVars()
  const raw = await new Promise<string>((resolveText, reject) => {
    const chunks: Buffer[] = []
    process.stdin.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
    process.stdin.on('end', () => resolveText(Buffer.concat(chunks).toString('utf8')))
    process.stdin.on('error', reject)
  })
  const payload = JSON.parse(raw) as {
    cameraId?: string
    priority?: string
    responder?: string
    briefing?: BriefingContract
  }
  const briefing = payload.briefing
  if (!briefing || !payload.cameraId || !briefingIsSendable(briefing)) {
    console.log(JSON.stringify({ ok: false, error: 'Briefing did not pass validation. Nothing sent.' }))
    process.exitCode = 1
    return
  }
  const text = formatPhotonBriefing({
    cameraId: payload.cameraId,
    priority: payload.priority,
    responder: payload.responder,
    briefing,
  })
  const result = await requestEstablished({ text })
  if (!result.ok || result.result?.text !== 'SENT') {
    console.log(JSON.stringify({ ok: false, error: mask(result.errors?.text || result.error || 'Text was not sent.'), text, source: briefing.source }))
    process.exitCode = 1
    return
  }
  console.log(JSON.stringify({ ok: true, text, source: briefing.source }))
}

const entry = process.argv[1]
if (entry && resolve(entry) === fileURLToPath(import.meta.url)) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : 'Photon delivery failed.'
    console.log(JSON.stringify({ ok: false, error: mask(message) }))
    process.exitCode = 1
  })
}
