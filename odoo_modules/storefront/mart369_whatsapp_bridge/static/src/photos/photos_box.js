/**
 * The Confirmation pictures tab: the Photographs box of the product editor, on
 * the form's own record. The website and the WhatsApp page read one list, so a
 * picture added here is in Photographs and the other way round.
 */
import { registry } from "@web/core/registry";
import { ProductEditorWidget } from "@mart369_product/products/editor_widget";

export class PhotosBox extends ProductEditorWidget {
    static template = "mart369_whatsapp_bridge.PhotosBox";

    /** No "How shoppers see it" column here to make room for. */
    useFullWidth() {}
}

registry.category("view_widgets").add("mart369_photos_box", {
    component: PhotosBox,
});
