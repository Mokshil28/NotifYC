import { describe, expect, it } from 'vitest'
import { demoCameras } from './demo-data'
import { demoClipName } from './clips'

describe('demo clips', () => {
  it('maps each of the ten cameras to its own file', () => {
    expect(demoCameras).toHaveLength(10)
    const names = demoCameras.map((camera) => demoClipName(camera.cameraId))
    expect(names).toEqual([
      'cam_001.mp4',
      'cam_002.mp4',
      'cam_003.mp4',
      'cam_004.mp4',
      'cam_005.mp4',
      'cam_006.mp4',
      'cam_007.mp4',
      'cam_008.mp4',
      'cam_009.mp4',
      'cam_010.mp4',
    ])
  })

  it('rejects an unknown camera', () => {
    expect(demoClipName('CAM-042')).toBeNull()
    expect(demoClipName('CAM-011')).toBeNull()
  })
})
