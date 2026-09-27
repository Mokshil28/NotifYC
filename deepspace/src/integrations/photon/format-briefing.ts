/**
 * Short iMessage text from an already validated briefing.
 * Does not detect collisions, rank incidents, or assign responders.
 */

export type BriefingContract = {
  summary: string
  observations: string[]
  limitations: string
  source: 'grok' | 'fallback'
}

export type PhotonBriefingInput = {
  cameraId: string
  eventTimestamp?: string | number
  priority?: string
  responder?: string
  briefing: BriefingContract
}

const BLOCKED = [
  'confirmed crash',
  'confirmed collision',
  'injured',
  'injury',
  'fatal',
  'fatality',
  'at fault',
  'medical severity',
  'people trapped',
  'dispatched',
  '911',
  'nypd',
  'ems',
]

export function briefingIsSendable(briefing: BriefingContract): boolean {
  if (briefing.source !== 'grok' && briefing.source !== 'fallback') return false
  if (!briefing.summary.trim()) return false
  const text = [briefing.summary, briefing.limitations, ...briefing.observations].join(' ').toLowerCase()
  return !BLOCKED.some((phrase) => text.includes(phrase))
}

export function formatPhotonBriefing(input: PhotonBriefingInput): string {
  const lines = [
    'NotifYC — Possible Collision',
    input.cameraId,
    '',
    input.briefing.summary.trim(),
    '',
    'Review visual evidence in NotifYC.',
  ]
  if (input.priority && input.priority.trim()) {
    lines.push('', `Operational priority: ${input.priority.trim()}`)
  }
  if (input.responder && input.responder.trim()) {
    lines.push(`Simulated responder: ${input.responder.trim()}`)
  }
  return lines.join('\n')
}
