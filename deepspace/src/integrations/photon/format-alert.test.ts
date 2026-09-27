import { describe, expect, it } from 'vitest'
import { formatAlert } from './format-alert'

describe('formatAlert', () => {
  it('uses demo wording and the supplied details', () => {
    const text = formatAlert({
      cameraId: 'CAM-004',
      locationName: 'Washington Square',
      eventTime: '2.400s into clip',
      operationalPriorityLabel: 'P2 — Medium',
      priorityReasons: ['closing speed 80 px/s'],
      involvedTracks: ['9', '12'],
      evidenceWindow: '2.0s–2.4s',
      observableSummary: 'closing_speed_px_s=80',
      responderLabel: 'UNIT-27',
    })
    expect(text).toContain('Possible collision')
    expect(text).toContain('Suspected traffic incident')
    expect(text).toContain('Operational response priority: P2 — Medium')
    expect(text).toContain('closing speed 80 px/s')
    expect(text).toContain('Simulated responder: UNIT-27')
    expect(text).toContain('Demo environment')
    expect(text.toLowerCase()).not.toMatch(/injur|fatal|fault|911|nypd|ems dispatched|confirmed crash/)
  })
})
