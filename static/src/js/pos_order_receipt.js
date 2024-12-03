/** @odoo-module */
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Static cache for HKA PDF images
const hkaPdfImageCache = new Map();

patch(OrderReceipt.prototype, {
    setup() {
        super.setup();
        this.state = useState({
            error: null,
            isLoading: false,
            hkaPdfImage: null
        });
        this.pos = useService("pos");
        this.rpc = useService("rpc");
        
        // Check if custom receipt system is available
        const hasCustomReceipts = this.pos?.config?.is_custom_receipt !== undefined;
        if (!hasCustomReceipts) {
            console.warn('[HKA Debug] Custom receipts system not properly configured');
        }
        
        this.fetchInvoiceData();
    },
    
    get orderData() {
        if (this.props.data) {
            return this.props.data;
        }
        const currentOrder = this.pos.get_order();
        return currentOrder ? currentOrder.export_for_printing() : null;
    },
    
    async getHKAPDFImage(invoiceId) {
        // Check cache first
        if (hkaPdfImageCache.has(invoiceId)) {
            console.log('[HKA Debug] Using cached image for invoice:', invoiceId);
            return hkaPdfImageCache.get(invoiceId);
        }

        // If not in cache, fetch and store
        try {
            const result = await this.rpc("/pos/get_hka_pdf", {
                invoice_id: invoiceId,
            });

            if (result.success && result.image_data) {
                console.log('[HKA Debug] Caching image for invoice:', invoiceId);
                hkaPdfImageCache.set(invoiceId, result.image_data);
                return result.image_data;
            }
            return null;
        } catch (error) {
            console.error('[HKA Debug] Error fetching image:', error);
            return null;
        }
    },
    
    async fetchInvoiceData() {
        console.log('[HKA Debug] Starting fetchInvoiceData');
        this.state.isLoading = true;
        
        if (!this.orderData) {
            console.log('[HKA Debug] No valid order data found');
            this.state.error = 'No valid order data found';
            this.state.isLoading = false;
            return;
        }
        
        // Use the appropriate reference based on the order data
        const orderRef = this.orderData.pos_reference || this.orderData.name;
        if (!orderRef) {
            console.log('[HKA Debug] No valid reference found in order data');
            this.state.error = 'No valid reference found in order data';
            this.state.isLoading = false;
            return;
        }
        
        try {
            const invoiceResult = await this.rpc("/pos/get_order_invoice", {
                pos_reference: orderRef,
            });
            console.log('[HKA Debug] Order invoice info:', invoiceResult);
            
            if (invoiceResult?.invoice_id) {
                const imageData = await this.getHKAPDFImage(invoiceResult.invoice_id);
                if (imageData) {
                    this.state.hkaPdfImage = imageData;
                    console.log('[HKA Debug] Successfully got image data');
                } else {
                    console.error('[HKA Debug] No image data available');
                    this.state.error = 'Failed to get image data';
                }
            } else {
                console.log('[HKA Debug] No invoice found for order');
                this.state.error = invoiceResult.error || 'No invoice found for order';
            }
        } catch (error) {
            console.error('[HKA Debug] Error fetching invoice data:', error);
            this.state.error = error.message || 'Failed to fetch invoice data';
        } finally {
            this.state.isLoading = false;
        }
    },
    
    get templateProps() {
        const receipt = this.pos.get_order().export_for_printing();
        const receiptWithPdf = {
            ...receipt,
            hkaPdfImage: this.state.hkaPdfImage
        };

        console.log('[HKA Debug] Receipt props:', {
            hasImage: !!this.state.hkaPdfImage,
            imageDataStart: this.state.hkaPdfImage ? this.state.hkaPdfImage.substring(0, 50) + '...' : null
        });

        return {
            data: this.props.data,
            order: this.pos.orders,
            receipt: receiptWithPdf,
            orderlines: this.pos.get_order().get_orderlines(),
            paymentlines: this.pos.get_order().get_paymentlines()
        };
    }
});
