/*
    POS Datalogic Scale module for Odoo
    Copyright (C) 2016 Mathieu VATEL
    @author: Mathieu VATEL
    The licence is in the file __openerp__.py
*/

odoo.define('pos_scale_datalogic.pos_scale_datalogic', function (require) {
    "use strict";

    var screens = require('point_of_sale.screens');
    var models = require('point_of_sale.models');
    var devices = require('point_of_sale.devices');
    var gui = require('point_of_sale.gui');
    var core = require('web.core');
    var _t = core._t;
    var QWeb = core.qweb;

    screens.ProductScreenWidget.include({

        click_product: function(product) {
            var self = this;
            if(product.to_weight && (this.pos.config.iface_scale_datalogic || this.pos.config.iface_electronic_scale)){
                this.gui.show_screen('scale', {product: product});
            } else {
                this.pos.get_order().add_product(product);
            }
        },

    });

    devices.ProxyDevice.include({
        // returns the weight on the scale.
        scale_read: function(){
            var self = this;
            var ret = new $.Deferred();
            if (self.use_debug_weight) {
                return (new $.Deferred()).resolve({weight:this.debug_weight, unit:'Kg', info:'ok'});
            }
            if (self.pos.config.iface_scale_datalogic) {
                this.message('scale_datalogic_read',{})
                    .then(function(weight){
                        ret.resolve(weight);
                    }, function(){ //failed to read weight
                        ret.resolve({weight:0.0, unit:'Kg', info:'ok'});
                    });
            } else {
                this.message('scale_read',{})
                    .then(function(weight){
                        ret.resolve(weight);
                    }, function(){ //failed to read weight
                        ret.resolve({weight:0.0, unit:'Kg', info:'ok'});
                    });
            }
            return ret;
        },
    });

    // TODO: Check if needed: Case the casher is scanning a product and
    // the product need to be weight so directly open the screen "scale"
//    models.PosModel = models.PosModel.extend({
//        scan_product: function(parsed_code){
//            var self = this;
//            var selectedOrder = this.get_order();       
//            var product = this.db.get_product_by_barcode(parsed_code.base_code);
//            if(!product){
//                return false;
//            }
//            if(parsed_code.type === 'price'){
//                selectedOrder.add_product(product, {price:parsed_code.value});
//            }else if(parsed_code.type === 'weight'){
//                selectedOrder.add_product(product, {quantity:parsed_code.value, merge:false});
//            }else if(parsed_code.type === 'discount'){
//                selectedOrder.add_product(product, {discount:parsed_code.value, merge:false});
//            }else{
//                if (product.to_weight && this.config.iface_scale_datalogic) {
//                    this.gui.show_screen('scale', {product: product});
//                }else {
//                    selectedOrder.add_product(product);
//                }
//            }
//            return true;
//        },
//    });

});
