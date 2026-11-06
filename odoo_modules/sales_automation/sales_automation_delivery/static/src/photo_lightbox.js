/**
 * Parcel photos on the delivery job form open in a popup on the same page.
 *
 * The thumbnails are plain links inside the computed Html field
 * `sa_photos_html` (class `o_sa_photo`, `data-group` pickup / delivery /
 * problem). A plain click opens the overlay; ctrl / middle click keeps the
 * browser's own "open in a new tab".
 *
 * Zoom: mouse wheel, the + / - buttons, + / - / 0 keys, double click (or
 * double tap), pinch on a phone. Zoomed in, drag to move the photo; swipe
 * to the next photo only works at normal size.
 */

const MIN_SCALE = 1;
const MAX_SCALE = 6;

let overlay = null;
let img = null;
let items = [];
let index = 0;

let scale = 1;
let tx = 0;
let ty = 0;
const pointers = new Map();     // pointerId -> {x, y}
let gesture = null;             // what the current press is doing
let lastTap = 0;

function captionOf(link) {
    return (link.innerText || link.title || "")
        .split("\n").map((s) => s.trim()).filter(Boolean).join(" · ");
}

function build() {
    overlay = document.createElement("div");
    overlay.className = "o_sa_lightbox";
    overlay.innerHTML = `
        <figure class="o_sa_lb_figure">
            <img class="o_sa_lb_img" alt="" draggable="false"/>
            <figcaption class="o_sa_lb_caption"></figcaption>
        </figure>
        <button type="button" class="o_sa_lb_close" aria-label="Close">&times;</button>
        <button type="button" class="o_sa_lb_nav o_sa_lb_prev" aria-label="Previous">&#8249;</button>
        <button type="button" class="o_sa_lb_nav o_sa_lb_next" aria-label="Next">&#8250;</button>
        <div class="o_sa_lb_zoom">
            <button type="button" class="o_sa_lb_out" aria-label="Zoom out">&minus;</button>
            <span class="o_sa_lb_pct">100%</span>
            <button type="button" class="o_sa_lb_in" aria-label="Zoom in">+</button>
            <button type="button" class="o_sa_lb_fit" aria-label="Fit to screen">&#10530;</button>
        </div>`;
    img = overlay.querySelector(".o_sa_lb_img");

    overlay.addEventListener("click", (ev) => {
        if (ev.target.closest(".o_sa_lb_prev")) {
            show(index - 1);
        } else if (ev.target.closest(".o_sa_lb_next")) {
            show(index + 1);
        } else if (ev.target.closest(".o_sa_lb_in")) {
            zoomAtCentre(scale * 1.5);
        } else if (ev.target.closest(".o_sa_lb_out")) {
            zoomAtCentre(scale / 1.5);
        } else if (ev.target.closest(".o_sa_lb_fit")) {
            resetZoom();
        } else if (ev.target.closest(".o_sa_lb_close")) {
            close();
        } else if (!ev.target.closest(".o_sa_lb_img, .o_sa_lb_zoom") && !(gesture && gesture.moved)) {
            close();
        }
    });
    overlay.addEventListener("wheel", (ev) => {
        ev.preventDefault();
        zoomAt(scale * (ev.deltaY < 0 ? 1.2 : 1 / 1.2), ev.clientX, ev.clientY);
    }, { passive: false });
    img.addEventListener("dblclick", (ev) => {
        ev.preventDefault();
        toggleZoom(ev.clientX, ev.clientY);
    });
    overlay.addEventListener("pointerdown", onPointerDown);
    overlay.addEventListener("pointermove", onPointerMove);
    overlay.addEventListener("pointerup", onPointerUp);
    overlay.addEventListener("pointercancel", onPointerUp);
}

// ---------------------------------------------------------------- zoom
function apply() {
    // keep part of the photo on screen: no panning past its own edges
    const w = img.offsetWidth;
    const h = img.offsetHeight;
    const maxX = (w * scale - w) / 2;
    const maxY = (h * scale - h) / 2;
    tx = Math.min(maxX, Math.max(-maxX, tx));
    ty = Math.min(maxY, Math.max(-maxY, ty));
    if (scale === 1) {
        tx = ty = 0;
    }
    img.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    img.style.cursor = scale > 1 ? "grab" : "zoom-in";
    overlay.classList.toggle("o_sa_lb_zoomed", scale > 1);
    overlay.querySelector(".o_sa_lb_pct").textContent = `${Math.round(scale * 100)}%`;
}

function zoomAt(next, x, y) {
    next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, next));
    if (next === scale) {
        return;
    }
    // the point under (x, y) stays under (x, y)
    const r = img.getBoundingClientRect();
    const cx = r.left + r.width / 2 - tx;
    const cy = r.top + r.height / 2 - ty;
    tx = x - cx - (next / scale) * (x - cx - tx);
    ty = y - cy - (next / scale) * (y - cy - ty);
    scale = next;
    apply();
}

