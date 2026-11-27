# Pochoco Trader — estrategia híbrida, Proyecto 4

Versión base auditada: `82c0cad21d62519c701f3cf382397c8757df95ba` (rama `Proyecto-4`). El código original `sw/trade.s` no se modifica. La referencia correcta es `sw/hibrido.py`, que importa las funciones de contabilidad de `sw/reference.py`; no ejecutar `reference.py` como estrategia híbrida.

## Cierre reproducible

Desde la raíz, con Python 3, Rust/Cargo, Yosys, nextpnr-ice40, icepack, Icarus Verilog (o Verilator reciente):

```bash
export YOSYS_CELLS_SIM=/usr/share/yosys/ice40/cells_sim.v
python3 -u tools/cierre_p4.py --jobs 3
```

El banco detecta Verilator y, si falla, reintenta con Icarus; para usar Icarus directamente, añadir `--engine iverilog`. `--preparar` sólo genera fuentes; `--solo-isa` verifica los binarios ensamblados sin simular RTL ni sintetizar. El script está diseñado para un checkout de la versión auditada, no para mezclarlo con la rama de la estrategia robusta anterior.

Produce en `bench_p4_final/` los bitstreams, logs de herramientas, CSV de decisiones, métricas por tick, perfiles PC, `resumen.json` y `versiones.txt`. `BITSTREAM_ELEGIDO.txt` existe únicamente si una variante pasó síntesis y ambas simulaciones. El script no programa la placa ni hace push. Si se produce un fallo, revisar `errores.txt` y los logs; los resultados que sí pasaron quedan registrados. No confundir resultados de las versiones anteriores.

### Referencia Python

```bash
python3 sw/hibrido.py practica_meta.csv
python3 sw/hibrido.py series/practica_tesla_2022.csv
```

Todas las decisiones usan sólo precios ya recibidos; los CSV son entradas del testbench y no se cargan en la FPGA.

### Ensamblado manual (después de preparar las variantes)

```bash
cargo run --quiet --release --manifest-path assembler/Cargo.toml -- sw/trade.s sw/trade.hex
cargo run --quiet --release --manifest-path assembler/Cargo.toml -- sw/trade_hybrid_fixed.s sw/trade_hybrid_fixed.hex
cargo run --quiet --release --manifest-path assembler/Cargo.toml -- sw/trade_hybrid_compact.s sw/trade_hybrid_compact.hex
```

### Síntesis manual (ejemplo COMPACT)

```bash
yosys -p 'read_verilog rtl/*.v rtl/espino_core/*.v; synth_ice40 -top trade_top_compact -json compact.json; stat'
nextpnr-ice40 --hx1k --package vq100 --freq 25 --json compact.json --pcf goboard.pcf --asc compact.asc
icepack compact.asc compact.bin
```

SW usa `trade_top`, FIXED `trade_top_fixed`, COMPACT `trade_top_compact`. FIXED añade SLLI 2/3/5 especializado en diferencias de precios de 8 bits; COMPACT suma RAM de 128 palabras. No es un shifter RV32E general. El acumulador se ubica en 508 y el código ocupa 119 palabras.

### Testbench manual (COMPACT, serie Meta)

```bash
mkdir -p bench_p4_final/manual
iverilog -g2012 -s tb_p4_final -DP4_COMPACT -Ptb_p4_final.NTICKS=20000 -o /tmp/p4.vvp "$YOSYS_CELLS_SIM" rtl/*.v rtl/espino_core/*.v tb_p4_final.sv
vvp -n /tmp/p4.vvp +SERIES=practica_meta.csv +DECISIONS=bench_p4_final/manual/decisiones.csv +METRICS=bench_p4_final/manual/metricas.csv +PCSTATS=bench_p4_final/manual/pc.csv
```

Para SW, retirar `-DP4_COMPACT`; para FIXED, cambiarlo por `-DP4_FIXED`. El banco automatizado es preferible porque compara cada decisión y la cartera contra Python, incluso el último byte escrito.

### Programar Go Board (sólo después de validar)

```bash
cat bench_p4_final/BITSTREAM_ELEGIDO.txt
iceprog "$(cat bench_p4_final/BITSTREAM_ELEGIDO.txt)"
iceprog -c "$(cat bench_p4_final/BITSTREAM_ELEGIDO.txt)"
```

No usar `make prog` para programar una variante elegida: ese objetivo original usa SW. En PowerShell, `usbipd list`, `usbipd bind --busid <BUSID>` (administrador, si aún no está compartido), `usbipd attach --wsl --busid <BUSID>`; en WSL, `lsusb` debe mostrar el FTDI (p. ej. 0403:6010).

### Evidencia e informe externo

El banco escribe el fragmento LaTeX en `../<nombre-del-checkout>_informe/seccion_3_3.txt`, fuera del repositorio. Copiar al informe existente; no se incorpora ningún `.tex` a Git. Para el roofline, añadir `\usepackage{pgfplots}` y `\pgfplotsset{compat=1.18}` al preámbulo de Overleaf. Las versiones reales están en `bench_p4_final/versiones.txt`. Los techos roofline son teóricos y se definen para el tráfico nominal de instrucciones del escalado, no el ancho de banda medido de RAM.

Conservar `resumen.json`, `versiones.txt`, los CSV de decisiones, métricas y perfiles, y los logs de síntesis y simulación. No agregar los directorios `obj_*`, netlists, ejecutables de simulación ni bitstreams generados. Los CSV de las series sirven exclusivamente de entradas de prueba, nunca de memoria de precios del agente.
