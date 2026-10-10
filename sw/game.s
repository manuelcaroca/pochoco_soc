# Juego de reflejos para Pochoco SoC (RV32E, registros x0-x15).
#
# MMIO de periféricos (base 0x80000000):
#   +0x00 displays de 7 segmentos (dos dígitos hexadecimales empaquetados)
#   +0x04 LEDs (bits 0-3)
#   +0x08 switches/botones (bits 0-3, activo alto)
#   +0x0C contador libre de ciclos de 32 bits
#
# Temporización: el periférico incrementa el contador a 25 MHz.
# 3 s = 75.000.000 ciclos; 1 décima = 2.500.000 ciclos.
# El resultado mostrado es el número de décimas (p. ej. 25 representa 2,5 s).
# El promedio de las diez respuestas se trunca a una décima entera.
#
# El LED objetivo se calcula con los bits bajos de una suma que mezcla una
# muestra del contador al iniciar la partida, otra al terminar la espera y el
# número de respuestas correctas. El tiempo de reacción del jugador modifica
# las muestras entre rondas, evitando repetir una secuencia fija por partida.

.section .text
.global _start

_start:
    lui  x2, 0x80000          # Base MMIO de los periféricos
    addi x7, x0, 0             # x7 = respuestas correctas de la partida
    addi x12, x0, 0            # x12 = suma de tiempos en décimas
    sw   x0, 0(x2)             # Mostrar 00
    sw   x0, 4(x2)             # LEDs apagados mientras se espera el inicio

wait_start_press:
    lw   x4, 8(x2)
    beq  x4, x0, wait_start_press
    lw   x1, 12(x2)            # Semilla tomada al presionar para iniciar

wait_start_release:
    lw   x4, 8(x2)
    bne  x4, x0, wait_start_release
    jal  x0, round_start

# Cada intento, incluso tras un error, comienza con los cuatro LEDs encendidos.
round_start:
    addi x3, x0, 15
    sw   x3, 4(x2)
    lw   x5, 12(x2)            # Inicio de la espera de tres segundos
    lui  x6, 0x4787
    addi x6, x6, -1856         # x6 = 75.000.000 ciclos

wait_three_seconds:
    lw   x9, 12(x2)
    sub  x10, x9, x5           # Resta modular: también tolera el wrap del timer
    bltu x10, x6, wait_three_seconds

# Elegir una máscara de un solo bit: 1, 2, 4 u 8.
    add  x3, x9, x1
    add  x3, x3, x7
    andi x3, x3, 3
    beq  x3, x0, choose_led0
    addi x4, x0, 1
    beq  x3, x4, choose_led1
    addi x4, x0, 2
    beq  x3, x4, choose_led2
    addi x3, x0, 8
    jal  x0, target_ready

choose_led0:
    addi x3, x0, 1
    jal  x0, target_ready

choose_led1:
    addi x3, x0, 2
    jal  x0, target_ready

choose_led2:
    addi x3, x0, 4

target_ready:
    lw   x8, 12(x2)            # Inicio lógico de la medición
    sw   x3, 4(x2)             # Encender únicamente el LED objetivo

wait_for_answer:
    lw   x4, 8(x2)
    beq  x4, x0, wait_for_answer
    lw   x9, 12(x2)             # Capturar el contador apenas se detecta presión
    bne  x4, x3, wrong_button

# Respuesta correcta: apagar LEDs y convertir ciclos a décimas de segundo.
    sw   x0, 4(x2)
    sub  x9, x9, x8
    addi x10, x0, 0             # x10 = tiempo de respuesta en décimas
    lui  x6, 0x262
    addi x6, x6, 1440           # x6 = 2.500.000 ciclos por décima

cycles_to_tenths:
    bltu x9, x6, tenths_ready
    sub  x9, x9, x6
    addi x10, x10, 1
    addi x11, x0, 99
    bne  x10, x11, cycles_to_tenths

tenths_ready:
# Convertir x10 (0-99) a BCD para mostrar decenas y unidades.
    addi x14, x0, 0             # x14 = decenas
    add  x15, x0, x10           # x15 = unidades/resto
    addi x11, x0, 10

response_to_bcd:
    bltu x15, x11, response_bcd_ready
    sub  x15, x15, x11
    addi x14, x14, 1
    jal  x0, response_to_bcd

response_bcd_ready:
    add  x5, x14, x14           # Decenas * 16 (sin usar shifts)
    add  x5, x5, x5
    add  x5, x5, x5
    add  x5, x5, x5
    add  x5, x5, x15
    sw   x5, 0(x2)
    add  x12, x12, x10          # Acumular décimas para el promedio
    addi x7, x7, 1

wait_correct_release:
    lw   x4, 8(x2)
    bne  x4, x0, wait_correct_release
    addi x11, x0, 10
    beq  x7, x11, show_average
    jal  x0, round_start

# Una respuesta incorrecta muestra EE y reinicia la ronda sin borrar el puntaje.
wrong_button:
    addi x3, x0, 238            # 0xEE
    sw   x3, 0(x2)
    sw   x0, 4(x2)

wait_wrong_release:
    lw   x4, 8(x2)
    bne  x4, x0, wait_wrong_release
    jal  x0, round_start

# Promedio = suma de las diez respuestas / 10, expresado en décimas.
show_average:
    addi x14, x0, 0             # Cociente del promedio
    add  x15, x0, x12           # Dividendo: suma de décimas
    addi x11, x0, 10

average_divide:
    bltu x15, x11, average_ready
    sub  x15, x15, x11
    addi x14, x14, 1
    jal  x0, average_divide

average_ready:
    add  x10, x0, x14
    addi x14, x0, 0
    add  x15, x0, x10

average_to_bcd:
    bltu x15, x11, average_bcd_ready
    sub  x15, x15, x11
    addi x14, x14, 1
    jal  x0, average_to_bcd

average_bcd_ready:
    add  x5, x14, x14           # Empaquetar BCD: decenas en nibble alto
    add  x5, x5, x5
    add  x5, x5, x5
    add  x5, x5, x5
    add  x5, x5, x15
    sw   x5, 0(x2)

wait_restart_press:
    lw   x4, 8(x2)
    beq  x4, x0, wait_restart_press
    lw   x1, 12(x2)            # Nueva semilla para la siguiente partida

wait_restart_release:
    lw   x4, 8(x2)
    bne  x4, x0, wait_restart_release
    addi x7, x0, 0
    addi x12, x0, 0
    sw   x0, 0(x2)
    jal  x0, round_start
