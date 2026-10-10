# sw/blink_leds.s — Verificación directa de hardware
.section .text
.global _start

_start:
    lui  x2, 0x80000        # Base MMIO = 0x8000_0000

    # 1. Encender los 4 LEDs (escribir 0x0F en offset +4)
    addi x3, x0, 15         # x3 = 15 (0x0F)
    sw   x3, 4(x2)          # MMIO 0x8000_0004 -> LEDs

    # 2. Mostrar "88" en los Displays (escribir 0x88 en offset +0)
    addi x4, x0, 136        # x4 = 136 (0x88)
    sw   x4, 0(x2)          # MMIO 0x8000_0000 -> Displays

halt:
    jal  x0, halt           # Bucle infinito