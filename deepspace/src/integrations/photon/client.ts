/**
 * Standalone Photon Spectrum client.
 * Sends only to PHOTON_TEST_PHONE. Does not read incidents or choose recipients.
 */

import { Spectrum } from 'spectrum-ts'
import { imessage } from 'spectrum-ts/providers/imessage'

export type PhotonSendResult =
  | { ok: true; messageId: string | null }
  | { ok: false; error: string }

export type PhotonEnv = {
  PHOTON_PROJECT_ID?: string
  PHOTON_PROJECT_SECRET?: string
  PHOTON_TEST_PHONE?: string
}

export type PhotonTransport = {
  sendText: (phone: string, text: string) => Promise<{ messageId?: string }>
  stop?: () => Promise<void>
}

function missing(name: string): PhotonSendResult {
  return { ok: false, error: `${name} is not set.` }
}

function redact(error: unknown, secret: string): string {
  const message = error instanceof Error ? error.message : 'Photon send failed.'
  if (!secret) return message
  return message.split(secret).join('[redacted]')
}

/** Cloud iMessage via Spectrum 12: resolve the user, open a DM, then space.send. */
export async function openSpectrumTransport(projectId: string, projectSecret: string): Promise<PhotonTransport> {
  const app = await Spectrum({
    projectId,
    projectSecret,
    providers: [imessage.config()],
  })
  const messages = imessage(app)
  return {
    async sendText(phone, text) {
      const user = await messages.user(phone)
      const space = await messages.space.create(user)
      const sent = await space.send(text)
      return { messageId: sent?.id }
    },
    stop: () => app.stop(),
  }
}

export async function sendToTestPhone(
  text: string,
  options: { env?: PhotonEnv; transport?: PhotonTransport } = {},
): Promise<PhotonSendResult> {
  const env = options.env ?? process.env
  const projectId = env.PHOTON_PROJECT_ID?.trim() ?? ''
  const projectSecret = env.PHOTON_PROJECT_SECRET?.trim() ?? ''
  const phone = env.PHOTON_TEST_PHONE?.trim() ?? ''
  if (!projectId) return missing('PHOTON_PROJECT_ID')
  if (!projectSecret) return missing('PHOTON_PROJECT_SECRET')
  if (!phone.startsWith('+') || phone.length < 8) return missing('PHOTON_TEST_PHONE')
  if (!text.trim()) return { ok: false, error: 'Message text is empty.' }

  let transport = options.transport
  let opened = false
  try {
    if (!transport) {
      transport = await openSpectrumTransport(projectId, projectSecret)
      opened = true
    }
    const sent = await transport.sendText(phone, text)
    return { ok: true, messageId: sent.messageId ?? null }
  } catch (error) {
    return { ok: false, error: redact(error, projectSecret) }
  } finally {
    if (opened) await transport?.stop?.().catch(() => undefined)
  }
}
