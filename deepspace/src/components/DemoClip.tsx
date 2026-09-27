import { useEffect, useRef } from 'react'

type DemoClipProps = {
  cameraId: string
  startSeconds?: number
  endSeconds?: number
}

/** Plays the existing local demo clip for this camera and can start at the evidence window. */
export function DemoClip({ cameraId, startSeconds, endSeconds }: DemoClipProps) {
  const video = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const node = video.current
    if (!node || startSeconds === undefined || Number.isNaN(startSeconds)) return
    const seek = () => {
      node.currentTime = startSeconds
    }
    node.addEventListener('loadedmetadata', seek)
    return () => node.removeEventListener('loadedmetadata', seek)
  }, [cameraId, startSeconds])

  return (
    <div>
      <video
        ref={video}
        className="w-full rounded-lg bg-black"
        controls
        data-testid={`camera-video-${cameraId}`}
        src={`/api/local/cameras/${cameraId}/video`}
      />
      {startSeconds !== undefined && endSeconds !== undefined && (
        <p className="mt-2 text-xs text-muted-foreground" data-testid="evidence-window">
          Evidence window {startSeconds}s – {endSeconds}s. Playback starts at the beginning of that window.
        </p>
      )}
    </div>
  )
}
