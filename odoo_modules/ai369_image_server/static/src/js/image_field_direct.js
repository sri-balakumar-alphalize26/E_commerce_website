/** Every image box of every app (current and future modules):
 *   - drag & drop a picture onto the box (or use the pencil) -> sent straight from the browser to the image
 *     server with a short-lived upload link; the record only keeps a tiny marker until Save;
 *   - under the image (form views) the permanent image-server link: hover shows it, click copies it.
 *  If the image server can't be reached the normal upload is used. */
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { browser } from "@web/core/browser/browser";
import { isBinarySize } from "@web/core/utils/binary";
import { ImageField } from "@web/views/fields/image/image_field";
import { BinaryField } from "@web/views/fields/binary/binary_field";
import { useEffect, useState } from "@odoo/owl";

const MARK = "PCEtLWltZ3Nydi"; // start of base64 "<!--imgsrv-" (staged upload or pasted link markers)
const previews = new Map();     // marker -> public URL of the picture

function toBlob(b64, type) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
        bytes[i] = bin.charCodeAt(i);
    }
    return new Blob([bytes], { type: type || "application/octet-stream" });
}

function readFile(file) {
    return new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result).split(",")[1]);
        r.onerror = reject;
        r.readAsDataURL(file);
    });
}

async function directUpload(info) {
    const t = await rpc("/ai369_image_server/upload_ticket", {});
    if (!t.enabled || !t.tickets?.length) {
        return null;
    }
    const resp = await fetch(t.tickets[0].upload_url, {
        method: "PUT",
        body: toBlob(info.data, info.type),
        headers: {
            "Content-Type": info.type || "application/octet-stream",
            "X-File-Name": encodeURIComponent(info.name || "file"),
        },
    });
    if (!resp.ok) {
        throw new Error(`image server: ${resp.status} ${await resp.text()}`);
    }
    return resp.json();
}

patch(ImageField.prototype, {
    setup() {
        super.setup(...arguments);
        this.imgsrv = useState({ url: "", status: "", staged: "", drag: false, copied: false });
        useEffect(
            (resId, value) => {
                this.imgsrv.url = "";
                this.imgsrv.status = "";
                this.imgsrv.staged = typeof value === "string" && value.startsWith(MARK) ? previews.get(value) || "" : "";
                if (this.imgsrvShowLink && resId && value && isBinarySize(value)) {
                    this.imgsrvFetch(resId);
                }
            },
            () => [this.props.record.resId, this.props.record.data[this.props.name]]
        );
    },

    get imgsrvShowLink() {
        return this.fieldType === "binary" && this.env.config?.viewType === "form";
    },

    async imgsrvFetch(resId) {
        try {
            const r = await rpc("/ai369_image_server/image_url", {
                model: this.props.record.resModel, res_id: resId, field: this.props.name,
            });
            if (resId === this.props.record.resId) {
                this.imgsrv.url = r.url || "";
                this.imgsrv.status = r.status || "";
            }
        } catch {
            // the link is a convenience only
        }
    },

    async imgsrvCopy(ev) {
        ev.stopPropagation();
        const url = this.imgsrv.url || this.imgsrv.staged;
        if (!url) {
            return;
        }
        try {
            await browser.navigator.clipboard.writeText(url);
        } catch {
            const ta = document.createElement("textarea");
            ta.value = url;
            document.body.append(ta);
            ta.select();
            document.execCommand("copy");
            ta.remove();
        }
        this.imgsrv.copied = true;
        browser.setTimeout(() => (this.imgsrv.copied = false), 1500);
    },

    // ---- paste a link of an image that is already on the image server (no upload)
    async imgsrvPasteLink(ev) {
        ev?.stopPropagation();
        if (this.props.readonly || this.fieldType !== "binary") {
            return;
        }
        const url = (window.prompt("Paste the image-server link of the picture (e.g. https://images.369ai.biz/products/…/main.webp)") || "").trim();
        if (!url) {
            return;
        }
        const r = await rpc("/ai369_image_server/check_link", { url });
        if (!r.ok) {
            this.notification.add(r.error, { type: "warning" });
            return;
        }
        this.state.isValid = true;
        const marker = btoa(`<!--imgsrv-linked:${r.url}-->`);
        previews.set(marker, r.public);
        this.props.record.update({ [this.props.name]: marker });
    },

    // ---- drag & drop
    imgsrvDragOver(ev) {
        if (this.props.readonly || this.fieldType !== "binary") {
            return;
        }
        ev.preventDefault();
        this.imgsrv.drag = true;
    },
    imgsrvDragLeave() {
        this.imgsrv.drag = false;
    },
    async imgsrvDrop(ev) {
        if (this.props.readonly || this.fieldType !== "binary") {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.imgsrv.drag = false;
        const file = [...(ev.dataTransfer?.files || [])].find((f) => f.type.startsWith("image/"));
        if (!file) {
            this.notification.add("Drop an image file (JPG, PNG, WEBP, GIF).", { type: "warning" });
            return;
        }
        await this.onFileUploaded({ name: file.name, size: file.size, type: file.type, data: await readFile(file) });
    },

    // ---- upload
    async onFileUploaded(info) {
        // also replaces the in-browser WEBP conversion: the image server makes the WEBP sizes itself
        if (this.fieldType !== "binary" || info.type === "image/svg+xml") {
            return super.onFileUploaded(info);
        }
        let res = null;
        try {
            res = await directUpload(info);
        } catch (e) {
            console.warn("Direct upload to the image server failed, using the normal upload.", e);
        }
        if (!res) {
            return super.onFileUploaded(info);
        }
        this.state.isValid = true;
        const marker = btoa(`<!--imgsrv-staged:${res.path}-->`);
        previews.set(marker, res.url);
        this.props.record.update({ [this.props.name]: marker });
    },

    getUrl(imageFieldName) {
        const value = this.props.record.data[this.props.name];
        if (typeof value === "string" && value.startsWith(MARK)) {
            this.lastURL = previews.get(value) || "/web/static/img/placeholder.png";
            return this.lastURL;
        }
        return super.getUrl(imageFieldName);
    },
});

/** File fields ("Upload your file": PDF, cheque scans, documents…) of every app: the file goes straight from the
 *  browser to the image server (private folder); the record keeps only a tiny marker until Save. */
patch(BinaryField.prototype, {
    async update(info) {
        if (info?.data && !String(info.data).startsWith(MARK)) {
            try {
                const res = await directUpload({ data: info.data, name: info.name, type: info.type || guessType(info.name) });
                if (res) {
                    return super.update({ ...info, data: btoa(`<!--imgsrv-staged:${res.path}-->`) });
                }
            } catch (e) {
                console.warn("Direct upload to the image server failed, using the normal upload.", e);
            }
        }
        return super.update(info);
    },
});

function guessType(name) {
    const ext = (name || "").split(".").pop().toLowerCase();
    return { pdf: "application/pdf", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp",
             gif: "image/gif", doc: "application/msword", xls: "application/vnd.ms-excel", csv: "text/csv",
             txt: "text/plain", zip: "application/zip" }[ext] || "application/octet-stream";
}
