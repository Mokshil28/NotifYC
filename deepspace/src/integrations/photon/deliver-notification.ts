/**
 * Ask the running conversation service to send on the established inbound chat.
 * stdin JSON: { text, audioPath?, videoPath? }
 * Does not call space.create.
 */

import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mask, requestEstablished, type EstablishedRequest } from './established.ts'

async function main(): Promise<void> {
  const raw = await new Promise<string>((done, reject) => {
    const chunks: Buffer[] = []
    process.stdin.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
    process.stdin.on('end', () => done(Buffer.concat(chunks).toString('utf8')))
    process.stdin.on('error', reject)
  })
  const payload = JSON.parse(raw) as EstablishedRequest
  const response = await requestEstablished(payload)
  console.log(JSON.stringify(response))
  if (!response.ok) process.exitCode = 1
}

const entry = process.argv[1]
if (entry && resolve(entry) === fileURLToPath(import.meta.url)) {
  main().catch((error: unknown) => {
    const message = mask(error instanceof Error ? error.message : 'Photon delivery failed.')
    console.log(JSON.stringify({ ok: false, error: message }))
    process.exitCode = 1
  })
}
