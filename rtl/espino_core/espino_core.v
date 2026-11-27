// Copyright 2026 Universidad de los Andes.
// Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
// you may not use this file except in compliance with the License.
// SPDX-License-Identifier: SHL-0.51
//
// Course: Arquitectura de Computadores (2026)
// 
// Authors:
// - Nicolás Villegas <navillegas@miuandes.cl>

module espino_core #(
  parameter [31:0] BootAddr = 32'h0000_0000,
  parameter integer P4_HYBRID_SHIFT = 0
) (
  input  wire        clk_i,
  input  wire        rst_ni,

  output wire        instr_req_o,
  output wire [31:0] instr_addr_o,
  input  wire [31:0] instr_rdata_i,

  output wire        data_req_o,
  output wire        data_we_o,
  output wire [3:0]  data_be_o,
  output wire [31:0] data_addr_o,
  output wire [31:0] data_wdata_o,
  input  wire [31:0] data_rdata_i
);

  wire [31:0] pc_id;
  wire        instr_valid_id;

  wire        pc_set;
  wire        stall;
  wire [31:0] pc_target;
  wire        branch_taken;
  wire        jump;

  wire [3:0]  rf_raddr_a, rf_raddr_b, rf_waddr;
  wire [31:0] rf_rdata_a, rf_rdata_b, rf_wdata;
  wire        rf_we;
  wire        rf_ready;

  wire        lsu_req, lsu_we, lsu_sign, lsu_busy;
  wire [1:0]  lsu_type;
  wire [31:0] lsu_addr, lsu_wdata, lsu_rdata;

  wire        illegal_insn;

  espino_if_stage #(.BootAddr(BootAddr)) u_if (
    .clk_i            (clk_i),
    .rst_ni           (rst_ni),
    .pc_set_i         (pc_set),
    .pc_target_i      (pc_target),
    .stall_i          (stall),
    .instr_req_o      (instr_req_o),
    .instr_addr_o     (instr_addr_o),
    .pc_id_o          (pc_id),
    .instr_valid_id_o (instr_valid_id)
  );

  espino_id_stage #(.P4_HYBRID_SHIFT(P4_HYBRID_SHIFT)) u_id (
    .clk_i          (clk_i),
    .rst_ni         (rst_ni),
    .instr_valid_i  (instr_valid_id),
    .instr_rdata_i  (instr_rdata_i),
    .pc_id_i        (pc_id),
    .stall_i        (stall),
    .rf_raddr_a_o   (rf_raddr_a),
    .rf_raddr_b_o   (rf_raddr_b),
    .rf_rdata_a_i   (rf_rdata_a),
    .rf_rdata_b_i   (rf_rdata_b),
    .rf_waddr_o     (rf_waddr),
    .rf_wdata_o     (rf_wdata),
    .rf_we_o        (rf_we),
    .lsu_req_o      (lsu_req),
    .lsu_we_o       (lsu_we),
    .lsu_type_o     (lsu_type),
    .lsu_sign_o     (lsu_sign),
    .lsu_addr_o     (lsu_addr),
    .lsu_wdata_o    (lsu_wdata),
    .lsu_rdata_i    (lsu_rdata),
    .branch_taken_o (branch_taken),
    .jump_o         (jump),
    .pc_target_o    (pc_target),
    .rf_ready_o     (rf_ready),
    .illegal_insn_o (illegal_insn)
  );

  espino_register_file u_rf (
    .clk_i     (clk_i),
    .rst_ni    (rst_ni),
    .raddr_a_i (rf_raddr_a),
    .rdata_a_o (rf_rdata_a),
    .raddr_b_i (rf_raddr_b),
    .rdata_b_o (rf_rdata_b),
    .waddr_i   (rf_waddr),
    .wdata_i   (rf_wdata),
    .we_i      (rf_we)
  );

  espino_load_store_unit u_lsu (
    .clk_i        (clk_i),
    .rst_ni       (rst_ni),
    .req_i        (lsu_req),
    .we_i         (lsu_we),
    .type_i       (lsu_type),
    .sign_i       (lsu_sign),
    .addr_i       (lsu_addr),
    .wdata_i      (lsu_wdata),
    .rdata_o      (lsu_rdata),
    .busy_o       (lsu_busy),
    .data_req_o   (data_req_o),
    .data_we_o    (data_we_o),
    .data_be_o    (data_be_o),
    .data_addr_o  (data_addr_o),
    .data_wdata_o (data_wdata_o),
    .data_rdata_i (data_rdata_i)
  );

  espino_controller u_ctrl (
    .instr_valid_i  (instr_valid_id),
    .rf_ready_i     (rf_ready),
    .branch_taken_i (branch_taken),
    .jump_i         (jump),
    .lsu_busy_i     (lsu_busy),
    .pc_set_o       (pc_set),
    .stall_o        (stall)
  );

endmodule