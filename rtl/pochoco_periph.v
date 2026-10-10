// Copyright 2026 Universidad de los Andes.
// Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
// you may not use this file except in compliance with the License.
// SPDX-License-Identifier: SHL-0.51
//
// Course: Arquitectura de Computadores (2026)
// 
// Authors:
// - Nicolás Villegas <navillegas@miuandes.cl>

module pochoco_periph (
    input  wire        clk_i,
    input  wire        rst_ni,
    input  wire        sel_i,
    input  wire        req_i,
    input  wire        we_i,
    input  wire [7:0]  addr_i,
    input  wire [31:0] wdata_i,
    output reg  [31:0] rdata_o,
    output wire [3:0]  leds_o,
    input  wire [3:0]  btn_i,
    output wire [6:0]  seg1_o,
    output wire [6:0]  seg2_o
);

    wire [5:0] off    = addr_i[7:2];
    wire       access = sel_i & req_i;

    // Registros MMIO
    reg [3:0]  led_q;
    reg [7:0]  digit_q;
    reg [31:0] cycle_cnt_q;

    // 1. Contador libre de ciclos (32 bits @ 25 MHz)
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni)
            cycle_cnt_q <= 32'd0;
        else
            cycle_cnt_q <= cycle_cnt_q + 32'd1;
    end

    // 2. Escritura MMIO
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            led_q   <= 4'b0;
            digit_q <= 8'b0;
        end else if (access & we_i) begin
            case (off)
                6'd0: digit_q <= wdata_i[7:0]; // Offset 0x00 (Displays 7-seg)
                6'd1: led_q   <= wdata_i[3:0]; // Offset 0x04 (LEDs)
                default: ;
            endcase
        end
    end

    // 3. Lectura MMIO (Sincrónica)
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            rdata_o <= 32'b0;
        end else if (access & ~we_i) begin
            case (off)
                6'd0: rdata_o <= {24'b0, digit_q};     // Offset 0x00
                6'd1: rdata_o <= {28'b0, led_q};       // Offset 0x04
                6'd2: rdata_o <= {28'b0, btn_i};       // Offset 0x08 (Botones)
                6'd3: rdata_o <= cycle_cnt_q;           // Offset 0x0C (Contador de Ciclos)
                default: rdata_o <= 32'b0;
            endcase
        end
    end

    assign leds_o = led_q;

    // Decodificador Hex a 7-segmentos (Activo Alto)
    function [6:0] hex2seg;
        input [3:0] hex;
        begin
            case (hex)
                4'h0: hex2seg = 7'b0111111; // 0
                4'h1: hex2seg = 7'b0000110; // 1
                4'h2: hex2seg = 7'b1011011; // 2
                4'h3: hex2seg = 7'b1001111; // 3
                4'h4: hex2seg = 7'b1100110; // 4
                4'h5: hex2seg = 7'b1101101; // 5
                4'h6: hex2seg = 7'b1111101; // 6
                4'h7: hex2seg = 7'b0000111; // 7
                4'h8: hex2seg = 7'b1111111; // 8
                4'h9: hex2seg = 7'b1101111; // 9
                4'hA: hex2seg = 7'b1110111; // A
                4'hB: hex2seg = 7'b1111100; // b
                4'hC: hex2seg = 7'b0111001; // C
                4'hD: hex2seg = 7'b1011110; // d
                4'hE: hex2seg = 7'b1111001; // E
                4'hF: hex2seg = 7'b1110001; // F
                default: hex2seg = 7'b0000000;
            endcase
        end
    endfunction

    assign seg1_o = hex2seg(digit_q[7:4]);
    assign seg2_o = hex2seg(digit_q[3:0]);

endmodule