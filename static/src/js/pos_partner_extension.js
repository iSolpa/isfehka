/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";
import { PartnerDetailsEdit } from "@point_of_sale/app/screens/partner_list/partner_editor/partner_editor";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useState, onMounted, useEffect } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

console.log("[ISFEHKA] Loading partner RUC extension");

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);
        
        if (loadedData['res.distrito.pa']) {
            this.distritos = loadedData['res.distrito.pa'];
            console.log("[ISFEHKA] Loaded distritos:", this.distritos);
        }

        if (loadedData['res.corregimiento.pa']) {
            this.corregimientos = loadedData['res.corregimiento.pa'];
            console.log("[ISFEHKA] Loaded corregimientos:", this.corregimientos);
        }
    }
});

patch(PartnerListScreen.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        const partner = this.props.partner || {};
        this.changes = {
            ...this.changes,
            ruc: partner?.ruc || '',
            dv: partner?.dv || '',
            tipo_contribuyente: partner?.tipo_contribuyente || '',
            tipo_cliente_fe: partner?.tipo_cliente_fe || '',
            l10n_pa_distrito_id: partner?.l10n_pa_distrito_id || '',
            l10n_pa_corregimiento_id: partner?.l10n_pa_corregimiento_id || '',
            ruc_verified: partner?.ruc_verified || false,
            ruc_verification_date: partner?.ruc_verification_date || false,
        };
        console.log("[ISFEHKA] PartnerListScreen setup called with partner:", partner);
    },

    getPartnerFields() {
        const fields = super.getPartnerFields();
        return {
            ...fields,
            ruc: this.partner?.ruc || '',
            dv: this.partner?.dv || '',
            tipo_contribuyente: this.partner?.tipo_contribuyente || '',
            tipo_cliente_fe: this.partner?.tipo_cliente_fe || '',
            l10n_pa_distrito_id: this.partner?.l10n_pa_distrito_id?.[0] || '',
            l10n_pa_corregimiento_id: this.partner?.l10n_pa_corregimiento_id?.[0] || '',
            ruc_verified: this.partner?.ruc_verified || false,
            ruc_verification_date: this.partner?.ruc_verification_date || false,
        };
    },
});

