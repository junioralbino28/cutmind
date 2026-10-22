// Frames the decoded picture of cut.mp4 trails the composition index: the cut's
// VIDEO start time in frames, rounded UP. OffthreadVideo draws the frame at or
// before frame/fps, so a video stream that starts even 0.02s after zero shows
// every frame one composition frame late. segments.json carries the measured
// value (`videoLag`, written by the segments step from ffprobe's start_time);
// edit-data.json `videoLag` overrides it. Without either: 1, what cut.mp4 files
// from older renders needed (video starting at 0.033s). Everything that must
// change WITH the picture adds it — camera zoom steps, split windows, the
// caption seam, person mattes — and mixar_final.py delays the voice by it. With
// the wrong value the zoom steps one frame after every cut (a visible double
// step) and every overlay window opens a frame off.
import editData from '../public/edit-data.json';
import segData from '../public/segments.json';

export const VIDEO_LAG: number = Number(
  (editData as {videoLag?: number}).videoLag ?? (segData as {videoLag?: number}).videoLag ?? 1,
);
