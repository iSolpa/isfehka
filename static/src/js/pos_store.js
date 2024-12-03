/** @odoo-module */
import { PosOrder } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

// Static cache for HKA PDF images
const hkaPdfImageCache = new Map();

patch(PosOrder.prototype, {
    setup() {
        super.setup();
        this.rpc = useService("rpc");
    },

    async export_for_printing(baseUrl, headerData) {
        const result = await super.export_for_printing(...arguments);
        console.log('[HKA Debug] Exporting order for printing:', this.name);
        
        try {
            // Try to get invoice and image data
            const orderRef = this.pos_reference || this.name;
            console.log('[HKA Debug] Fetching invoice for order:', orderRef);
            
            const invoiceResult = await this.rpc("/pos/get_order_invoice", {
                pos_reference: orderRef,
            });
            
            console.log('[HKA Debug] Invoice result:', invoiceResult);
            
            if (invoiceResult.success && invoiceResult.invoice_id) {
                const invoiceId = invoiceResult.invoice_id;
                
                // Check cache first
                if (!hkaPdfImageCache.has(invoiceId)) {
                    console.log('[HKA Debug] Fetching image for invoice:', invoiceId);
                    const imageResult = await this.rpc("/pos/get_hka_pdf", {
                        invoice_id: invoiceId,
                    });
                    
                    if (imageResult.success && imageResult.image_data) {
                        console.log('[HKA Debug] Caching image for invoice:', invoiceId);
                        hkaPdfImageCache.set(invoiceId, imageResult.image_data);
                    } else {
                        console.error('[HKA Debug] Failed to get image:', imageResult.error);
                    }
                } else {
                    console.log('[HKA Debug] Using cached image for invoice:', invoiceId);
                }
                
                // Add image data to the printing result
                result.hkaPdfImage = hkaPdfImageCache.get(invoiceId) || null;
                console.log('[HKA Debug] Added image to receipt:', !!result.hkaPdfImage);
            }
        } catch (error) {
            console.error('[HKA Debug] Error preparing order for printing:', error);
        }
        
        return result;
    },
});
