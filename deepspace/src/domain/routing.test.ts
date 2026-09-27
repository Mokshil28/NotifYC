import { describe, expect, it } from 'vitest'
import { demoCameras, demoResponders } from './demo-data'
import { formatKm, haversineKm, rankAvailableResponders, selectNearestAvailable } from './routing'

const incident = { latitude: 40.7061, longitude: -73.9969 }

describe('haversineKm', () => {
  it('is zero for the same point and symmetric', () => {
    const point = { latitude: 40.758, longitude: -73.9855 }
    expect(haversineKm(point, point)).toBe(0)
    const other = { latitude: 40.7061, longitude: -73.9969 }
    expect(haversineKm(point, other)).toBeCloseTo(haversineKm(other, point), 8)
    expect(haversineKm(point, other)).toBeGreaterThan(5)
    expect(haversineKm(point, other)).toBeLessThan(7)
  })

  it('matches a known one-degree latitude span', () => {
    const distance = haversineKm({ latitude: 0, longitude: 0 }, { latitude: 1, longitude: 0 })
    expect(distance).toBeCloseTo(111.195, 2)
    expect(formatKm(1.2)).toBe('1.20 km')
  })
})

describe('selectNearestAvailable', () => {
  const responders = demoResponders.map((responder) => ({
    responderId: responder.responderId,
    status: responder.status,
    latitude: responder.latitude,
    longitude: responder.longitude,
  }))

  it('selects the colocated available unit at Brooklyn Bridge', () => {
    const nearest = selectNearestAvailable(incident, responders)
    expect(nearest?.responder.responderId).toBe('UNIT-42')
    expect(nearest?.distanceKm).toBe(0)
  })

  it('ignores an unavailable unit even when it is closer', () => {
    const ranked = rankAvailableResponders(
      { latitude: 40.7496, longitude: -73.9877 },
      responders,
    )
    expect(ranked.map((row) => row.responder.responderId)).not.toContain('UNIT-18')
    expect(ranked[0]?.responder.responderId).not.toBe('UNIT-18')
  })

  it('returns null when nobody is available', () => {
    const nearest = selectNearestAvailable(incident, responders.map((responder) => ({ ...responder, status: 'unavailable' })))
    expect(nearest).toBeNull()
  })

  it('breaks an equal-distance tie by responder id', () => {
    const tied = [
      { responderId: 'UNIT-90', status: 'available', latitude: 40.75, longitude: -73.99 },
      { responderId: 'UNIT-20', status: 'available', latitude: 40.75, longitude: -73.99 },
      { responderId: 'UNIT-50', status: 'unavailable', latitude: 40.75, longitude: -73.99 },
    ]
    const ranked = rankAvailableResponders({ latitude: 40.7, longitude: -73.9 }, tied)
    expect(ranked.map((row) => row.responder.responderId)).toEqual(['UNIT-20', 'UNIT-90'])
  })

  it('does not seed a collision incident', () => {
    expect(demoCameras).toHaveLength(10)
  })
})
