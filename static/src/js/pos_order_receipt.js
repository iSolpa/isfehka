/** @odoo-module */
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(OrderReceipt.prototype, {
    setup() {
        super.setup();
        this.state = useState({
            error: null,
            isLoading: false
        });
        this.pos = useService("pos");
        this.rpc = useService("rpc");
    },
    
    async loadHkaImage(orderData) {
        if (!orderData || !orderData.name) {
            console.log('[HKA Debug] No order data to load HKA image');
            return orderData;
        }

        try {
            console.log('[HKA Debug] Loading HKA image for order:', orderData.name);
            
            const invoiceResult = await this.rpc("/pos/get_order_invoice", {
                pos_reference: orderData.name,
            });
            
            console.log('[HKA Debug] Invoice result:', invoiceResult);
            
            if (invoiceResult.success && invoiceResult.invoice_id) {
                const imageResult = await this.rpc("/pos/get_hka_pdf", {
                    invoice_id: invoiceResult.invoice_id,
                });
                
                if (imageResult.success && imageResult.image_data) {
                    console.log('[HKA Debug] Successfully loaded HKA image');
                    return { ...orderData, hkaPdfImage: imageResult.image_data };
                }
            }
        } catch (error) {
            console.error('[HKA Debug] Error loading HKA image:', error);
        }
        
        return orderData;
    },
    
    get orderData() {
        const data = this.props.data;
        console.log('[HKA Debug] Receipt props data:', data);
        
        if (!data) {
            const currentOrder = this.pos.get_order()?.export_for_printing();
            console.log('[HKA Debug] Using current order data:', currentOrder);
            return currentOrder;
        }
        
        // For reprint case, load the HKA image
        if (!data.hkaPdfImage) {
            console.log('[HKA Debug] Reprint case - loading HKA image');
            this.loadHkaImage(data).then(updatedData => {
                if (updatedData.hkaPdfImage) {
                    Object.assign(data, { hkaPdfImage: updatedData.hkaPdfImage });
                    this.render(true); // Force re-render when image is loaded
                }
            });
        }
        
        return data;
    },
    
    get templateProps() {
        const receipt = this.orderData;
        if (!receipt) {
            console.warn('[HKA Debug] No receipt data available');
            return {};
        }

        console.log('[HKA Debug] Template props receipt data:', {
            hasImage: !!receipt.hkaPdfImage,
            imageStart: receipt.hkaPdfImage ? receipt.hkaPdfImage.substring(0, 50) + '...' : null,
            orderName: receipt.name,
            total: receipt.amount_total
        });

        return {
            receipt,
            orderlines: receipt.orderlines,
            paymentlines: receipt.paymentlines
        };
    }
});
