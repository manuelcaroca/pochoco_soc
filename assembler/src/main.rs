//! RV32E assembler (adaptado de ML_Translator/main.py).
//!
//! Uso: cargo run -- entrada.asm [salida.hex]
//! Salida: una palabra de máquina de 8 dígitos hexadecimales por línea.
//! Si se omite la salida, se usa el mismo nombre con extensión `.hex`.

use std::collections::HashMap;
use std::env;
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};

type AsmResult<T> = Result<T, Box<dyn Error>>;
type Symbols = HashMap<String, u32>; // etiqueta -> dirección en bytes

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Format {
    R,
    I,
    S,
    B,
    U,
    J,
}

#[derive(Debug, Clone, Copy)]
struct InstructionSpec {
    format: Format,
    opcode: u32,
    funct3: Option<u32>,
    funct7: Option<u32>, // Solo instrucciones de registro y shifts inmediatos.
}

#[derive(Debug, Clone)]
struct ParsedInstruction {
    mnemonic: String,
    operands: Vec<String>,
    pc: u32, // Dirección en bytes, no índice de instrucción.
    line_number: usize,
}

fn main() {
    if let Err(e) = run() {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}

fn run() -> AsmResult<()> {
    let (input, output) = parse_args()?;
    let source = read_source(&input.to_string_lossy())?;
    let (instructions, symbols) = first_pass(&source)?;
    let words = second_pass(&instructions, &symbols)?;
    write_hex(&output.to_string_lossy(), &words)?;
    Ok(())
}

/// Antepone "línea N: " al error para que el usuario sepa dónde falló.
fn at_line<T>(line: usize, r: AsmResult<T>) -> AsmResult<T> {
    r.map_err(|e| format!("línea {line}: {e}").into())
}

// ── CLI / FILES ───────────────────────────────────────────────────────────────
fn parse_args() -> AsmResult<(PathBuf, PathBuf)> {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.len() {
        1 => {
            let input = PathBuf::from(&args[0]);
            let output = input.with_extension("hex");
            Ok((input, output))
        }
        2 => Ok((PathBuf::from(&args[0]), PathBuf::from(&args[1]))),
        _ => Err("uso: assembler <entrada.asm> [salida.hex]".into()),
    }
}

fn read_source(path: &str) -> AsmResult<String> {
    let text = fs::read_to_string(Path::new(path))
        .map_err(|e| format!("no se pudo leer '{path}': {e}"))?;
    Ok(text)
}

fn write_hex(path: &str, words: &[u32]) -> AsmResult<()> {
    let mut text = words
        .iter()
        .map(|word| format!("{word:08X}"))
        .collect::<Vec<_>>()
        .join("\n");
    if !text.is_empty() {
        text.push('\n');
    }
    fs::write(path, text).map_err(|e| format!("no se pudo escribir '{path}': {e}"))?;
    Ok(())
}

// ── PASS 1: LINES, LABELS, TOKENS ─────────────────────────────────────────────
fn first_pass(source: &str) -> AsmResult<(Vec<ParsedInstruction>, Symbols)> {
    let mut symbols = Symbols::new();
    let mut instructions = Vec::new();
    let mut pc: u32 = 0;

    for (idx, raw) in source.lines().enumerate() {
        let line_number = idx + 1;
        let mut line = strip_comment(raw);

        // Permite una o más etiquetas: "a: b: addi x1, x0, 1".
        while let Some((label, rest)) = line.split_once(':') {
            let label = label.trim();
            at_line(line_number, validate_label(label))?;
            if symbols.insert(label.to_string(), pc).is_some() {
                return Err(format!("línea {line_number}: etiqueta duplicada '{label}'").into());
            }
            line = rest.trim();
        }

        if line.is_empty() {
            continue;
        }

        // Directivas que no afectan el código máquina
        if line.starts_with(".section ") || line.starts_with(".global ") {
            continue;
        }

        let parsed = at_line(line_number, parse_instruction(line, pc, line_number))?;
        // Se expanden las pseudoinstrucciones ANTES de avanzar el PC,
        // así las etiquetas posteriores quedan en la dirección correcta.
        for mut inst in at_line(line_number, expand_pseudoinstruction(&parsed))? {
            inst.pc = pc;
            instructions.push(inst);
            pc = pc
                .checked_add(4)
                .ok_or_else(|| format!("línea {line_number}: programa demasiado grande"))?;
        }
    }

    Ok((instructions, symbols))
}

fn strip_comment(line: &str) -> &str {
    line.split(|c: char| c == '#' || c == ';')
        .next()
        .unwrap_or("")
        .trim()
}

fn validate_label(name: &str) -> AsmResult<()> {
    let mut chars = name.chars();
    let first = chars.next().ok_or("etiqueta vacía")?;
    if !(first.is_ascii_alphabetic() || matches!(first, '_' | '.')) {
        return Err(format!("etiqueta inválida '{name}': debe empezar con letra, '_' o '.'").into());
    }
    if !chars.all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '.' | '$')) {
        return Err(format!("etiqueta inválida '{name}': caracteres no permitidos").into());
    }
    if parse_register(name).is_ok() {
        return Err(format!("etiqueta inválida '{name}': es un nombre de registro").into());
    }
    // La detección de duplicados se hace en first_pass (necesita la tabla de símbolos).
    Ok(())
}

