/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";
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
            l10n_pa_distrito_id: partner?.l10n_pa_distrito_id || false,
            l10n_pa_corregimiento_id: partner?.l10n_pa_corregimiento_id || false,
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
            l10n_pa_distrito_id: this.partner?.l10n_pa_distrito_id || false,
            l10n_pa_corregimiento_id: this.partner?.l10n_pa_corregimiento_id || false,
            ruc_verified: this.partner?.ruc_verified || false,
            ruc_verification_date: this.partner?.ruc_verification_date || false,
        };
    },
});