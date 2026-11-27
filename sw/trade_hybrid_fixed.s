# Selector causal entre bandas fijas y adaptativas. Tres solicitudes por giro.
# x12 minimo, x13 maximo, x14 contador de muestras (saturado a 16384), x15 amplitud.
# x2 base SPI; x3 fase (0 buscar compra, 1 buscar venta);
# x4 zona activada; x5 extremo observado; x6 repeticiones restantes;
# x7 orden anterior; x8 precio actual; x9 temporal; x10 orden nueva.
# La maestra limita la cantidad por caja o acciones en cada ejecución.
.section .text
.global _start
_start:
    lui x2, 0x80010
    addi x3, x0, 0
    addi x4, x0, 0
    addi x6, x0, 0
    addi x7, x0, 0
    addi x12, x0, 256
    addi x13, x0, 0
    addi x14, x0, 0
    addi x11, x0, 0       # modo: 0 fijo, 1 adaptativo
    addi x1, x0, 0        # precio previo durante la calibracion
    sw x0, 2000(x0)       # suma de diferencias absolutas en los primeros 2048 ticks
esperar:
    lw x9, 0(x2)
    andi x9, x9, 1
    beq x9, x0, esperar
    lw x8, 4(x2)
    addi x10, x0, 0
    bltu x8, x12, nuevo_minimo
    jal x0, ver_maximo
nuevo_minimo:
    addi x12, x8, 0
ver_maximo:
    bltu x13, x8, nuevo_maximo
    jal x0, rango
nuevo_maximo:
    addi x13, x8, 0
rango:
    sub x15, x13, x12
    lui x9, 4
    beq x9, x14, modo
    addi x14, x14, 1
    lui x9, 1
    addi x9, x9, -2048
    bltu x9, x14, modo
    beq x1, x0, guardar_previo
    bltu x8, x1, bajada
    sub x9, x8, x1
    jal x0, acumular
bajada:
    sub x9, x1, x8
acumular:
    lw x10, 2000(x0)
    add x10, x10, x9
    sw x10, 2000(x0)
guardar_previo:
    addi x1, x8, 0
modo:
    addi x10, x0, 0
    addi x9, x0, 100
    bltu x12, x9, adapt
    addi x9, x0, 150
    bltu x9, x12, zona_faltante
    addi x9, x0, 225
    bltu x13, x9, zona_faltante
    jal x0, aplicar_modo
zona_faltante:
    lui x9, 4
    beq x14, x9, adapt
    lui x9, 1
    addi x9, x9, -2048
    bltu x14, x9, aplicar_modo
    lw x9, 2000(x0)
    addi x10, x0, 682
    bltu x10, x9, fijo
adapt:
    addi x10, x0, 1
    jal x0, aplicar_modo
fijo:
    addi x10, x0, 0
aplicar_modo:
    beq x10, x11, mismo_modo
    addi x4, x0, 0
    addi x11, x10, 0
mismo_modo:
    addi x10, x0, 0
    bne x6, x0, repetir
    beq x11, x0, evaluar_zona
    addi x9, x0, 128
    bltu x14, x9, publicar
    addi x9, x0, 8
    bltu x15, x9, publicar
evaluar_zona:
    bne x3, x0, buscar_venta
    bne x4, x0, seguir_minimo
    bne x11, x0, compra_relativa
    addi x9, x0, 150
    bltu x9, x8, publicar
    jal x0, activar
compra_relativa:
    sub x9, x8, x12
    slli x9, x9, 3       # escala adaptativa especializada
    bltu x15, x9, publicar
    jal x0, activar
seguir_minimo:
    bltu x8, x5, extender
    sub x9, x8, x5
    bne x11, x0, relativo_comprar
    addi x10, x0, 8
    bltu x9, x10, mantener
    jal x0, comprar
relativo_comprar:
    # Confirmar cuando 32 veces el giro alcanza la amplitud.
    slli x9, x9, 5       # escala adaptativa especializada
    bltu x9, x15, publicar
comprar:
    addi x10, x0, 127
    addi x3, x0, 1
    jal x0, iniciar_serie
buscar_venta:
    bne x4, x0, seguir_maximo
    bne x11, x0, venta_relativa
    addi x9, x0, 225
    bltu x8, x9, publicar
    jal x0, activar
venta_relativa:
    sub x9, x13, x8
    slli x9, x9, 2       # escala adaptativa especializada
    bltu x15, x9, publicar
activar:
    addi x4, x0, 1
extender:
    addi x5, x8, 0
    jal x0, publicar
seguir_maximo:
    bltu x5, x8, extender
    sub x9, x5, x8
    bne x11, x0, relativo_vender
    addi x10, x0, 8
    bltu x9, x10, mantener
    jal x0, vender
relativo_vender:
    # Confirmar cuando 32 veces el giro alcanza la amplitud.
    slli x9, x9, 5       # escala adaptativa especializada
    bltu x9, x15, publicar
vender:
    addi x10, x0, 191
    addi x3, x0, 0
iniciar_serie:
    addi x4, x0, 0
    addi x6, x0, 2
    jal x0, publicar
repetir:
    addi x10, x7, 0
    addi x6, x6, -1
    jal x0, publicar
mantener:
    addi x10, x0, 0
publicar:
    addi x7, x10, 0
    sw x10, 8(x2)
    jal x0, esperar