fn parse_instruction(text: &str, pc: u32, line_number: usize) -> AsmResult<ParsedInstruction> {
    let text = text.trim();
    let (mnemonic, rest) = match text.split_once(char::is_whitespace) {
        Some((m, r)) => (m, r.trim()),
        None => (text, ""),
    };
    if mnemonic.is_empty() {
        return Err("instrucción vacía".into());
    }

    // Separar por comas conserva "4(x2)" como un solo operando.
    let operands: Vec<String> = if rest.is_empty() {
        Vec::new()
    } else {
        rest.split(',').map(|s| s.trim().to_string()).collect()
    };
    if operands.iter().any(|o| o.is_empty()) {
        return Err(format!("operando vacío en '{text}'").into());
    }

    Ok(ParsedInstruction {
        mnemonic: mnemonic.to_ascii_lowercase(),
        operands,
        pc,
        line_number,
    })
}

// ── INSTRUCTION LOOKUP ───────────────────────────────────────────────────────
const fn spec(
    format: Format,
    opcode: u32,
    funct3: Option<u32>,
    funct7: Option<u32>,
) -> InstructionSpec {
    InstructionSpec { format, opcode, funct3, funct7 }
}

fn lookup_instruction(mnemonic: &str) -> AsmResult<InstructionSpec> {
    use Format::*;
    let s = match mnemonic {
        // R (opcode 0x33)
        "add" => spec(R, 0x33, Some(0), Some(0x00)),
        "sub" => spec(R, 0x33, Some(0), Some(0x20)),
        "sll" => spec(R, 0x33, Some(1), Some(0x00)),
        "slt" => spec(R, 0x33, Some(2), Some(0x00)),
        "sltu" => spec(R, 0x33, Some(3), Some(0x00)),
        "xor" => spec(R, 0x33, Some(4), Some(0x00)),
        "srl" => spec(R, 0x33, Some(5), Some(0x00)),
        "sra" => spec(R, 0x33, Some(5), Some(0x20)),
        "or" => spec(R, 0x33, Some(6), Some(0x00)),
        "and" => spec(R, 0x33, Some(7), Some(0x00)),
        // I aritméticas (opcode 0x13)
        "addi" => spec(I, 0x13, Some(0), None),
        "slti" => spec(I, 0x13, Some(2), None),
        "sltiu" => spec(I, 0x13, Some(3), None),
        "xori" => spec(I, 0x13, Some(4), None),
        "ori" => spec(I, 0x13, Some(6), None),
        "andi" => spec(I, 0x13, Some(7), None),
        "slli" => spec(I, 0x13, Some(1), Some(0x00)),
        "srli" => spec(I, 0x13, Some(5), Some(0x00)),
        "srai" => spec(I, 0x13, Some(5), Some(0x20)),
        // Loads (opcode 0x03)
        "lb" => spec(I, 0x03, Some(0), None),
        "lh" => spec(I, 0x03, Some(1), None),
        "lw" => spec(I, 0x03, Some(2), None),
        "lbu" => spec(I, 0x03, Some(4), None),
        "lhu" => spec(I, 0x03, Some(5), None),
        // Stores (opcode 0x23)
        "sb" => spec(S, 0x23, Some(0), None),
        "sh" => spec(S, 0x23, Some(1), None),
        "sw" => spec(S, 0x23, Some(2), None),
        // Branches (opcode 0x63)
        "beq" => spec(B, 0x63, Some(0), None),
        "bne" => spec(B, 0x63, Some(1), None),
        "blt" => spec(B, 0x63, Some(4), None),
        "bge" => spec(B, 0x63, Some(5), None),
        "bltu" => spec(B, 0x63, Some(6), None),
        "bgeu" => spec(B, 0x63, Some(7), None),
        // U, J, JALR
        "lui" => spec(U, 0x37, None, None),
        "auipc" => spec(U, 0x17, None, None),
        "jal" => spec(J, 0x6F, None, None),
        "jalr" => spec(I, 0x67, Some(0), None),
        _ => return Err(format!("instrucción desconocida: '{mnemonic}'").into()),
    };
    Ok(s)
}

