/**
 * Operational response priority from observable CV metrics only.
 * This is not medical severity, injury, fault, or danger.
 */

import type { IncidentPriority } from './demo-data'

export type PriorityDecision = {
  priority: IncidentPriority
  label: string
  reasons: string[]
}

const ORDER: Record<IncidentPriority, number> = { high: 0, normal: 1, low: 2 }

export function priorityLabel(priority: IncidentPriority): string {
  if (priority === 'high') return 'P1 — High'
  if (priority === 'normal') return 'P2 — Medium'
  return 'P3 — Standard'
}

function numberMetric(metrics: Record<string, number | boolean | null>, key: string): number | null {
  const value = metrics[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function flagMetric(metrics: Record<string, number | boolean | null>, key: string): boolean {
  return metrics[key] === true
}

/**
 * High needs at least two strong observable signals.
 * Medium needs one strong signal or two milder ones.
 * Otherwise the surfaced incident stays standard.
 */
export function operationalPriority(
  metrics: Record<string, number | boolean | null>,
  involvedTrackCount = 0,
): PriorityDecision {
  const strong: string[] = []
  const mild: string[] = []
  const score = numberMetric(metrics, 'collisionEvidenceScore')
  const closing = numberMetric(metrics, 'closing_speed_px_s')
  const iou = numberMetric(metrics, 'bbox_iou_at_interaction')
  const reduction = numberMetric(metrics, 'separation_reduction')

  if (score !== null && score >= 60) strong.push(`evidence score ${score} out of 100`)
  else if (score !== null && score >= 40) mild.push(`evidence score ${score} out of 100`)
  if (flagMetric(metrics, 'vehicle_rollover')) {
    strong.push('a tracked vehicle flipped over')
    strong.push('rollover is the first location sent to the simulated police notification')
  }
  if (flagMetric(metrics, 'wall_impact')) {
    mild.push('a tracked vehicle collided with a wall')
  }
  if (flagMetric(metrics, 'synchronized_response')) {
    strong.push('both tracked vehicles showed a motion response in the same window')
  }
  if (flagMetric(metrics, 'abrupt_geometry_change')) {
    strong.push('abrupt change in vehicle-box geometry during the interaction')
  }
  if (iou !== null && iou >= 0.08) strong.push(`vehicle boxes overlap in the image (IoU ${iou})`)
  if (closing !== null && closing >= 200) strong.push(`closing speed ${closing} px/s`)
  else if (closing !== null && closing >= 40) mild.push(`closing speed ${closing} px/s`)
  if (flagMetric(metrics, 'projected_path_convergence')) {
    mild.push('recent motion projects the paths toward the same image region')
  }
  if (reduction !== null && reduction >= 30) mild.push(`separation decreased by ${reduction} px before the interaction`)
  if (involvedTrackCount >= 2) mild.push(`${involvedTrackCount} tracked vehicles are listed on the event`)

  if (strong.length >= 2) {
    return { priority: 'high', label: priorityLabel('high'), reasons: strong }
  }
  if (strong.length === 1 || mild.length >= 2) {
    return { priority: 'normal', label: priorityLabel('normal'), reasons: [...strong, ...mild] }
  }
  const reasons = [...strong, ...mild]
  if (reasons.length === 0) {
    reasons.push('the state machine surfaced the event, without additional strong motion signals')
  }
  return { priority: 'low', label: priorityLabel('low'), reasons }
}

export function compareOperational<T extends { priority: IncidentPriority; detectedAt: string }>(left: T, right: T): number {
  const rank = ORDER[left.priority] - ORDER[right.priority]
  if (rank !== 0) return rank
  return left.detectedAt.localeCompare(right.detectedAt)
}
