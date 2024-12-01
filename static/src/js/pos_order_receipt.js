/** @odoo-module */
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";
import { useState, Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Configure PDF.js worker
if (window.pdfjsLib) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

// Define a custom receipt component
class CustomReceiptTemplate extends Component {
    static template = 'point_of_sale.OrderReceipt';
    static props = {
        data: { type: Object, optional: true },
        order: { type: Object, optional: true },
        receipt: { type: Object, optional: true },
        orderlines: { type: Array, optional: true },
        paymentlines: { type: Array, optional: true }
    };
}

patch(OrderReceipt.prototype, {
    setup() {
        super.setup();
        this.state = useState({
            template: true,
            hkaPdfData: null,
            hkaPdfImage: null,
            error: null
        });
        this.pos = useState(useService("pos"));
        this.rpc = useService("rpc");
        
        // Initial fetch for the current order
        this.fetchInvoiceData();
    },
    
    get orderData() {
        if (this.props.data) {
            return this.props.data;
        }
        const currentOrder = this.pos.get_order();
        return currentOrder ? currentOrder.export_for_printing() : null;
    },
    
    async fetchInvoiceData() {
        console.log('[HKA Debug] Starting fetchInvoiceData');
        console.log('[HKA Debug] props:', this.props);
        console.log('[HKA Debug] Order data:', this.orderData);
        console.log('[HKA Debug] Current state:', this.state);
        
        if (!this.orderData) {
            console.log('[HKA Debug] No valid order data found');
            this.state.error = 'No valid order data found';
            return;
        }
        
        // Use the appropriate reference based on the order data
        const orderRef = this.orderData.pos_reference || this.orderData.name;
        if (!orderRef) {
            console.log('[HKA Debug] No valid reference found in order data');
            this.state.error = 'No valid reference found in order data';
            return;
        }
        
        console.log('[HKA Debug] Searching for POS order:', orderRef);
        try {
            const invoiceResult = await this.rpc("/pos/get_order_invoice", {
                pos_reference: orderRef,
            });
            console.log('[HKA Debug] Order invoice info:', invoiceResult);
            
            if (invoiceResult?.invoice_id) {
                const pdfResult = await this.rpc("/pos/get_hka_pdf", {
                    invoice_id: invoiceResult.invoice_id,
                });
                console.log('[HKA Debug] PDF result:', pdfResult);
                
                if (pdfResult?.success && pdfResult?.pdf_data) {
                    console.log('[HKA Debug] Received PDF data, length:', pdfResult.pdf_data.length);
                    this.state.hkaPdfData = pdfResult.pdf_data;
                    if (window.pdfjsLib) {
                        await this.convertPdfToImage(pdfResult.pdf_data);
                    } else {
                        console.warn('[HKA Debug] PDF.js not loaded, falling back to iframe display');
                    }
                    this.state.error = null;
                } else {
                    console.error('[HKA Debug] No PDF data in response:', pdfResult?.error || 'Unknown error');
                    this.state.error = pdfResult?.error || 'No PDF data available';
                    this.state.hkaPdfData = null;
                    this.state.hkaPdfImage = null;
                }
            } else {
                console.error('[HKA Debug] No invoice found:', invoiceResult?.error || 'Unknown error');
                this.state.error = invoiceResult?.error || 'No invoice found for this order';
                this.state.hkaPdfData = null;
                this.state.hkaPdfImage = null;
            }
        } catch (error) {
            console.error('[HKA Debug] Error:', error);
            this.state.error = error.message || 'Failed to fetch invoice data';
            this.state.hkaPdfData = null;
        }
        
        console.log('[HKA Debug] Final state after fetch:', this.state);
    },

    async convertPdfToImage(pdfData) {
        try {
            if (!window.pdfjsLib) {
                throw new Error('PDF.js library not loaded');
            }

            // Convert base64 to array buffer
            const pdfBytes = atob(pdfData);
            const pdfArray = new Uint8Array(pdfBytes.length);
            for (let i = 0; i < pdfBytes.length; i++) {
                pdfArray[i] = pdfBytes.charCodeAt(i);
            }

            // Load the PDF document
            const loadingTask = window.pdfjsLib.getDocument({ data: pdfArray });
            const pdf = await loadingTask.promise;
            
            // Get the first page
            const page = await pdf.getPage(1);
            
            // Set the scale for rendering (adjust as needed)
            const viewport = page.getViewport({ scale: 2.0 });
            
            // Create a canvas element
            const canvas = document.createElement('canvas');
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            
            // Render the PDF page to the canvas
            const context = canvas.getContext('2d');
            const renderContext = {
                canvasContext: context,
                viewport: viewport
            };
            
            await page.render(renderContext).promise;
            
            // Convert canvas to image data URL
            this.state.hkaPdfImage = canvas.toDataURL('image/png');
            console.log('[HKA Debug] PDF converted to image successfully');
        } catch (error) {
            console.error('[HKA Debug] Error converting PDF to image:', error);
            this.state.error = 'Failed to convert PDF to image';
            this.state.hkaPdfImage = null;
        }
    },
    
    get templateProps() {
        const receipt = this.pos.get_order().export_for_printing();
        const receiptWithPdf = {
            ...receipt,
            hkaPdfData: this.state.hkaPdfData,
            hkaPdfImage: this.state.hkaPdfImage
        };

        console.log('[HKA Debug] Template props:', {
            hkaPdfDataInState: !!this.state.hkaPdfData,
            hkaPdfDataInReceipt: !!receiptWithPdf.hkaPdfData,
        });

        return {
            data: this.props.data,
            order: this.pos.orders,
            receipt: receiptWithPdf,
            orderlines: this.pos.get_order().get_orderlines(),
            paymentlines: this.pos.get_order().get_paymentlines()
        };
    },

    get templateComponent() {
        return CustomReceiptTemplate;
    }
});