function zoomAtCentre(next) {
    const r = overlay.getBoundingClientRect();
    zoomAt(next, r.left + r.width / 2, r.top + r.height / 2);
}

function toggleZoom(x, y) {
    if (scale > 1) {
        resetZoom();
    } else {
        zoomAt(2.5, x, y);
    }
}

function resetZoom() {
    scale = 1;
    tx = ty = 0;
    apply();
}

// ------------------------------------------------- drag, pinch, swipe
function onPointerDown(ev) {
    if (ev.target.closest("button, .o_sa_lb_zoom")) {
        return;
    }
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (pointers.size === 1) {
        gesture = { kind: "drag", x: ev.clientX, y: ev.clientY, tx, ty, moved: false,
                    onImg: !!ev.target.closest(".o_sa_lb_img") };
        if (scale > 1) {
            img.style.cursor = "grabbing";
        }
    } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        gesture = { kind: "pinch", dist: Math.hypot(a.x - b.x, a.y - b.y), scale, moved: true };
    }
}

function onPointerMove(ev) {
    if (!pointers.has(ev.pointerId) || !gesture) {
        return;
    }
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (gesture.kind === "pinch" && pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (gesture.dist > 0) {
            zoomAt(gesture.scale * dist / gesture.dist, (a.x + b.x) / 2, (a.y + b.y) / 2);
        }
    } else if (gesture.kind === "drag") {
        const dx = ev.clientX - gesture.x;
        const dy = ev.clientY - gesture.y;
        if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
            gesture.moved = true;
        }
        if (scale > 1) {
            tx = gesture.tx + dx;
            ty = gesture.ty + dy;
            apply();
        }
    }
}

function onPointerUp(ev) {
    if (!pointers.has(ev.pointerId)) {
        return;
    }
    pointers.delete(ev.pointerId);
    const g = gesture;
    if (pointers.size > 0) {
        // one finger lifted from a pinch: carry on as a drag from here
        const [p] = [...pointers.values()];
        gesture = { kind: "drag", x: p.x, y: p.y, tx, ty, moved: true };
        return;
    }
    if (g && g.kind === "drag") {
        const dx = ev.clientX - g.x;
        if (scale === 1 && Math.abs(dx) > 50 && items.length > 1) {
            show(index + (dx < 0 ? 1 : -1));                   // swipe
        } else if (!g.moved && g.onImg && ev.pointerType === "touch") {
            const now = Date.now();                             // double tap
            if (now - lastTap < 300) {
                toggleZoom(ev.clientX, ev.clientY);
                lastTap = 0;
            } else {
                lastTap = now;
            }
        }
    }
    if (scale > 1) {
        img.style.cursor = "grab";
    }
    // the click that follows this pointerup still needs to know it was a drag
    setTimeout(() => {
        if (!pointers.size) {
            gesture = null;
        }
    }, 0);
}

// ------------------------------------------------------------- popup
function show(i) {
    index = (i + items.length) % items.length;
    const link = items[index];
    const many = items.length > 1;
    resetZoom();
    img.src = link.getAttribute("href");
    overlay.querySelector(".o_sa_lb_caption").textContent =
        (many ? `${index + 1} / ${items.length} · ` : "") + captionOf(link);
    for (const nav of overlay.querySelectorAll(".o_sa_lb_nav")) {
        nav.style.display = many ? "" : "none";
    }
}

function onKey(ev) {
    if (ev.key === "Escape") {
        ev.stopPropagation();
        ev.preventDefault();
        close();
    } else if (ev.key === "ArrowLeft") {
        show(index - 1);
    } else if (ev.key === "ArrowRight") {
        show(index + 1);
    } else if (ev.key === "+" || ev.key === "=") {
        zoomAtCentre(scale * 1.5);
    } else if (ev.key === "-") {
        zoomAtCentre(scale / 1.5);
    } else if (ev.key === "0") {
        resetZoom();
    }
}

function open(link) {
    if (!overlay) {
        build();
    }
    const group = link.dataset.group;
    const scope = link.closest(".o_field_html") || document;
    items = [...scope.querySelectorAll("a.o_sa_photo")].filter(
        (a) => a.dataset.group === group
    );
    document.body.appendChild(overlay);
    // capture: Esc must close the popup, not discard the form / leave the record
    document.addEventListener("keydown", onKey, true);
    show(Math.max(0, items.indexOf(link)));
}

function close() {
    if (overlay && overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
        img.removeAttribute("src");
    }
    pointers.clear();
    gesture = null;
    document.removeEventListener("keydown", onKey, true);
}

document.addEventListener("click", (ev) => {
    const link = ev.target.closest && ev.target.closest("a.o_sa_photo");
    if (!link || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) {
        return;
    }
    ev.preventDefault();
    ev.stopPropagation();
    open(link);
}, true);