// ── OPERANDS AND VALUES ──────────────────────────────────────────────────────
fn parse_register(text: &str) -> AsmResult<u32> {
    let t = text.trim().to_ascii_lowercase();

    if let Some(num) = t.strip_prefix('x') {
        if !num.is_empty() && num.chars().all(|c| c.is_ascii_digit()) {
            return match num.parse::<u32>() {
                Ok(n @ 0..=15) => Ok(n),
                Ok(16..=31) => {
                    Err(format!("el registro '{text}' no existe en RV32E (solo x0..x15)").into())
                }
                _ => Err(format!("registro inválido: '{text}'").into()),
            };
        }
    }

    match t.as_str() {
        "zero" => Ok(0),
        "ra" => Ok(1),
        "sp" => Ok(2),
        "gp" => Ok(3),
        "tp" => Ok(4),
        "t0" => Ok(5),
        "t1" => Ok(6),
        "t2" => Ok(7),
        "s0" | "fp" => Ok(8),
        "s1" => Ok(9),
        "a0" => Ok(10),
        "a1" => Ok(11),
        "a2" => Ok(12),
        "a3" => Ok(13),
        "a4" => Ok(14),
        "a5" => Ok(15),
        "a6" | "a7" | "t3" | "t4" | "t5" | "t6" | "s2" | "s3" | "s4" | "s5" | "s6" | "s7"
        | "s8" | "s9" | "s10" | "s11" => {
            Err(format!("el registro '{text}' no existe en RV32E (solo x0..x15)").into())
        }
        _ => Err(format!("registro inválido: '{text}'").into()),
    }
}

fn parse_immediate(text: &str) -> AsmResult<i32> {
    let bad = || format!("inmediato inválido: '{text}'");
    let t = text.trim();
    let (negative, body) = if let Some(r) = t.strip_prefix('-') {
        (true, r)
    } else if let Some(r) = t.strip_prefix('+') {
        (false, r)
    } else {
        (false, t)
    };
    if !body.chars().next().map_or(false, |c| c.is_ascii_digit()) {
        return Err(bad().into());
    }

    let parsed = if let Some(h) = body.strip_prefix("0x").or_else(|| body.strip_prefix("0X")) {
        i64::from_str_radix(h, 16)
    } else if let Some(b) = body.strip_prefix("0b").or_else(|| body.strip_prefix("0B")) {
        i64::from_str_radix(b, 2)
    } else {
        body.parse::<i64>()
    };
    let magnitude = parsed.map_err(|_| bad())?;

    let value = if negative { -magnitude } else { magnitude };
    // Se aceptan tanto valores con signo como patrones de 32 bits (0xFFFFFFFF).
    if !(i32::MIN as i64..=u32::MAX as i64).contains(&value) {
        return Err(format!("inmediato fuera de 32 bits: '{text}'").into());
    }
    Ok(value as u32 as i32)
}

fn parse_memory_operand(text: &str) -> AsmResult<(i32, u32)> {
    let bad = || format!("operando de memoria inválido: '{text}' (se esperaba imm(reg))");
    let (offset, rest) = text.split_once('(').ok_or_else(bad)?;
    let reg = rest.trim().strip_suffix(')').ok_or_else(bad)?;
    let offset = offset.trim();
    let imm = if offset.is_empty() { 0 } else { parse_immediate(offset)? };
    Ok((imm, parse_register(reg)?))
}

