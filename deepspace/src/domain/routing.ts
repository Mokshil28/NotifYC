/**
 * Simulated responder routing.
 *
 * Distance is geographic only, using the haversine formula. It picks the
 * nearest unit whose status is exactly "available". It is not emergency
 * dispatch and it does not call a model.
 */

const EARTH_RADIUS_KM = 6371

export type RoutePoint = {
  latitude: number
  longitude: number
}

export type RoutableResponder = RoutePoint & {
  responderId: string
  status: string
}

export type RankedResponder = {
  responder: RoutableResponder
  distanceKm: number
}

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180
}

export function haversineKm(from: RoutePoint, to: RoutePoint): number {
  const latitudeDelta = toRadians(to.latitude - from.latitude)
  const longitudeDelta = toRadians(to.longitude - from.longitude)
  const fromLatitude = toRadians(from.latitude)
  const toLatitude = toRadians(to.latitude)
  const arc =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(fromLatitude) * Math.cos(toLatitude) * Math.sin(longitudeDelta / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(arc)))
}

export function formatKm(distanceKm: number): string {
  return `${distanceKm.toFixed(2)} km`
}

/**
 * Available units only, nearest first.
 * Equal distances break ties by responder id, ascending, so the same inputs
 * always return the same order.
 */
export function rankAvailableResponders(
  incident: RoutePoint,
  responders: readonly RoutableResponder[],
): RankedResponder[] {
  return responders
    .filter((responder) => responder.status === 'available')
    .map((responder) => ({
      responder,
      distanceKm: haversineKm(incident, responder),
    }))
    .sort((left, right) => {
      if (left.distanceKm !== right.distanceKm) return left.distanceKm - right.distanceKm
      return left.responder.responderId.localeCompare(right.responder.responderId)
    })
}

export function selectNearestAvailable(
  incident: RoutePoint,
  responders: readonly RoutableResponder[],
): RankedResponder | null {
  return rankAvailableResponders(incident, responders)[0] ?? null
}
