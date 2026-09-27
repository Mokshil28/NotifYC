/** Maps a simulated camera id to the existing local demo file. No extra copies. */

const CLIP = /^CAM-(0\d{2})$/

export function demoClipName(cameraId: string): string | null {
  const match = CLIP.exec(cameraId)
  if (!match) return null
  const number = Number(match[1])
  if (number < 1 || number > 10) return null
  return `cam_${match[1]}.mp4`
}
