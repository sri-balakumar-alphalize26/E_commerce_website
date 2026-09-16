/**
 * Whether a source should bypass the Next image optimizer.
 *
 * `/_next/image` answers 400 for SVG unless `images.dangerouslyAllowSVG` is
 * set, and that flag is global: turning it on to serve our own generated
 * pack-shots would also permit SVG from any remote source added later, where
 * the file could carry script. The flag is named the way it is for a reason.
 *
 * Bypassing costs nothing here. SVG is vector, so rasterising it at 640px
 * buys no quality and no bytes -- these files are 1-8 KB and scale perfectly
 * at any size. Raster sources are untouched by this and still go through the
 * optimizer, so the day real photography lands it is optimised normally with
 * no code change.
 */
export function isVector(src: string) {
  return src.toLowerCase().endsWith('.svg')
}