fn resolve_offset(target: &str, pc: u32, symbols: &Symbols) -> AsmResult<i32> {
    let t = target.trim();
    if let Some(&addr) = symbols.get(t) {
        let diff = addr as i64 - pc as i64; // i64: la resta no desborda
        return i32::try_from(diff).map_err(|_| format!("salto a '{t}' fuera de rango").into());
    }
    let first = t.chars().next().unwrap_or(' ');
    if first.is_ascii_alphabetic() || matches!(first, '_' | '.') {
        return Err(format!("etiqueta no definida: '{t}'").into());
    }
    // Número literal: se interpreta directamente como offset en BYTES.
    parse_immediate(t)
}

fn check_signed_range(value: i32, bits: u32) -> AsmResult<()> {
    let min = -(1_i64 << (bits - 1));
    let max = (1_i64 << (bits - 1)) - 1;
    if (min..=max).contains(&(value as i64)) {
        Ok(())
    } else {
        Err(format!("valor {value} fuera de rango para {bits} bits con signo [{min}, {max}]").into())
    }
}

fn check_even_offset(value: i32) -> AsmResult<()> {
    if value & 1 != 0 {
        Err(format!("el offset {value} debe ser par").into())
    } else {
        Ok(())
    }
}

fn expect_operands(inst: &ParsedInstruction, n: usize) -> AsmResult<()> {
    if inst.operands.len() != n {
        return Err(format!(
            "'{}' espera {} operando(s), pero recibió {}",
            inst.mnemonic,
            n,
            inst.operands.len()
        )
        .into());
    }
    Ok(())
}

// ── PASS 2: ASSEMBLY ─────────────────────────────────────────────────────────
fn second_pass(lines: &[ParsedInstruction], symbols: &Symbols) -> AsmResult<Vec<u32>> {
    lines
        .iter()
        .map(|inst| at_line(inst.line_number, assemble_instruction(inst, symbols)))
        .collect()
}

fn assemble_instruction(inst: &ParsedInstruction, symbols: &Symbols) -> AsmResult<u32> {
    let spec = lookup_instruction(&inst.mnemonic)?;
    let ops = &inst.operands;
    let funct3 = spec.funct3.unwrap_or(0);
    let funct7 = spec.funct7.unwrap_or(0);

    match spec.format {
        Format::R => {
            expect_operands(inst, 3)?;
            let rd = parse_register(&ops[0])?;
            let rs1 = parse_register(&ops[1])?;
            let rs2 = parse_register(&ops[2])?;
            Ok(encode_r(spec.opcode, rd, funct3, rs1, rs2, funct7))
        }
        Format::I => match spec.opcode {
            // Loads y JALR: rd, imm(rs1)
            0x03 | 0x67 => {
                expect_operands(inst, 2)?;
                let rd = parse_register(&ops[0])?;
                let (imm, rs1) = parse_memory_operand(&ops[1])?;
                check_signed_range(imm, 12)?;
                Ok(encode_i(spec.opcode, rd, funct3, rs1, imm))
            }
            // Aritméticas inmediatas y shifts: rd, rs1, imm
            _ => {
                expect_operands(inst, 3)?;
                let rd = parse_register(&ops[0])?;
                let rs1 = parse_register(&ops[1])?;
                let imm = parse_immediate(&ops[2])?;
                let field = if spec.funct7.is_some() {
                    if !(0..=31).contains(&imm) {
                        return Err(format!("shamt {imm} fuera de rango [0, 31]").into());
                    }
                    // imm[11:5] = funct7 (SRAI = 0100000), imm[4:0] = shamt
                    ((funct7 << 5) as i32) | imm
                } else {
                    check_signed_range(imm, 12)?;
                    imm
                };
                Ok(encode_i(spec.opcode, rd, funct3, rs1, field))
            }
        },
        Format::S => {
            expect_operands(inst, 2)?;
            let rs2 = parse_register(&ops[0])?;
            let (imm, rs1) = parse_memory_operand(&ops[1])?;
            check_signed_range(imm, 12)?;
            Ok(encode_s(spec.opcode, funct3, rs1, rs2, imm))
        }
        Format::B => {
            expect_operands(inst, 3)?;
            let rs1 = parse_register(&ops[0])?;
            let rs2 = parse_register(&ops[1])?;
            let offset = resolve_offset(&ops[2], inst.pc, symbols)?;
            check_signed_range(offset, 13)?;
            check_even_offset(offset)?;
            Ok(encode_b(spec.opcode, funct3, rs1, rs2, offset))
        }
        Format::U => {
            expect_operands(inst, 2)?;
            let rd = parse_register(&ops[0])?;
            let imm = parse_immediate(&ops[1])?;
            // Valor de CAMPO de 20 bits: se acepta con signo [-2^19, 2^19-1]
            // o sin signo [0, 2^20-1].
            if !(-(1_i32 << 19)..=(1_i32 << 20) - 1).contains(&imm) {
                return Err(format!("inmediato U {imm} fuera de rango de 20 bits").into());
            }
            Ok(encode_u(spec.opcode, rd, imm))
        }
        Format::J => {
            expect_operands(inst, 2)?;
            let rd = parse_register(&ops[0])?;
            let offset = resolve_offset(&ops[1], inst.pc, symbols)?;
            check_signed_range(offset, 21)?;
            check_even_offset(offset)?;
            Ok(encode_j(spec.opcode, rd, offset))
        }
    }
}

