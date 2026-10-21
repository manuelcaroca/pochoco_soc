# Copyright 2026 Universidad de los Andes.
# Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: SHL-0.51


ASM_SRC := sw/game.s
HEX_OUT := sw/game.hex

ASM_MANIFEST := assembler/Cargo.toml
ASM_FILES := $(wildcard assembler/src/*.rs)

TOP := game_top
PCF := goboard.pcf

# RTL Sources (Búsqueda recursiva de archivos .v)
SRC     := $(wildcard ./rtl/*.v ./rtl/**/*.v)

# Targets
JSON    := $(TOP).json
ASC     := $(TOP).asc
BIN     := $(TOP).bin

.PHONY: all prog clean

all: prog

# Paso 0: Ensamblar código RISC-V a Hex
$(HEX_OUT): $(ASM_SRC) $(ASM_MANIFEST) $(ASM_FILES)
	cargo run --quiet --release --manifest-path $(ASM_MANIFEST) -- $(ASM_SRC) $(HEX_OUT)

# Paso 1: Síntesis con Yosys (Depende de sw/game.hex)
$(JSON): $(HEX_OUT) $(SRC)
	yosys -p "read_verilog $(SRC); synth_ice40 -top $(TOP) -json $(JSON); stat"

# Paso 2: Place and Route con NextPNR
$(ASC): $(JSON) $(PCF)
	nextpnr-ice40 --hx1k --package vq100 --json $(JSON) --pcf $(PCF) --asc $(ASC)

# Paso 3: Generación del Bitstream
$(BIN): $(ASC)
	icepack $(ASC) $(BIN)

# Paso 4: Cargar a la FPGA
prog: $(BIN)
	iceprog $(BIN)

# Limpieza sin dependencia de Python
ifeq ($(OS),Windows_NT)
clean:
	powershell -NoProfile -Command "Remove-Item -Force -ErrorAction SilentlyContinue -Path '$(HEX_OUT)','$(JSON)','$(ASC)','$(BIN)'"
else
clean:
	rm -f $(HEX_OUT) $(JSON) $(ASC) $(BIN)
	cargo clean --manifest-path $(ASM_MANIFEST)
endif