patch(PartnerDetailsEdit.prototype, {
    setup() {
        super.setup();
        const partner = this.props.partner;
        this.pos = usePos();
        
        // Initialize the changes state with custom fields
        this.changes = useState({
            ...this.changes,
            ruc: partner.ruc || "",
            dv: partner.dv || "",
            tipo_contribuyente: partner.tipo_contribuyente || "",
            tipo_cliente_fe: partner.tipo_cliente_fe || "",
            street: partner.street || "",
            l10n_pa_distrito_id: partner.l10n_pa_distrito_id && partner.l10n_pa_distrito_id[0],
            l10n_pa_corregimiento_id: partner.l10n_pa_corregimiento_id && partner.l10n_pa_corregimiento_id[0],
            ruc_verified: partner.ruc_verified || false,
            ruc_verification_date: partner.ruc_verification_date || false,
        });

        // Initialize filtered districts
        this.state = useState({
            filteredDistritos: [],
        });

        // Watch for state changes
        this._watchStateChanges();
    },

    getPartnerFields() {
        const fields = super.getPartnerFields();
        return {
            ...fields,
            ruc: this.partner?.ruc || '',
            dv: this.partner?.dv || '',
            tipo_contribuyente: this.partner?.tipo_contribuyente || '',
            tipo_cliente_fe: this.partner?.tipo_cliente_fe || '',
            l10n_pa_distrito_id: this.partner?.l10n_pa_distrito_id?.[0] || '',
            l10n_pa_corregimiento_id: this.partner?.l10n_pa_corregimiento_id?.[0] || '',
            ruc_verified: this.partner?.ruc_verified || false,
            ruc_verification_date: this.partner?.ruc_verification_date || false,
        };
    },

    formatDateTime(date) {
        if (!date) return false;
        const d = new Date(date);
        return d.getFullYear() + '-' + 
               String(d.getMonth() + 1).padStart(2, '0') + '-' +
               String(d.getDate()).padStart(2, '0') + ' ' +
               String(d.getHours()).padStart(2, '0') + ':' +
               String(d.getMinutes()).padStart(2, '0') + ':' +
               String(d.getSeconds()).padStart(2, '0');
    },

    _watchStateChanges() {
        onMounted(() => {
            this._updateDistritosByState(this.changes.state_id);
        });

        // Watch for state_id changes
        useEffect(
            () => {
                this._updateDistritosByState(this.changes.state_id);
            },
            () => [this.changes.state_id]
        );

        // Watch for RUC changes
        useEffect(
            () => {
                if (this.changes.ruc !== this.props.partner.ruc) {
                    this.changes.ruc_verified = false;
                    this.changes.ruc_verification_date = false;
                    // Clear DV if RUC is cleared or changed
                    if (!this.changes.ruc) {
                        this.changes.dv = '';
                    }
                }
            },
            () => [this.changes.ruc]
        );
    },

    _updateDistritosByState(stateId) {
        if (!stateId) {
            this.state.filteredDistritos = [];
            // Clear distrito and corregimiento when state is cleared
            this.changes.l10n_pa_distrito_id = false;
            this.changes.l10n_pa_corregimiento_id = false;
            return;
        }

        // Filter distritos by state
        this.state.filteredDistritos = (this.pos.distritos || []).filter(
            distrito => distrito.state_id && distrito.state_id[0] === parseInt(stateId)
        );

        // If current distrito is not in filtered list, clear it
        if (this.changes.l10n_pa_distrito_id) {
            const isValidDistrito = this.state.filteredDistritos.some(
                d => d.id === parseInt(this.changes.l10n_pa_distrito_id)
            );
            if (!isValidDistrito) {
                this.changes.l10n_pa_distrito_id = false;
                this.changes.l10n_pa_corregimiento_id = false;
            }
        }
    },

    async verifyRUC() {
        console.log("[ISFEHKA] Starting RUC verification");
        console.log("[ISFEHKA] Initial verification state:", {
            ruc: this.changes.ruc,
            ruc_verified: this.changes.ruc_verified,
            ruc_verification_date: this.changes.ruc_verification_date,
            dv: this.changes.dv
        });
        
        if (!this.changes.ruc || !this.changes.tipo_contribuyente) {
            this.pos.env.services.notification.add(
                _t('Por favor ingrese el RUC y tipo de contribuyente'),
                { type: 'danger' }
            );
            return;
        }

        // Handle Consumidor Final case
        if (this.changes.ruc === 'CF') {
            this.changes.ruc_verified = true;
            this.changes.dv = '00';
            this.changes.tipo_cliente_fe = '02';
            if (!this.props.partner.id) {  // Only set name if it's a new partner
                this.changes.name = 'CONSUMIDOR FINAL';
            }
            this.changes.ruc_verification_date = this.formatDateTime(new Date());
            
            console.log("[ISFEHKA] After CF verification:", {
                ruc: this.changes.ruc,
                ruc_verified: this.changes.ruc_verified,
                ruc_verification_date: this.changes.ruc_verification_date,
                dv: this.changes.dv
            });

            this.pos.env.services.notification.add(
                _t('Cliente Consumidor Final verificado'),
                { type: 'success' }
            );
            return;
        }

        try {
            const result = await this.pos.env.services.orm.call(
                'hka.service',
                'verify_ruc',
                [this.changes.ruc, this.changes.tipo_contribuyente]
            );

            if (result.success) {
                this.changes.ruc_verified = true;
                this.changes.dv = result.data.dv || '';
                if (!this.props.partner.id && result.data.razonSocial) {
                    this.changes.name = result.data.razonSocial;
                }
                this.changes.ruc_verification_date = this.formatDateTime(new Date());

                console.log("[ISFEHKA] After successful verification:", {
                    ruc: this.changes.ruc,
                    ruc_verified: this.changes.ruc_verified,
                    ruc_verification_date: this.changes.ruc_verification_date,
                    dv: this.changes.dv
                });

                this.pos.env.services.notification.add(
                    _t('RUC verificado exitosamente'),
                    { type: 'success' }
                );
            } else {
                this.changes.ruc_verified = false;
                this.changes.ruc_verification_date = false;
                
                console.log("[ISFEHKA] After failed verification:", {
                    ruc: this.changes.ruc,
                    ruc_verified: this.changes.ruc_verified,
                    ruc_verification_date: this.changes.ruc_verification_date,
                    dv: this.changes.dv
                });

                this.pos.env.services.notification.add(
                    result.message || _t('Error al verificar RUC'),
                    { type: 'danger' }
                );
            }
        } catch (error) {
            console.error("[ISFEHKA] Verification error:", error);
            this.changes.ruc_verified = false;
            this.changes.ruc_verification_date = false;
            
            console.log("[ISFEHKA] After error in verification:", {
                ruc: this.changes.ruc,
                ruc_verified: this.changes.ruc_verified,
                ruc_verification_date: this.changes.ruc_verification_date,
                dv: this.changes.dv
            });

            this.pos.env.services.notification.add(
                error.message || _t('Error al verificar RUC'),
                { type: 'danger' }
            );
        }
    },

    saveChanges() {
        console.log("[ISFEHKA] Starting saveChanges");
        console.log("[ISFEHKA] Initial this.changes:", {
            ruc: this.changes.ruc,
            ruc_verified: this.changes.ruc_verified,
            ruc_verification_date: this.changes.ruc_verification_date,
            dv: this.changes.dv
        });
        
        const processedChanges = {};
        const partnerId = this.props.partner?.id;
        
        // If we have a partner ID, ensure it's included in the changes
        if (partnerId) {
            processedChanges.id = partnerId;
        }
        
        // Process all changes
        for (const [key, value] of Object.entries(this.changes)) {
            if (this.intFields.includes(key)) {
                processedChanges[key] = parseInt(value) || false;
            } else {
                processedChanges[key] = value;
            }
        }

        console.log("[ISFEHKA] After processing changes - verification fields:", {
            ruc: processedChanges.ruc,
            ruc_verified: processedChanges.ruc_verified,
            ruc_verification_date: processedChanges.ruc_verification_date,
            dv: processedChanges.dv
        });
        
        // Handle required fields
        if (!partnerId && !processedChanges.name) {
            this.pos.env.services.notification.add(
                _t("Please enter a customer name before saving."),
                { type: 'danger' }
            );
            return false;
        }

        // Validate required fields for facturación electrónica when RUC is present
        if (processedChanges.ruc && processedChanges.ruc !== 'CF') {
            if (!processedChanges.ruc_verified) {
                this.pos.env.services.notification.add(
                    _t("Por favor verifique el RUC antes de guardar"),
                    { type: 'danger' }
                );
                return false;
            }
            if (!processedChanges.dv) {
                this.pos.env.services.notification.add(
                    _t("El DV es requerido para clientes con RUC"),
                    { type: 'danger' }
                );
                return false;
            }
            if (!processedChanges.tipo_contribuyente) {
                this.pos.env.services.notification.add(
                    _t("El tipo de contribuyente es requerido para clientes con RUC"),
                    { type: 'danger' }
                );
                return false;
            }
            if (!processedChanges.tipo_cliente_fe) {
                this.pos.env.services.notification.add(
                    _t("El tipo de cliente FE es requerido para clientes con RUC"),
                    { type: 'danger' }
                );
                return false;
            }
        }
        
        console.log("[ISFEHKA] Saving partner with ID:", partnerId, "Changes:", processedChanges);
        
        // Call parent's saveChanges with our processed changes
        const result = this.props.saveChanges(processedChanges);
        
        // Update local partner data if save was successful
        if (result !== false && partnerId) {
            const partner = this.pos.partners.find(p => p.id === partnerId);
            if (partner) {
                Object.assign(partner, processedChanges);
            }
        }
        
        return result;
    },
});