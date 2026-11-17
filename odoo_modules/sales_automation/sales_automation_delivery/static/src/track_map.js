/* The WhatsApp tracking page's live map: OpenFreeMap's Liberty style through
 * MapLibre, with the rider's top-view scooter gliding along the road.
 *
 * delivery_track_templates.xml loads this plainly, outside any asset bundle: it
 * is a public page for a customer's phone. The page keeps its old Leaflet map
 * as the backup, and start() calls onFail when this one cannot start.
 *
 * The movement rules are the same as the website's order page. This module
 * cannot import that file, so tests/unit/trackMapWa.test.mjs in the 369Mart
 * repo checks that the two give the same answers.
 *
 * Points are [lat, lng].
 */
(function (root) {
    "use strict";

    var ON_ROAD_METRES = 60;      // a phone's GPS wanders about this much
    var JITTER_METRES = 5;        // less than this is not the rider moving
    var GLIDE_MIN_MS = 3000;
    var GLIDE_MAX_MS = 20000;
    var GLIDE_DEFAULT_MS = 6000;
    var TURN_DEGREES_PER_SECOND = 180;
    var STYLE_WAIT_MS = 8000;
    var EARTH = 6371000;
    var NOTHING = { type: "FeatureCollection", features: [] };

    function rad(d) { return d * Math.PI / 180; }
    function deg(r) { return r * 180 / Math.PI; }

    function metres(a, b) {
        var x = rad(b[1] - a[1]) * Math.cos(rad((a[0] + b[0]) / 2));
        var y = rad(b[0] - a[0]);
        return Math.hypot(x, y) * EARTH;
    }

    // Degrees clockwise from north: what the map's icon-rotate wants.
    function bearing(a, b) {
        var y = Math.sin(rad(b[1] - a[1])) * Math.cos(rad(b[0]));
        var x = Math.cos(rad(a[0])) * Math.sin(rad(b[0]))
            - Math.sin(rad(a[0])) * Math.cos(rad(b[0])) * Math.cos(rad(b[1] - a[1]));
        return (deg(Math.atan2(y, x)) + 360) % 360;
    }

    function locate(route, at) {
        var scale = Math.cos(rad(at[0]));
        var best = null;
        var walked = 0;
        for (var i = 0; i < route.length - 1; i += 1) {
            var a = route[i];
            var b = route[i + 1];
            var piece = metres(a, b);
            var dx = (b[1] - a[1]) * scale;
            var dy = b[0] - a[0];
            var across = dx * dx + dy * dy;
            var t = across
                ? Math.max(0, Math.min(1, (((at[1] - a[1]) * scale) * dx + (at[0] - a[0]) * dy) / across))
                : 0;
            var point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
            var away = metres(point, at);
            if (!best || away < best.away) { best = { point: point, away: away, along: walked + piece * t, piece: i }; }
            walked += piece;
        }
        return best;
    }

    function usable(route) { return Array.isArray(route) && route.length > 1; }

    function placeOnRoad(route, at) {
        if (!usable(route)) { return { at: at, bearing: 0 }; }
        var spot = locate(route, at);
        if (spot.away > ON_ROAD_METRES) { return { at: at, bearing: 0 }; }
        return { at: spot.point, bearing: bearing(route[spot.piece], route[spot.piece + 1]) };
    }

    function pathLength(points) {
        var total = 0;
        for (var i = 0; i < points.length - 1; i += 1) { total += metres(points[i], points[i + 1]); }
        return total;
    }

    function tidy(points) {
        var out = [points[0]];
        points.slice(1).forEach(function (p) {
            if (metres(out[out.length - 1], p) > 0.01) { out.push(p); }
        });
        return out.length > 1 ? out : [points[0], points[points.length - 1]];
    }

    // Along the road when on it and going forward; otherwise straight. Null
    // when the rider has not really moved.
    function planMove(from, to, route) {
        var target = to;
        var points = null;
        if (usable(route)) {
            var a = locate(route, from);
            var b = locate(route, to);
            if (b.away <= ON_ROAD_METRES) { target = b.point; }
            if (a.away <= ON_ROAD_METRES && b.away <= ON_ROAD_METRES && b.along > a.along) {
                var road = [from, a.point].concat(route.slice(a.piece + 1, b.piece + 1), [b.point]);
                // A road doubling back past itself can match the far stretch.
                if (pathLength(road) <= 4 * metres(from, to) + 200) { points = road; }
            }
        }
        if (metres(from, target) < JITTER_METRES) { return null; }
        return tidy(points || [from, target]);
    }

    function pointAt(path, k) {
        var left = Math.max(0, Math.min(1, k)) * pathLength(path);
        for (var i = 0; i < path.length - 1; i += 1) {
            var piece = metres(path[i], path[i + 1]);
            if (left <= piece || i === path.length - 2) {
                var t = piece ? Math.min(1, left / piece) : 1;
                return {
                    at: [path[i][0] + (path[i + 1][0] - path[i][0]) * t, path[i][1] + (path[i + 1][1] - path[i][1]) * t],
                    bearing: bearing(path[i], path[i + 1]),
                };
            }
            left -= piece;
        }
        return { at: path[path.length - 1], bearing: 0 };
    }

    function nextGlideMs(lastFixMs, fixMs, current) {
        if (current === undefined) { current = GLIDE_DEFAULT_MS; }
        if (!lastFixMs || !fixMs || !(fixMs > lastFixMs)) { return current; }
        return Math.max(GLIDE_MIN_MS, Math.min(GLIDE_MAX_MS, fixMs - lastFixMs));
    }

    function turnToward(current, target, maxStep) {
        var gap = ((target - current + 540) % 360) - 180;
        if (Math.abs(gap) <= maxStep) { return (target + 360) % 360; }
        return (current + Math.sign(gap) * maxStep + 360) % 360;
    }

    /* ---------------------------------------------------------------- the map */

    function lngLat(p) { return [p[1], p[0]]; }
    function reduced() { return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches); }
    function known(p) { return !!(p && p.latitude); }
    function point(p) { return [p.latitude, p.longitude]; }

    /* options: { container, style, picture, pictureHeight, drawnHeight, decode,
     *            onShown, onFail }
     * Returns { show(payload) }, or null when MapLibre did not load. The map
     * itself is made on the first payload with a place to show. */
    function start(options) {
        var ml = root.maplibregl;
        if (!ml) { return null; }
        var map = null, timer = null, ready = false, broken = false, latest = null;
        var pins = {}, fitted = false, riderSeen = false, lineText = null, route = null;
        var at = null, heading = 0, fixMs = 0, glideMs, frame = 0;

        function fail() {
            if (broken) { return; }
            broken = true;
            clearTimeout(timer);
            cancelAnimationFrame(frame);
            try { if (map) { map.remove(); } } catch (e) { /* it never got going */ }
            map = null;
            options.onFail();
        }

        function make(first, zoom) {
            try {
                map = new ml.Map({
                    container: options.container,
                    style: options.style,
                    center: lngLat(first),
                    zoom: zoom || 13,
                    maxZoom: 19,
                    scrollZoom: false,
                    dragRotate: false,
                    pitchWithRotate: false,
                    touchPitch: false,
                    // The credits stay written out, on phones too.
                    attributionControl: { compact: false },
                });
            } catch (e) {
                // No WebGL. Not from inside this call: the page is mid-update.
                setTimeout(fail, 0);
                return;
            }
            map.touchZoomRotate.disableRotation();
            map.keyboard.disableRotation();
            map.on("error", function (e) { if (!ready && !(e && e.sourceId)) { fail(); } });
            timer = setTimeout(fail, STYLE_WAIT_MS);
            map.once("styledata", function () {
                map.loadImage(options.picture).then(function (picture) {
                    if (broken) { return; }
                    map.addImage("sa-rider", picture.data);
                    // Under the street names; the scooter goes over everything.
                    var firstLabel = map.getStyle().layers.filter(function (l) { return l.type === "symbol"; })[0];
                    map.addSource("sa-line", { type: "geojson", data: NOTHING });
                    map.addSource("sa-rider", { type: "geojson", data: NOTHING });
                    map.addLayer({
                        id: "sa-line", type: "line", source: "sa-line",
                        layout: { "line-cap": "round", "line-join": "round" },
                        paint: { "line-color": "#0a78ab", "line-width": 5, "line-opacity": 0.85 },
                    }, firstLabel && firstLabel.id);
                    map.addLayer({
                        id: "sa-rider", type: "symbol", source: "sa-rider",
                        layout: {
                            "icon-image": "sa-rider",
                            "icon-size": options.drawnHeight / options.pictureHeight,
                            "icon-rotate": ["get", "heading"],
                            "icon-rotation-alignment": "map",
                            "icon-allow-overlap": true,
                            "icon-ignore-placement": true,
                        },
                    });
                    clearTimeout(timer);
                    ready = true;
                    map.resize();
                    if (latest) { draw(latest); }
                }).catch(fail);
            });
        }

        function pin(name, place, text, cls) {
            if (!known(place)) { return; }
            // An approximate pin (a looked-up address) is replaced by the
            // exact one when that arrives, so the pin follows the place.
            // MapLibre adds its own classes to the element: only `approx` is
            // toggled here, the rest is left alone.
            var approx = !!place.approximate;
            var key = place.latitude + "," + place.longitude + "," + approx;
            var old = pins[name];
            if (old) {
                if (old._saKey === key) { return; }
                old.setLngLat(lngLat(point(place)));
                old.getElement().classList.toggle("approx", approx);
                old._saKey = key;
                return;
            }
            var el = document.createElement("span");
            el.className = "sa-pin " + cls + (approx ? " approx" : "");
            el.textContent = text;
            pins[name] = new ml.Marker({ element: el, anchor: "center" }).setLngLat(lngLat(point(place))).addTo(map);
            pins[name]._saKey = key;
        }

        function fit(points, padding) {
            var bounds = points.reduce(function (b, p) { return b.extend(lngLat(p)); },
                new ml.LngLatBounds(lngLat(points[0]), lngLat(points[0])));
            map.fitBounds(bounds, { padding: padding, maxZoom: 15, animate: !reduced() });
        }

        function setRider() {
            map.getSource("sa-rider").setData({
                type: "Feature", properties: { heading: heading },
                geometry: { type: "Point", coordinates: lngLat(at) },
            });
        }

        function hideRider() {
            cancelAnimationFrame(frame);
            at = null;
            fixMs = 0;
            riderSeen = false;
            map.getSource("sa-rider").setData(NOTHING);
        }

        function keepInView(place) {
            var c = map.getContainer();
            var px = map.project(lngLat(place));
            var x = c.clientWidth * 0.25;
            var y = c.clientHeight * 0.25;
            if (px.x < x || px.x > c.clientWidth - x || px.y < y || px.y > c.clientHeight - y) {
                map.panTo(lngLat(place), { animate: !reduced(), duration: 1200 });
            }
        }

        function moveRider(r, you) {
            var place = [r.latitude, r.longitude];
            map.setPaintProperty("sa-rider", "icon-opacity", r.stale ? 0.45 : 1);
            var newFix = r.fix_at ? new Date(r.fix_at).getTime() : 0;
            glideMs = nextGlideMs(fixMs, newFix, glideMs);
            if (newFix) { fixMs = newFix; }
            if (!at) {
                var first = placeOnRoad(route, place);
                at = first.at;
                heading = first.bearing;
                setRider();
            } else {
                var path = planMove(at, place, route);
                if (path) {
                    cancelAnimationFrame(frame);
                    if (reduced() || document.hidden) {
                        var end = pointAt(path, 1);
                        at = end.at;
                        heading = end.bearing;
                        setRider();
                    } else {
                        var began = performance.now(), last = began, ms = glideMs;
                        var step = function (now) {
                            var k = Math.min(1, (now - began) / ms);
                            var here = pointAt(path, k);
                            at = here.at;
                            heading = turnToward(heading, here.bearing, TURN_DEGREES_PER_SECOND * Math.max(0, now - last) / 1000);
                            last = now;
                            setRider();
                            // Past the end only to finish a turn still under way.
                            var turning = Math.abs(((here.bearing - heading + 540) % 360) - 180) > 0.5;
                            if (k < 1 || turning) { frame = requestAnimationFrame(step); }
                        };
                        frame = requestAnimationFrame(step);
                    }
                }
            }
            if (!riderSeen) {
                riderSeen = true;
                fit(known(you) ? [place, point(you)] : [place, place], 70);
            } else {
                keepInView(place);
            }
        }

        function draw(d) {
            pin("shop", d.shop, "Shop", "");
            pin("you", d.dropoff, "You", "you");
            var text = d.route && d.route.polyline;
            if (text && text !== lineText) {
                lineText = text;
                route = options.decode(text);
                map.getSource("sa-line").setData({
                    type: "Feature", properties: {},
                    geometry: { type: "LineString", coordinates: route.map(lngLat) },
                });
                map.setPaintProperty("sa-line", "line-dasharray", d.route.approximate ? [1.2, 2] : null);
            }
            if (!fitted) {
                var all = (route || []).slice();
                if (known(d.shop)) { all.push(point(d.shop)); }
                if (known(d.dropoff)) { all.push(point(d.dropoff)); }
                if (all.length) {
                    fit(all, { top: 56, right: 40, bottom: 64, left: 40 });
                    fitted = true;
                }
            }
            if (!d.ended && d.show_rider && d.rider) { moveRider(d.rider, d.dropoff); } else { hideRider(); }
        }

        return {
            show: function (d) {
                if (broken) { return; }
                latest = d;
                if (!map) {
                    // A pin, else the town the server found to centre on, so
                    // an order with nothing pinned yet still shows a map.
                    var first = known(d.shop) ? d.shop : known(d.dropoff) ? d.dropoff : known(d.center) ? d.center : null;
                    if (!first) { return; }
                    options.onShown();
                    make(point(first), known(d.shop) || known(d.dropoff) ? 13 : 12);
                } else if (ready) {
                    draw(d);
                }
            },
        };
    }

    var api = {
        start: start, bearing: bearing, locate: locate, metres: metres, nextGlideMs: nextGlideMs,
        placeOnRoad: placeOnRoad, planMove: planMove, pointAt: pointAt, turnToward: turnToward,
    };
    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    } else {
        root.SaTrackMap = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
