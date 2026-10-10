#!/usr/bin/env python3
import sys
import re

REG_MAP = {
    'x0': 0, 'zero': 0, 'x1': 1, 'ra': 1, 'x2': 2, 'sp': 2,
    'x3': 3, 'gp': 3,   'x4': 4, 'tp': 4, 'x5': 5, 't0': 5,
    'x6': 6, 't1': 6,   'x7': 7, 't2': 7, 'x8': 8, 's0': 8,
    'x9': 9, 's1': 9,   'x10': 10, 'a0': 10, 'x11': 11, 'a1': 11,
    'x12': 12, 'a2': 12, 'x13': 13, 'a3': 13, 'x14': 14, 'a4': 14,
    'x15': 15, 'a5': 15
}

def parse_reg(r):
    r = r.strip()
    if r in REG_MAP: return REG_MAP[r]
    raise ValueError(f"Registro inválido para RV32E: {r}")

def parse_imm(imm, labels=None, pc=0):
    imm = imm.strip()
    if labels and imm in labels:
        return labels[imm] - pc
    return int(imm, 0)

def preprocess(filename):
    lines = []
    with open(filename, 'r') as f:
        for line in f:
            line = re.sub(r'#.*', '', line)
            line = re.sub(r'//.*', '', line).strip()
            if not line or line.startswith('.'): continue
            
            if line.endswith(':'):
                lines.append(line)
                continue
            if ':' in line:
                lbl, inst = line.split(':', 1)
                lines.append(lbl.strip() + ':')
                line = inst.strip()

            parts = line.split(maxsplit=1)
            mnem = parts[0].lower()
            args = [a.strip() for a in parts[1].split(',')] if len(parts) > 1 else []

            if mnem == 'li':
                rd, val = args[0], int(args[1], 0) & 0xFFFFFFFF
                if val <= 2047 or val >= 0xFFFFF000:
                    v = val if val <= 2047 else val - 0x100000000
                    lines.append(f"addi {rd}, x0, {v}")
                else:
                    hi = (val + 0x800) >> 12
                    lo = val - (hi << 12)
                    if lo >= 2048: lo -= 4096
                    lines.append(f"lui {rd}, {hi}")
                    lines.append(f"addi {rd}, {rd}, {lo}")
            else:
                lines.append(line)
    return lines

def assemble(infile, outfile):
    raw_lines = preprocess(infile)
    labels, insts, pc = {}, [], 0

    for l in raw_lines:
        if l.endswith(':'): labels[l[:-1].strip()] = pc
        else:
            insts.append((pc, l))
            pc += 4

    hex_out = []
    for pc, line in insts:
        parts = line.split(maxsplit=1)
        mnem = parts[0].lower()
        args = [a.strip() for a in parts[1].split(',')] if len(parts) > 1 else []

        if mnem == 'nop': mnem, args = 'addi', ['x0', 'x0', '0']
        elif mnem == 'j': mnem, args = 'jal', ['x0', args[0]]

        if mnem == 'lui':
            rd = parse_reg(args[0])
            imm = parse_imm(args[1], labels, pc)
            code = ((imm & 0xFFFFF) << 12) | (rd << 7) | 0x37
        elif mnem == 'addi':
            rd, rs1 = parse_reg(args[0]), parse_reg(args[1])
            imm = parse_imm(args[2], labels, pc) & 0xFFF
            code = (imm << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x13
        elif mnem == 'andi':
            rd, rs1 = parse_reg(args[0]), parse_reg(args[1])
            imm = parse_imm(args[2], labels, pc) & 0xFFF
            code = (imm << 20) | (rs1 << 15) | (7 << 12) | (rd << 7) | 0x13
        elif mnem == 'xori':
            rd, rs1 = parse_reg(args[0]), parse_reg(args[1])
            imm = parse_imm(args[2], labels, pc) & 0xFFF
            code = (imm << 20) | (rs1 << 15) | (4 << 12) | (rd << 7) | 0x13
        elif mnem == 'slli':
            rd, rs1 = parse_reg(args[0]), parse_reg(args[1])
            sh = parse_imm(args[2], labels, pc) & 0x1F
            code = (sh << 20) | (rs1 << 15) | (1 << 12) | (rd << 7) | 0x13
        elif mnem == 'srli':
            rd, rs1 = parse_reg(args[0]), parse_reg(args[1])
            sh = parse_imm(args[2], labels, pc) & 0x1F
            code = (sh << 20) | (rs1 << 15) | (5 << 12) | (rd << 7) | 0x13
        elif mnem == 'lw':
            rd = parse_reg(args[0])
            if '(' in args[1]:
                m = re.match(r'(-?\d+|0x[0-9a-fA-F]+)\((\w+)\)', args[1])
                imm, rs1 = parse_imm(m.group(1), labels, pc) & 0xFFF, parse_reg(m.group(2))
            else:
                rs1, imm = parse_reg(args[1]), parse_imm(args[2], labels, pc) & 0xFFF
            code = (imm << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x03
        elif mnem == 'sw':
            rs2 = parse_reg(args[0])
            if '(' in args[1]:
                m = re.match(r'(-?\d+|0x[0-9a-fA-F]+)\((\w+)\)', args[1])
                imm, rs1 = parse_imm(m.group(1), labels, pc) & 0xFFF, parse_reg(m.group(2))
            else:
                rs1, imm = parse_reg(args[1]), parse_imm(args[2], labels, pc) & 0xFFF
            code = (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) | (2 << 12) | ((imm & 0x1F) << 7) | 0x23
        elif mnem in ('beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu'):
            f3 = {'beq':0, 'bne':1, 'blt':4, 'bge':5, 'bltu':6, 'bgeu':7}[mnem]
            rs1, rs2 = parse_reg(args[0]), parse_reg(args[1])
            off = parse_imm(args[2], labels, pc) & 0x1FFF
            code = (((off >> 12) & 1) << 31) | (((off >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (((off >> 1) & 0xF) << 8) | (((off >> 11) & 1) << 7) | 0x63
        elif mnem == 'jal':
            rd = 0 if len(args) == 1 else parse_reg(args[0])
            target = args[0] if len(args) == 1 else args[1]
            off = parse_imm(target, labels, pc) & 0x1FFFFF
            code = (((off >> 20) & 1) << 31) | (((off >> 1) & 0x3FF) << 21) | (((off >> 11) & 1) << 20) | (((off >> 12) & 0xFF) << 12) | (rd << 7) | 0x6F
        elif mnem in ('add', 'sub', 'xor', 'or', 'and', 'sll', 'srl'):
            f3 = {'add':0, 'sub':0, 'sll':1, 'xor':4, 'srl':5, 'or':6, 'and':7}[mnem]
            f7 = 0x20 if mnem == 'sub' else 0x00
            rd, rs1, rs2 = parse_reg(args[0]), parse_reg(args[1]), parse_reg(args[2])
            code = (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | 0x33
        else:
            raise ValueError(f"Instrucción no soportada: {line}")

        hex_out.append(f"{code:08x}")

    with open(outfile, 'w') as f:
        for w in hex_out: f.write(w + '\n')

if __name__ == '__main__':
    assemble(sys.argv[1] if len(sys.argv) > 1 else 'game.s',
             sys.argv[2] if len(sys.argv) > 2 else 'game.hex')