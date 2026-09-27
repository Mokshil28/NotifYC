import { describe, expect, it, vi } from 'vitest'
import { sendToTestPhone, type PhotonTransport } from './client'

const env = {
  PHOTON_PROJECT_ID: 'project-id',
  PHOTON_PROJECT_SECRET: 'project-secret',
  PHOTON_TEST_PHONE: '+15550001111',
}

describe('sendToTestPhone', () => {
  it('sends only to the configured test phone through the mock transport', async () => {
    const sendText = vi.fn(async () => ({ messageId: 'msg-1' }))
    const transport: PhotonTransport = { sendText }
    const result = await sendToTestPhone('NotifYC Integration Test', { env, transport })
    expect(result).toEqual({ ok: true, messageId: 'msg-1' })
    expect(sendText).toHaveBeenCalledOnce()
    expect(sendText).toHaveBeenCalledWith('+15550001111', 'NotifYC Integration Test')
  })

  it('does not call the transport when the test phone is missing', async () => {
    const sendText = vi.fn(async () => ({ messageId: 'nope' }))
    const result = await sendToTestPhone('hello', {
      env: { ...env, PHOTON_TEST_PHONE: '' },
      transport: { sendText },
    })
    expect(result.ok).toBe(false)
    expect(sendText).not.toHaveBeenCalled()
  })

  it('returns a failure without the project secret when delivery throws', async () => {
    const transport: PhotonTransport = {
      sendText: async () => {
        throw new Error('delivery failed for project-secret')
      },
    }
    const result = await sendToTestPhone('hello', { env, transport })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toContain('[redacted]')
      expect(result.error).not.toContain('project-secret')
    }
  })
})
