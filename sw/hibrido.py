"""Uso: py sw/hibrido.py precios.csv"""
import argparse
from reference import ejecutar_orden, leer_precios

def decisiones(precios):
    buscar_venta = False
    extremo = None
    pendientes = 0
    ultima = 0
    minimo, maximo = 256, 0
    anterior_adaptativo = False
    previo = None
    movimiento = 0
    comprimida = False
    for muestras, (_, precio) in enumerate(precios, start=1):
        minimo = min(minimo, precio)
        maximo = max(maximo, precio)
        amplitud = maximo - minimo
        if muestras <= 2048:
            if previo is not None:
                movimiento += abs(precio - previo)
            previo = precio
            if muestras == 2048:
                comprimida = movimiento <= 682
        # Un mínimo bajo 100 descarta la escala de práctica. Después del
        # calentamiento, comprobar también si ambas zonas fijas se alcanzaron.
        adaptativo = minimo < 100 or ((comprimida or muestras >= 16384) and (minimo > 150 or maximo < 225))
        if adaptativo != anterior_adaptativo:
            extremo = None
            anterior_adaptativo = adaptativo
        if pendientes:
            pendientes -= 1
            yield ultima
            continue
        if adaptativo and (muestras < 128 or amplitud < 8):
            yield 0
            continue
        if adaptativo:
            zona_alta = 4 * (maximo - precio) <= amplitud
            zona_baja = 8 * (precio - minimo) <= amplitud
            giro = (amplitud + 31) // 32
        else:
            zona_alta = precio >= 225
            zona_baja = precio <= 150
            giro = 8
        if extremo is None and (zona_alta if buscar_venta else zona_baja):
            extremo = precio
        orden = 0
        if extremo is not None:
            extremo = max(extremo, precio) if buscar_venta else min(extremo, precio)
            if abs(precio - extremo) >= giro:
                orden = 191 if buscar_venta else 127
                buscar_venta = not buscar_venta
                extremo = None
                pendientes = 2
        ultima = orden
        yield orden

def evaluar(precios):
    caja = pico = 10000
    acciones = pendiente = ordenes = caida = 0
    for (_, precio), nueva in zip(precios, decisiones(precios)):
        caja, acciones, cantidad = ejecutar_orden(pendiente, precio, caja, acciones)
        ordenes += int(cantidad > 0)
        patrimonio = caja + acciones * precio
        pico = max(pico, patrimonio)
        caida = max(caida, pico - patrimonio)
        pendiente = nueva
    return patrimonio, ordenes, caida

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    args = parser.parse_args()
    print('Patrimonio=%d; órdenes ejecutadas=%d; caída máxima=%d' %
          evaluar(leer_precios(args.csv)))
