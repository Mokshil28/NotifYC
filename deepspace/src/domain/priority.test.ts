import { describe, expect, it } from 'vitest'
import { compareOperational, operationalPriority } from './priority'

describe('operationalPriority', () => {
  it('uses only supplied observable metrics', () => {
    const decision = operationalPriority({
      collisionEvidenceScore: 70,
      synchronized_response: true,
      closing_speed_px_s: 210,
    }, 2)
    expect(decision.priority).toBe('high')
    expect(decision.label).toBe('P1 — High')
    expect(decision.reasons.join(' ')).toContain('evidence score 70')
    expect(decision.reasons.join(' ')).not.toMatch(/injur|fatal|fault|danger/i)
  })

  it('stays standard when the only fact is that an event surfaced', () => {
    const decision = operationalPriority({}, 0)
    expect(decision.priority).toBe('low')
    expect(decision.label).toBe('P3 — Standard')
  })

  it('sorts high before medium before standard, then by event time', () => {
    const rows = [
      { priority: 'low' as const, detectedAt: '1970-01-01T00:00:01.000Z', id: 'late-standard' },
      { priority: 'high' as const, detectedAt: '1970-01-01T00:00:09.000Z', id: 'high' },
      { priority: 'normal' as const, detectedAt: '1970-01-01T00:00:02.000Z', id: 'medium-early' },
      { priority: 'normal' as const, detectedAt: '1970-01-01T00:00:08.000Z', id: 'medium-late' },
    ]
    expect(rows.sort(compareOperational).map((row) => row.id)).toEqual([
      'high',
      'medium-early',
      'medium-late',
      'late-standard',
    ])
  })
})