// ── BIT ENCODERS ─────────────────────────────────────────────────────────────
// El rango de los inmediatos se valida en assemble_instruction (aquí solo hay
// debug_assert, porque estas funciones devuelven u32 y no Result).
fn encode_r(opcode: u32, rd: u32, funct3: u32, rs1: u32, rs2: u32, funct7: u32) -> u32 {
    (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode
}

fn encode_i(opcode: u32, rd: u32, funct3: u32, rs1: u32, imm: i32) -> u32 {
    debug_assert!((-2048..=2047).contains(&imm));
    (((imm as u32) & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode
}

fn encode_s(opcode: u32, funct3: u32, rs1: u32, rs2: u32, imm: i32) -> u32 {
    debug_assert!((-2048..=2047).contains(&imm));
    let imm = (imm as u32) & 0xFFF;
    (((imm >> 5) & 0x7F) << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (funct3 << 12)
        | ((imm & 0x1F) << 7)
        | opcode
}

fn encode_b(opcode: u32, funct3: u32, rs1: u32, rs2: u32, offset: i32) -> u32 {
    debug_assert!((-4096..=4095).contains(&offset) && offset % 2 == 0);
    let o = offset as u32;
    (((o >> 12) & 1) << 31)          // imm[12]
        | (((o >> 5) & 0x3F) << 25)  // imm[10:5]
        | (rs2 << 20)
        | (rs1 << 15)
        | (funct3 << 12)
        | (((o >> 1) & 0xF) << 8)    // imm[4:1]
        | (((o >> 11) & 1) << 7)     // imm[11]
        | opcode
}

fn encode_u(opcode: u32, rd: u32, imm20: i32) -> u32 {
    (((imm20 as u32) & 0xFFFFF) << 12) | (rd << 7) | opcode
}

fn encode_j(opcode: u32, rd: u32, offset: i32) -> u32 {
    debug_assert!((-(1 << 20)..(1 << 20)).contains(&offset) && offset % 2 == 0);
    let o = offset as u32;
    (((o >> 20) & 1) << 31)            // imm[20]
        | (((o >> 1) & 0x3FF) << 21)   // imm[10:1]
        | (((o >> 11) & 1) << 20)      // imm[11]
        | (((o >> 12) & 0xFF) << 12)   // imm[19:12]
        | (rd << 7)
        | opcode
}

// ── PSEUDOINSTRUCCIONES ──────────────────────────────────────────────────────
// nop, mv, not, neg, li, j, jal <label>, jr, ret, beqz, bnez
fn expand_pseudoinstruction(inst: &ParsedInstruction) -> AsmResult<Vec<ParsedInstruction>> {
    let make = |mnemonic: &str, operands: &[&str]| ParsedInstruction {
        mnemonic: mnemonic.to_string(),
        operands: operands.iter().map(|s| s.to_string()).collect(),
        pc: inst.pc,
        line_number: inst.line_number,
    };

    let mnemonic = inst.mnemonic.as_str();
    let expected = match mnemonic {
        "nop" | "ret" => Some(0),
        "j" | "jr" => Some(1),
        "mv" | "not" | "neg" | "li" | "beqz" | "bnez" => Some(2),
        _ => None,
    };
    if let Some(n) = expected {
        expect_operands(inst, n)?;
    }
    let ops: Vec<&str> = inst.operands.iter().map(String::as_str).collect();

    let out = match mnemonic {
        "nop" => vec![make("addi", &["x0", "x0", "0"])],
        "mv" => vec![make("addi", &[ops[0], ops[1], "0"])],
        "not" => vec![make("xori", &[ops[0], ops[1], "-1"])],
        "neg" => vec![make("sub", &[ops[0], "x0", ops[1]])],
        "j" => vec![make("jal", &["x0", ops[0]])],
        "jal" if ops.len() == 1 => vec![make("jal", &["x1", ops[0]])],
        "jr" => {
            let mem = format!("0({})", ops[0]);
            vec![make("jalr", &["x0", mem.as_str()])]
        }
        "ret" => vec![make("jalr", &["x0", "0(x1)"])],
        "beqz" => vec![make("beq", &[ops[0], "x0", ops[1]])],
        "bnez" => vec![make("bne", &[ops[0], "x0", ops[1]])],
        "li" => {
            let imm = parse_immediate(ops[1])?;
            if (-2048..=2047).contains(&imm) {
                vec![make("addi", &[ops[0], "x0", ops[1]])]
            } else {
                // lui carga la parte alta; addi suma la parte baja con signo,
                // por eso se redondea hacia arriba con +0x800.
                let v = imm as i64;
                let q = (v + 0x800) >> 12;
                let hi = (q & 0xFFFFF).to_string();
                let lo = v - (q << 12);
                let mut v = vec![make("lui", &[ops[0], hi.as_str()])];
                if lo != 0 {
                    v.push(make("addi", &[ops[0], ops[0], lo.to_string().as_str()]));
                }
                v
            }
        }
        _ => vec![inst.clone()],
    };
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn asm(src: &str) -> Vec<u32> {
        let (insts, syms) = first_pass(src).unwrap();
        second_pass(&insts, &syms).unwrap()
    }

    #[test]
    fn add_example() {
        // ADD x5,x6,x7 -> 0x007302B3.
        assert_eq!(encode_r(0x33, 5, 0, 6, 7, 0), 0x0073_02B3);
    }

    #[test]
    fn addi_example() {
        // ADDI x5,x6,10 -> 0x00A30293.
        assert_eq!(encode_i(0x13, 5, 0, 6, 10), 0x00A3_0293);
    }

    #[test]
    fn formats() {
        assert_eq!(asm("sub x1, x2, x3"), [0x403100B3]);
        assert_eq!(asm("lw x5, 4(x2)"), [0x00412283]);
        assert_eq!(asm("sw x5, 8(x2)"), [0x00512423]);
        assert_eq!(asm("beq x1, x2, 8"), [0x00208463]);
        assert_eq!(asm("jal x1, 8"), [0x008000EF]);
        assert_eq!(asm("lui x5, 0x12345"), [0x123452B7]);
        assert_eq!(asm("srai x1, x2, 3"), [0x40315093]);
    }

    #[test]
    fn labels_and_backward_branch() {
        let words = asm("loop: addi x1, x1, 1 # sube\n bne x1, x2, loop");
        assert_eq!(words, [0x00108093, 0xFE209EE3]);
    }

    #[test]
    fn label_on_same_line_and_abi_names() {
        assert_eq!(asm("start: addi a0, zero, 1"), [0x00100513]);
    }

    #[test]
    fn li_large_expands_to_two_words() {
        assert_eq!(asm("li x5, 0x12345678"), [0x123452B7, 0x67828293]);
    }

    #[test]
    fn rejects_rv32i_registers() {
        assert!(parse_register("x16").is_err());
        assert!(parse_register("a6").is_err());
        assert_eq!(parse_register("x15").unwrap(), 15);
    }

    #[test]
    fn rejects_bad_input() {
        assert!(first_pass("a:\na:").is_err()); // etiqueta duplicada
        let (i, s) = first_pass("addi x1, x0, 5000").unwrap();
        assert!(second_pass(&i, &s).is_err()); // fuera de rango
        let (i, s) = first_pass("beq x0, x0, nowhere").unwrap();
        assert!(second_pass(&i, &s).is_err()); // etiqueta no definida
    }
}
