/**
 * Formats details NotifYC has already decided. Does not detect collisions,
 * rank incidents, or assign responders.
 */

export type NotifycAlertCopy = {
  cameraId: string
  locationName: string
  eventTime: string
  operationalPriorityLabel: string
  priorityReasons: string[]
  involvedTracks: string[]
  evidenceWindow: string
  observableSummary: string
  responderLabel: string
}

export function formatAlert(alert: NotifycAlertCopy): string {
  const reasons = alert.priorityReasons.length > 0
    ? alert.priorityReasons.map((reason) => `- ${reason}`).join('\n')
    : '- No extra observable reasons were stored.'
  const tracks = alert.involvedTracks.length > 0 ? alert.involvedTracks.join(', ') : 'none recorded'
  return [
    'NotifYC',
    'Demo environment. Simulated responders only.',
    '',
    'Possible collision',
    'Suspected traffic incident',
    '',
    `Camera: ${alert.cameraId}`,
    `Location: ${alert.locationName}`,
    `Event time: ${alert.eventTime}`,
    `Operational response priority: ${alert.operationalPriorityLabel}`,
    'Why this priority:',
    reasons,
    `Involved tracks: ${tracks}`,
    `Visual evidence window: ${alert.evidenceWindow}`,
    `Observable evidence: ${alert.observableSummary}`,
    `Simulated responder: ${alert.responderLabel}`,
  ].join('\n')
}
