/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    setup() {
        super.setup();
        // Initialize cache for HKA PDF images
        this.hkaPdfImageCache = new Map();
    },

    async getHKAPDFImage(invoiceId) {
        // Check if image is in cache
        if (this.hkaPdfImageCache.has(invoiceId)) {
            console.log('[HKA Debug] Using cached image for invoice:', invoiceId);
            return this.hkaPdfImageCache.get(invoiceId);
        }

        // If not in cache, fetch and store it
        try {
            const result = await this.rpc("/pos/get_hka_pdf", {
                invoice_id: invoiceId,
            });

            if (result.success && result.image_data) {
                console.log('[HKA Debug] Caching image for invoice:', invoiceId);
                this.hkaPdfImageCache.set(invoiceId, result.image_data);
                return result.image_data;
            } else {
                console.error('[HKA Debug] Error getting image data:', result.error);
                return null;
            }
        } catch (error) {
            console.error('[HKA Debug] Error fetching image:', error);
            return null;
        }
    }
});
