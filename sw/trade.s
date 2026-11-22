# Agente Pochoco Trader para Espino RV32E.
#
# Regla: compara el precio actual con el promedio de los cinco precios
# anteriores. H_compra = 7 y H_venta = 7 unidades de precio. Compra 63 si está
# fuera del mercado y el precio supera el promedio por más de H_compra; vende
# 63 si tiene acciones y cae bajo el promedio por más de H_venta. La FPGA limita
# cada orden a la caja o a las acciones disponibles.
#
# DECISION se transmite en el tick siguiente. Por eso, al recibir un precio,
# primero se aplica al registro local la decisión pendiente al precio actual,
# y luego se calcula y escribe la nueva decisión.
#
# Copia local de la cartera y estado en RAM (NumWords=512):
#   0x7D8 caja, 0x7DC acciones, 0x7E0-0x7F0 ventana de 5 precios,
#   0x7F4 cantidad de precios válidos, 0x7F8 índice circular,
#   0x7FC decisión pendiente.

.section .text
.global _start

_start:
    lui  x2, 0x80010          # Base SPI: 0x80010000
    addi x14, x0, 2008        # Base del estado: 0x7D8

    lui  x3, 0x2
    addi x3, x3, 1808         # Caja inicial = 10.000
    sw   x3, 0(x14)
    sw   x0, 4(x14)           # Acciones iniciales = 0
    sw   x0, 28(x14)          # Precios válidos = 0
    sw   x0, 32(x14)          # Índice de ventana = 0
    sw   x0, 36(x14)          # Decisión pendiente = mantener

wait_price:
    lw   x5, 0(x2)            # STATUS: bit 0 = precio nuevo
    andi x5, x5, 1
    beq  x5, x0, wait_price
    lw   x8, 4(x2)            # PRICE; la lectura limpia el indicador

# Aplicar la decisión transmitida en el tick anterior al precio actual.
    lw   x3, 0(x14)           # Caja local
    lw   x4, 4(x14)           # Acciones locales
    lw   x5, 36(x14)          # Decisión pendiente
    addi x6, x0, 127          # 0x7F = comprar hasta 63
    beq  x5, x6, apply_buy
    addi x6, x0, 191          # 0xBF = vender hasta 63
    beq  x5, x6, apply_sell
    jal  x0, after_order

apply_buy:
    addi x7, x0, 5            # Comisión
    bltu x3, x7, after_order  # Sin caja para pagar la comisión
    sub  x7, x3, x7           # Caja disponible para acciones
    addi x9, x0, 0            # Cantidad ejecutada
    addi x10, x0, 63

buy_quantity_loop:
    beq  x9, x10, buy_done
    bltu x7, x8, buy_done     # La caja restante no alcanza para otra
    sub  x7, x7, x8
    addi x9, x9, 1
    jal  x0, buy_quantity_loop

buy_done:
    beq  x9, x0, after_order
    sw   x7, 0(x14)           # Resto = caja - comisión - cantidad * precio
    add  x4, x4, x9
    sw   x4, 4(x14)
    jal  x0, after_order

apply_sell:
    addi x9, x0, 63
    bltu x4, x9, sell_partial
    jal  x0, sell_quantity_ready

sell_partial:
    add  x9, x0, x4           # Vender todas si hay menos de 63

sell_quantity_ready:
    beq  x9, x0, after_order
    addi x10, x0, 0           # Ingresos brutos
    add  x11, x0, x9          # Contador de acciones

sell_value_loop:
    beq  x11, x0, sell_value_done
    add  x10, x10, x8
    addi x11, x11, -1
    jal  x0, sell_value_loop

sell_value_done:
    add  x11, x3, x10         # Caja + ingresos brutos
    addi x12, x0, 5
    bltu x11, x12, after_order # El mercado no ejecuta si no cubre comisión
    sub  x11, x11, x12
    sw   x11, 0(x14)
    sub  x4, x4, x9
    sw   x4, 4(x14)
    jal  x0, after_order

after_order:
# Decidir con la ventana anterior a incorporar el precio actual.
    lw   x7, 28(x14)          # Cantidad de precios válidos
    addi x11, x0, 5
    bltu x7, x11, choose_hold # Esperar a tener cinco precios

    lw   x9, 8(x14)
    lw   x10, 12(x14)
    add  x9, x9, x10
    lw   x10, 16(x14)
    add  x9, x9, x10
    lw   x10, 20(x14)
    add  x9, x9, x10
    lw   x10, 24(x14)
    add  x9, x9, x10         # Suma de los cinco precios anteriores

    add  x10, x8, x8
    add  x10, x10, x10       # Multiplicar por cuatro
    add  x10, x10, x8        # Cinco veces el precio actual
    addi x11, x9, 35         # Suma + 5*H_compra
    bltu x11, x10, signal_high

    addi x11, x0, 35         # Cinco veces el umbral de venta (5*7)
    bltu x9, x11, choose_hold # Evitar underflow en suma - 5*H_venta
    sub  x11, x9, x11
    bltu x10, x11, signal_low
    jal  x0, choose_hold

signal_high:
    lw   x4, 4(x14)
    bne  x4, x0, choose_hold # Ya hay acciones
    addi x13, x0, 127         # Comprar hasta 63
    jal  x0, decision_ready

signal_low:
    lw   x4, 4(x14)
    beq  x4, x0, choose_hold # No hay acciones para vender
    addi x13, x0, 191         # Vender hasta 63
    jal  x0, decision_ready

choose_hold:
    addi x13, x0, 0           # Mantener

decision_ready:
# Guardar el precio actual en la ranura circular idx y avanzar idx = (idx+1)%5.
    lw   x7, 32(x14)
    add  x9, x7, x7
    add  x9, x9, x9           # idx * 4
    add  x9, x9, x14
    addi x9, x9, 8            # Dirección de la ventana + idx * 4
    sw   x8, 0(x9)
    addi x7, x7, 1
    addi x11, x0, 5
    bltu x7, x11, index_ready
    addi x7, x0, 0

index_ready:
    sw   x7, 32(x14)

    lw   x7, 28(x14)
    addi x11, x0, 5
    beq  x7, x11, count_ready
    addi x7, x7, 1
    sw   x7, 28(x14)

count_ready:
    sw   x13, 36(x14)         # Copia local de la decisión pendiente
    sw   x13, 8(x2)           # Escribir DECISION para el siguiente tick
    jal  x0, wait_price
