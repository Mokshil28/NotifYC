import { describe, expect, it } from 'vitest'
import { briefingIsSendable, formatPhotonBriefing, type PhotonBriefingInput } from './format-briefing'

function input(overrides: Partial<PhotonBriefingInput> = {}): PhotonBriefingInput {
  return {
    cameraId: 'CAM-004',
    briefing: {
      summary: 'Possible vehicle collision surfaced at CAM-004.',
      observations: ['Track ids were supplied.'],
      limitations: 'Visual evidence was referenced and should be reviewed.',
      source: 'grok',
    },
    ...overrides,
  }
}

describe('formatPhotonBriefing', () => {
  it('keeps the message short and omits missing priority and responder', () => {
    const text = formatPhotonBriefing(input())
    expect(text).toBe(
      [
        'NotifYC — Possible Collision',
        'CAM-004',
        '',
        'Possible vehicle collision surfaced at CAM-004.',
        '',
        'Review visual evidence in NotifYC.',
      ].join('\n'),
    )
    expect(text).not.toMatch(/px\/s|IoU|normalized/i)
  })

  it('includes priority and responder only when supplied', () => {
    const text = formatPhotonBriefing(input({ priority: 'normal', responder: 'UNIT-12' }))
    expect(text).toContain('Operational priority: normal')
    expect(text).toContain('Simulated responder: UNIT-12')
  })

  it('refuses an unvalidated briefing', () => {
    expect(briefingIsSendable(input({
      briefing: {
        summary: 'Confirmed crash with injuries. EMS dispatched.',
        observations: [],
        limitations: '',
        source: 'grok',
      },
    }).briefing)).toBe(false)
  })
})
