/**
 * track_map.js — static/js/track_map.js
 *
 * NOTE: The authoritative track map logic lives in the template
 * (indexsp_python_backend.html). This file is kept for reference only
 * and is NOT loaded by the template to avoid duplicate function conflicts.
 *
 * If you move track map JS here in the future, ensure the template does
 * not also define the same track-map globals.
 *
 * All point coordinates use the px/py convention (normalised pixel space):
 *   - Track shape points: { px, py }
 *   - Live car points:    { driverNumber, x, y, px, py, date }
 *
 * DO NOT use p.x or p.y for SVG drawing — always use p.px and p.py.
 */

window.F1TrackMapReference = {
    svgPointsString(points) {
        return (points || [])
            .map(p => `${Number(p.px).toFixed(1)},${Number(p.py).toFixed(1)}`)
            .join(" ");
    },
};
