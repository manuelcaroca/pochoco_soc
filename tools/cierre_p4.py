#!/usr/bin/env python3
"""Cierre reproducible del híbrido de Proyecto-4, commit 82c0cad. Ejecutar desde raíz."""
from pathlib import Path
import argparse,csv,os,re,sys,subprocess,shutil,json,statistics,concurrent.futures,hashlib
from collections import Counter
from isa_check import emulate
ROOT=Path(__file__).resolve().parents[1]; os.chdir(ROOT)
OUT=ROOT/'bench_p4_final'; OUT.mkdir(exist_ok=True)
REPORT_DIR=ROOT.parent/(ROOT.name+'_informe')
FREQ=25_000_000; BUDGET=(100000-9500)//40
VAR={'sw':('trade_top','sw/trade.s','sw/trade.hex',0,512), 'fixed':('trade_top_fixed','sw/trade_hybrid_fixed.s','sw/trade_hybrid_fixed.hex',1,512), 'compact':('trade_top_compact','sw/trade_hybrid_compact.s','sw/trade_hybrid_compact.hex',1,128)}
BASE_HASH='46fdb9b2bbcc4667a15756d0e29a71226c48afbf'

def blobhash(s):
    b=s.encode(); return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def rep(s,a,b):
    if s.count(a)!=1: raise RuntimeError(f'Patrón inesperado: {a[:100]}')
    return s.replace(a,b,1)
def put(p,s):
    p=ROOT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf8')
def read(p):return (ROOT/p).read_text(encoding='utf8')

def prepare():
    src=read('sw/trade.s')
    if blobhash(read('sw/hibrido.py'))!='f7e804e5f6c885fe63ae32be1f1b10e67bb9a012': raise RuntimeError('hibrido.py no coincide con la referencia auditada.')
    if blobhash(src)!=BASE_HASH: raise RuntimeError('trade.s no coincide con el commit 82c0cad. Usa una copia limpia de Proyecto-4; no se cambia tu estrategia.')
    # Escalas adaptativas: cada secuencia es una cadena de ADD sobre x9 (0..254).
    pat=r'(?:^    add x9, x9, x9\n){2,5}'
    lens=[]
    def replace(m):
        n=m.group().count('\n');lens.append(n);return f'    slli x9, x9, {n}       # escala adaptativa especializada\n'
    fixed=re.sub(pat,replace,src,flags=re.M)
    if lens!=[3,5,2,5]:raise RuntimeError(f'Secuencias inesperadas {lens}')
    put('sw/trade_hybrid_fixed.s',fixed)
    compact=fixed.replace('2000(x0)','508(x0)')
    assert fixed.count('2000(x0)')==4 and '2000(x0)' not in compact
    put('sw/trade_hybrid_compact.s',compact)
    # Parche idempotente: marcadores de parámetro indican instalación previa de este paquete.
    alu='rtl/espino_core/espino_alu.v'; ids='rtl/espino_core/espino_id_stage.v'; core='rtl/espino_core/espino_core.v'; soc='rtl/pochoco_soc.v'
    s=read(alu)
    if 'P4_HYBRID_SHIFT' not in s:
        s=rep(s,'module espino_alu (','module espino_alu #(parameter integer P4_HYBRID_SHIFT = 0) (')
        s=rep(s,'      // ALU_SLL:  result_o = operand_a_i << shamt;', '''      // P4_HYBRID_SHIFT: sólo SLLI 2/3/5, operando sin signo de 8 bits.
      ALU_SLL: begin
        result_o = operand_a_i + operand_b_i;
        if (P4_HYBRID_SHIFT != 0) begin
          case (shamt)
            5'd2: result_o = {22'b0, operand_a_i[7:0], 2'b0};
            5'd3: result_o = {21'b0, operand_a_i[7:0], 3'b0};
            5'd5: result_o = {19'b0, operand_a_i[7:0], 5'b0};
            default: result_o = operand_a_i + operand_b_i;
          endcase
        end
      end''');put(alu,s)
        s=rep(read(ids),'module espino_id_stage (','module espino_id_stage #(parameter integer P4_HYBRID_SHIFT = 0) (');s=rep(s,'espino_alu u_alu (','espino_alu #(.P4_HYBRID_SHIFT(P4_HYBRID_SHIFT)) u_alu (');put(ids,s)
        s=rep(read(core),"parameter [31:0] BootAddr = 32'h0000_0000","parameter [31:0] BootAddr = 32'h0000_0000,\n  parameter integer P4_HYBRID_SHIFT = 0");s=rep(s,'espino_id_stage u_id (','espino_id_stage #(.P4_HYBRID_SHIFT(P4_HYBRID_SHIFT)) u_id (');put(core,s)
        s=rep(read(soc),'parameter MemFile    = ""','parameter MemFile    = "",\n  parameter integer P4_HYBRID_SHIFT = 0');s=rep(s,"espino_core #(.BootAddr(32'h0000_0000))","espino_core #(.BootAddr(32'h0000_0000), .P4_HYBRID_SHIFT(P4_HYBRID_SHIFT))");put(soc,s)
    for v in ('fixed','compact'):
        top,_,hexfile,mode,n=VAR[v];s=rep(read('rtl/trade_top.v'),'module trade_top (',f'module {top} (');s=rep(s,'.MemFile("sw/trade.hex")',f'.MemFile("{hexfile}"), .NumWords({n}), .P4_HYBRID_SHIFT({mode})');put(f'rtl/{top}.v',s)
    # Testbench separado: se mantiene intacto el entregado por el profesor.
    s=read('tb_proyecto_4.sv');s=rep(s,'module tb_proyecto_4;', 'module tb_p4_final;')
    s=re.sub(r'  localparam string PROGRAMA\s*=.*?;','''`ifdef P4_FIXED
  localparam PROGRAMA = "sw/trade_hybrid_fixed.hex";
  localparam integer SHIFT = 1, WORDS = 512;
`elsif P4_COMPACT
  localparam PROGRAMA = "sw/trade_hybrid_compact.hex";
  localparam integer SHIFT = 1, WORDS = 128;
`else
  localparam PROGRAMA = "sw/trade.hex";
  localparam integer SHIFT = 0, WORDS = 512;
`endif''',s,count=1)
    s=re.sub(r'  localparam string SERIE\s*=.*?;', '  string serie_path, decisions_path, metrics_path, pc_path;',s,count=1)
    s=rep(s,'localparam int    NTICKS','parameter integer NTICKS')
    s=rep(s,'pochoco_soc #(.MemFile(PROGRAMA)) dut','pochoco_soc #(.MemFile(PROGRAMA), .NumWords(WORDS), .P4_HYBRID_SHIFT(SHIFT)) dut')
    s=rep(s,'string encabezado;','reg [2047:0] encabezado;')
    s=rep(s,'fd = $fopen(SERIE, "r");','fd = $fopen(serie_path, "r");')
    s=rep(s,'$display("ERROR: no se encontro %s", SERIE); $finish;','$fatal(1, "No se encontro %s", serie_path);')
    s=rep(s,'for (int n = 0; n < NTICKS; n++) r = $fscanf(fd, "%d,%d\\n", t, precio[n]);','''for (int n = 0; n < NTICKS; n++) begin
      r = $fscanf(fd, "%d,%d\\n", t, precio[n]);
      if (r != 2 || precio[n] < 1 || precio[n] > 255) $fatal(1,"CSV invalido tick %0d",n);
    end''')
    s=rep(s,'int peor_tiempo_ns = 0, fd_metricas;', '''int peor_tiempo_ns = 0, fd_metricas;
  integer pcycles [0:511], pcommits [0:511];
  integer pi, fd_pc;''')
    s=rep(s,'      ciclos++;','''      ciclos++;
      if (dut.u_core.pc_id[31:11] == 0) begin
        pi = dut.u_core.pc_id[10:2];
        pcycles[pi] = pcycles[pi] + 1;
        if (dut.u_core.u_id.commit) pcommits[pi] = pcommits[pi] + 1;
      end''')
    s=rep(s,'"%0d,%0d,%0d,%0.3f,%0d",','"%0d,%0d,%0d,%0.3f,%0d,%02h",')
    s=rep(s,'cpi_tick, tiempo_tick_ns);','cpi_tick, tiempo_tick_ns, dut.u_spi.wdata_i[7:0]);')
    s=rep(s,'    leer_serie();','''    for (int j=0; j<512; j++) begin pcycles[j]=0; pcommits[j]=0; end
    if (!$value$plusargs("SERIES=%s",serie_path)) $fatal(1,"Falta SERIES");
    if (!$value$plusargs("DECISIONS=%s",decisions_path)) $fatal(1,"Falta DECISIONS");
    if (!$value$plusargs("METRICS=%s",metrics_path)) $fatal(1,"Falta METRICS");
    if (!$value$plusargs("PCSTATS=%s",pc_path)) $fatal(1,"Falta PCSTATS");
    leer_serie();''')
    s=rep(s,'$fopen("decisiones.csv", "w")','$fopen(decisions_path, "w")')
    s=rep(s,'$fopen("sw/resultados_reales/practica_meta_metricas_tick.csv", "w")','$fopen(metrics_path, "w")')
    s=rep(s,'"tick,instrucciones,ciclos,cpi,tiempo_ns"','"tick,instrucciones,ciclos,cpi,tiempo_ns,decision_written"')
    s=rep(s,'    $fclose(fd_metricas);','''    $fclose(fd_metricas);
    fd_pc = $fopen(pc_path,"w");
    $fdisplay(fd_pc,"pc,ciclos_en_id,commits");
    for (int j=0; j<512; j++) if (pcycles[j]>0) $fdisplay(fd_pc,"%0d,%0d,%0d",j*4,pcycles[j],pcommits[j]);
    $fclose(fd_pc);''')
    s=rep(s,'chequear(respuestas > 0,','chequear(respuestas == NTICKS,')
    s=rep(s,'    $finish;\n  end\n\nendmodule','    if (tests_aprobados != total_tests) $fatal(1,"Fallaron chequeos");\n    $finish;\n  end\n\nendmodule')
    put('tb_p4_final.sv',s)
    print('Variantes y testbench preparados.',flush=True)

def run(args,log):
    log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
    print('$',' '.join(map(str,args)),flush=True)
    with log.open('w') as f:
        r=subprocess.run(list(map(str,args)),stdout=f,stderr=subprocess.STDOUT,cwd=ROOT)
    if r.returncode: raise RuntimeError(f'Fallo {args[0]} ({r.returncode}): {log}\n'+'\n'.join(log.read_text(errors='replace').splitlines()[-20:]))
    return log.read_text(errors='replace')

def rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def load_ref():
    sys.path.insert(0,str(ROOT/'sw'));from hibrido import decisiones;from reference import ejecutar_orden,leer_precios,comprar_y_mantener
    return decisiones,ejecutar_orden,leer_precios,comprar_y_mantener

def synthetic():
    # Min <100; calentamiento, zonas baja/alta y giros, órdenes repetidas.
    ps=[160]*100+[60]*28+([60]+list(range(60,161))+list(range(160,59,-1)))*3
    path=ROOT/'series/prueba_adaptativa.csv';path.parent.mkdir(exist_ok=True)
    with path.open('w') as f:
        w=csv.writer(f);w.writerow(['tick','price']);w.writerows(enumerate(ps))
    # Segundo caso: escala comprimida con transición en 2048; validación ISA.
    ps=[180]*2048+([180]+list(range(180,196))+list(range(195,179,-1)))*5
    path=ROOT/'series/prueba_comprimida.csv'
    with path.open('w') as f:
        w=csv.writer(f);w.writerow(['tick','price']);w.writerows(enumerate(ps))

def reference(path):
    decide,exec_order,read_prices,bh=load_ref();p=read_prices(path); ds=list(decide(p));cash=peak=10000;shares=pending=orders=dd=0;detail=[]
    for i,((_,price),d) in enumerate(zip(p,ds)):
        cash,shares,q=exec_order(pending,price,cash,shares);orders+=q>0;w=cash+shares*price;peak=max(peak,w);dd=max(dd,peak-w)
        detail.append((i,price,pending,cash,shares,w,d));pending=d
    return p,ds,detail,{'wealth':w,'orders':orders,'fees':orders*5,'drawdown':dd,'bh':bh(p)}

def assemble(v):
    top,src,hx,mode,n=VAR[v];run(['cargo','run','--quiet','--release','--manifest-path','assembler/Cargo.toml','--',src,hx],OUT/f'{v}_asm.log')
    words=[int(l,16) for l in read(hx).split()]
    addr=508 if v=='compact' else 2000
    if len(words)*4>addr or addr>=n*4:raise RuntimeError(f'Solapamiento código/datos {v}: {len(words)} palabras')
    return words

def rtl_sources():return sorted(str(x.relative_to(ROOT)) for x in (ROOT/'rtl').rglob('*.v'))
def synth(v):
    top=VAR[v][0];j=OUT/f'{top}.json';a=OUT/f'{top}.asc';b=OUT/f'{top}.bin';b.unlink(missing_ok=True)
    y=run(['yosys','-p','read_verilog '+' '.join(rtl_sources())+f'; synth_ice40 -top {top} -json {j}; stat'],OUT/f'{v}_yosys.log')
    p=run(['nextpnr-ice40','--hx1k','--package','vq100','--freq','25','--json',j,'--pcf','goboard.pcf','--asc',a],OUT/f'{v}_pnr.log')
    run(['icepack',a,b],OUT/f'{v}_icepack.log')
    def cell(k):
        r=re.findall(rf'^\s*(?:({re.escape(k)})\s+(\d+)|(\d+)\s+({re.escape(k)}))\s*$',y,re.M);return int(r[-1][1] or r[-1][2]) if r else 0
    f=re.findall(r'Max frequency for clock.*?:\s*([\d.]+)\s*MHz',p)
    lc=re.findall(r'ICESTORM_LC:\s*(\d+)\s*/',p)
    if not f or float(f[-1])<25:raise RuntimeError('Fmax no verificada')
    return {'lut':cell('SB_LUT4'),'bram':cell('SB_RAM40_4K'),'lc':int(lc[-1]) if lc else None,'fmax':float(f[-1]),'bitstream':str(b.relative_to(ROOT))}

def cells_sim():
    opts=[os.environ.get('YOSYS_CELLS_SIM'),'/usr/share/yosys/ice40/cells_sim.v']
    if shutil.which('yosys-config'):opts.append(subprocess.check_output(['yosys-config','--datdir'],text=True).strip()+'/ice40/cells_sim.v')
    for x in opts:
        if x and Path(x).is_file():return x
    raise RuntimeError('Configura YOSYS_CELLS_SIM')

def sim(v,case,path,engine):
    folder=OUT/case;folder.mkdir(exist_ok=True);prefix=folder/v;p,ds,expected,_=reference(path);n=len(p)
    defs=[] if v=='sw' else ['-DP4_'+v.upper()];common=defs+[cells_sim()]+rtl_sources()+['tb_p4_final.sv']
    argv=[f'+SERIES={path.resolve()}',f'+DECISIONS={prefix}_decisiones.csv',f'+METRICS={prefix}_metricas.csv',f'+PCSTATS={prefix}_pc.csv']
    if engine=='verilator':
        obj=folder/f'obj_{v}';exe=obj/'sim';run(['verilator','--binary','--timing','-Wno-fatal','--top-module','tb_p4_final',f'-GNTICKS={n}','--Mdir',obj,'-o','sim','-j','2']+common,str(prefix)+'_compile.log');cmd=[exe]
    else:
        exe=str(prefix)+'.vvp';run(['iverilog','-g2012','-s','tb_p4_final',f'-Ptb_p4_final.NTICKS={n}','-o',exe]+common,str(prefix)+'_compile.log');cmd=['vvp','-n',exe]
    run(cmd+argv,str(prefix)+'_sim.log')
    got=rows(str(prefix)+'_decisiones.csv');m=rows(str(prefix)+'_metricas.csv');assert len(got)==len(m)==n,(v,case,len(got),len(m),n)
    for i,(g,x,e) in enumerate(zip(got,m,expected)):
        t=(int(g['tick']),int(g['precio']),int(g['decision'],16),int(g['caja']),int(g['acciones']),int(g['patrimonio']),int(x['decision_written'],16));assert t==e,(v,case,i,t,e);assert int(x['tick'])==i
    cy=[int(x['ciclos']) for x in m];ic=[int(x['instrucciones']) for x in m];assert max(cy)<BUDGET and min(ic)>0
    pr={int(x['pc']):(int(x['ciclos_en_id']),int(x['commits'])) for x in rows(str(prefix)+'_pc.csv')}
    info=profile(v,pr);info.update({'ticks':n,'ic':statistics.mean(ic),'ic_max':max(ic),'cycles':statistics.mean(cy),'cycles_max':max(cy),'cpi':sum(cy)/sum(ic),'cpi_max':max(c/i for c,i in zip(cy,ic)),'time_mean_us':statistics.mean(cy)*.04,'time_max_us':max(cy)*.04,'total_cycles':sum(cy),'engine':engine});print(f'PASS {case}/{v}: {n} ticks',flush=True);return info

def profile(v,pr):
    code=[];labels={};region='inicio';groups=[];ops=[]
    for l in read(VAR[v][1]).splitlines():
        l=l.split('#')[0].strip()
        if not l or l.startswith('.'):continue
        if l.endswith(':'):region=l[:-1];continue
        pc=len(code)*4;code.append((l,region));labels[pc]=region
        if re.match(r'(sub|bltu)\s',l):ops.append(pc)
        if re.fullmatch(r'add\s+x9,\s*x9,\s*x9',l) or re.match(r'slli\s+x9,\s*x9,',l):
            if groups and groups[-1][-1]==pc-4:groups[-1].append(pc)
            else:groups.append([pc])
    assert len(groups)==4
    get=lambda p:pr.get(p,(0,0));scale=[p for g in groups for p in g];events=sum(get(g[0])[1] for g in groups);instr=sum(get(p)[1] for p in scale);scale_cycles=sum(get(p)[0] for p in scale)
    byregion=Counter()
    for p,(c,i) in pr.items():byregion[labels.get(p,'otro')]+=c
    return {'scale_events':events,'scale_instr':instr,'scale_cycles':scale_cycles,'useful_ops':sum(get(p)[1] for p in ops)+events,'hot_regions':byregion.most_common(3),'profile_cycles':sum(c for c,i in pr.values())}

def report(hw,measure,isa):
    def fmt(x,n=3):return f'{x:.{n}f}' if isinstance(x,(int,float)) else '--'
    def esc(s):return str(s).replace('_',r'\_')
    tex=['% Generado por tools/cierre_p4.py. No editar métricas a mano.',r'\subsection{Síntesis y place \& route (HX1K)}',r'\begin{tabular}{lrrrrr}\toprule Variante & LUT4 & BRAM & LC & Fmax (MHz) & Timing 25 MHz\\\midrule']
    for v in VAR:
        h=hw.get(v,{});tex.append(f'{v.upper()} & {h.get("lut","--")} & {h.get("bram","--")} & {h.get("lc","--")} & {fmt(h.get("fmax"),2)} & '+('PASS' if h else 'Sin validar')+r'\\')
    tex.append(r'\bottomrule\end{tabular}')
    for case,data in measure.items():
        tex += [r'\subsection{Mediciones RTL: '+esc(case)+'}',r'\begin{tabular}{lrrrrrrr}\toprule Variante & Ticks & IC med. & IC máx. & Cic. med. & Cic. máx. & CPI glob. & $S$\\\midrule']
        base=data.get('sw')
        for v in VAR:
            m=data.get(v,{})
            if not m:continue
            speed=base['cycles']/m['cycles'] if base else None
            tex.append(f'{v.upper()} & {m["ticks"]} & {fmt(m["ic"],2)} & {m["ic_max"]} & {fmt(m["cycles"],2)} & {m["cycles_max"]} & {fmt(m["cpi"])} & {fmt(speed)}'+r'\\')
        tex += [r'\bottomrule\end{tabular}',r'\par\medskip',r'\begin{tabular}{lrrrr}\toprule Variante & CPI máx. & Tiempo med. ($\mu$s) & Tiempo máx. ($\mu$s) & MOp/s$^*$\\\midrule']
        for v,m in data.items():tex.append(f'{v.upper()} & {fmt(m["cpi_max"])} & {fmt(m["time_mean_us"])} & {fmt(m["time_max_us"])} & {fmt(m["useful_ops"]*25/m["total_cycles"])}'+r'\\')
        tex += [r'\bottomrule\end{tabular}',r'\par\smallskip $^*$ Se cuentan SUB, BLTU y una operación por cada escalado completo; se excluyen los demás opcodes. El denominador es el tiempo total medido por tick.']
        if data:
            tex.append(r'\par Margen mínimo frente a 2262 ciclos: '+', '.join(v.upper()+': '+str(BUDGET-m['cycles_max'])+' ciclos' for v,m in data.items())+'.')
        if base:
            tex.append(r'\par Bloques con más ciclos atribuidos en ID (SW): '+', '.join(esc(a)+' ('+str(b)+')' for a,b in base['hot_regions'])+'.')
            if base['scale_events']:
                f=base['scale_cycles']/base['total_cycles'];s=base['scale_instr']/base['scale_events'];pred=1/(1-f+f/s)
                tex.append(f'\\par Amdahl: $f={f:.5f}$, $s\\approx {s:.3f}$, $S_{{pred}}={pred:.4f}$. Se estima el coste de un SLLI igual al de un ADD; se incluyen stalls atribuidos al PC en ID.')
                tex.append(r'\par\smallskip\begin{tabular}{lrrrr}\toprule Variante & Escalados & AI (op/B) & MOp/s kernel & Speedup kernel\\\midrule')
                for v,m in data.items():
                    if m['scale_events'] and m['scale_instr'] and m['scale_cycles']:
                        ai=m['scale_events']/(4*m['scale_instr']);p=m['scale_events']*25/m['scale_cycles'];sp=(base['scale_cycles']/base['scale_events'])/(m['scale_cycles']/m['scale_events']);tex.append(f'{v.upper()} & {m["scale_events"]} & {ai:.4f} & {p:.3f} & {sp:.3f}'+r'\\')
                tex.append(r'\bottomrule\end{tabular}')
            else:tex.append(r'\par El escalado adaptativo no se ejecutó: $f=0$ para este kernel; Amdahl predice $S=1$. No hay punto roofline de escalado en esta serie.')
    if not measure:tex.append(r'\par Sin mediciones RTL para el nuevo código: ejecutar el banco antes de entregar.')
    if isa:tex.append(r'\par Emulación funcional de los binarios ensamblados: '+str(sum(x['ticks'] for x in isa))+' comparaciones de decisiones, cero diferencias (incluye series sintéticas y variantes). No equivale a simulación RTL.')
    # Selección: conservar SW si faltan resultados; si ambas pasan, preferir COMPACT para ahorrar RAM.
    valid=[v for v in VAR if v in hw and 'meta' in measure and v in measure['meta'] and 'adaptativa' in measure and v in measure['adaptativa']]
    chosen='compact' if 'compact' in valid else 'fixed' if 'fixed' in valid else 'sw' if 'sw' in valid else None
    tex.append(r'\par\textbf{Selección:} '+(esc(chosen.upper())+r' pasó ambas simulaciones y síntesis. '+('Se prioriza memoria reducida y escalado especializado.' if chosen=='compact' else 'Se utiliza la alternativa validada disponible.') if chosen else 'Pendiente de completar las comprobaciones RTL y timing.'))
    (OUT/'resumen.json').write_text(json.dumps({'hardware':hw,'mediciones':measure,'isa':isa,'seleccion':chosen},indent=2))
    print('Mediciones actualizadas. Selección:',chosen,flush=True)
    if chosen:(OUT/'BITSTREAM_ELEGIDO.txt').write_text(hw[chosen]['bitstream']+'\n')
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    intro = '\\section{Co-diseño hardware/software}\n\\subsection{Alternativas y dominio de operación}\nLa versión SW conserva la ALU original y ejecuta las cadenas de ADD. FIXED añade una operación SLLI especializada para desplazamientos constantes de 2, 3 y 5 bits; el operando es una diferencia de precios o extremos sin signo, acotada a 254, por lo que bastan ocho bits de entrada y trece de salida. Se sustituyen cuatro cadenas de 3, 5, 2 y 5 ADD por cuatro SLLI. Los demás desplazamientos siguen sin estar implementados con semántica RV32E completa. Se mantiene la CPU a cargo de la lectura y escritura SPI. No se modifican los umbrales o la estrategia.\n\nCOMPACT combina FIXED con una RAM de 128 palabras de 32 bits, frente a las 512 palabras originales. Al retirar once instrucciones redundantes se obtiene un programa de 119 palabras (476 bytes), sujeto a la comprobación del ensamblado del banco; se reubica el acumulador de calibración a la última palabra, dirección 508 (\\texttt{0x1FC}), separada del código. El script comprueba el tamaño realmente ensamblado y la no superposición. La reducción de capacidad lógica es del 75\\%; la ocupación BRAM física debe obtenerse de la síntesis, no inferirse directamente de esa proporción.\n\n\\subsection{Perfil, Amdahl e intensidad aritmética}\nLa fracción acelerable $f$ se calcula a partir de los ciclos atribuidos en la etapa ID a los ADD de las cadenas sustituidas, divididos por los ciclos medidos totales. Se estima $s$ mediante el cociente entre ADD ejecutados y escalados, suponiendo coste similar por instrucción. Por Amdahl,\n\\[\nS_{\\mathrm{pred}}=\\frac{1}{1-f+f/s}.\n\\]\nEl speedup global observado se calcula por el cociente de ciclos medios SW/variante. Los stalls atribuidos al PC y cambios de saltos pueden producir discrepancias. Para las series en modo fijo el kernel de escalado no se ejecuta; una prueba sintética que fuerza el modo adaptativo permite medirlo. No se asume que sea el bloque dominante: el perfil por región reporta los bloques de mayor coste real.\n\nPara el roofline del escalado se define una operación útil como multiplicar una diferencia de precios por 4, 8 o 32. Se contabilizan cuatro bytes nominales de instrucciones por instrucción ejecutada del escalado, sin accesos de datos RAM en ese kernel. Así $AI=N_{\\rm escalados}/(4N_{\\rm instrucciones})$. Esto es un roofline de tráfico de instrucciones, no de memoria de datos: los operandos están en registros. Se adoptan techos teóricos de 25 MOp/s (una operación por ciclo) y 100 MB/s (una palabra de instrucción por ciclo), no medidos por microbenchmark. El rendimiento localizado se estima con los ciclos atribuidos en ID, no con latencia aislada de la ALU. Se documenta también el rendimiento global normalizado por todo el tiempo de decisión.\n\n'
    plot=[]
    if 'adaptativa' in measure:
        for v,m in measure['adaptativa'].items():
            if m['scale_instr'] and m['scale_cycles']:
                ai=m['scale_events']/(4*m['scale_instr']);p=m['scale_events']*25/m['scale_cycles']
                plot.append(r'\addplot+[only marks,mark size=3pt] coordinates {('+str(ai)+','+str(p)+r')};\addlegendentry{'+v.upper()+'}')
    graph = r"""\begin{center}
\begin{tikzpicture}
\begin{loglogaxis}[width=.86\linewidth,height=6cm,xlabel={Intensidad nominal (op/B)},ylabel={Rendimiento (MOp/s)},xmin=.025,xmax=2,ymin=.1,ymax=45,grid=both,legend pos=south east]
\addplot[thick,domain=.025:.25,samples=20] {100*x};\addlegendentry{Techo fetch teórico}
\addplot[thick,domain=.25:2,samples=2] {25};\addlegendentry{Techo cómputo teórico}
"""+'\n'.join(plot)+r"""
\end{loglogaxis}
\end{tikzpicture}
\end{center}
Las líneas superiores son techos teóricos del modelo de tráfico de instrucciones. Los puntos, cuando existen, se obtienen del perfil RTL del escalado en la prueba adaptativa. No representan mediciones del ancho de banda físico de la RAM de datos.
"""
    versions=(OUT/'versiones.txt').read_text() if (OUT/'versiones.txt').exists() else 'Pendiente'
    fragment='% Pegar en el LaTeX existente, reemplazando el ultimo parrafo de la seccion Verificacion y presupuesto temporal.\n% Agregar al preambulo: \\usepackage{pgfplots} y \\pgfplotsset{compat=1.18}\n'+intro+'\n'+'\n'.join(tex)+'\n'
    if plot:fragment+='\n'+graph+'\n'
    fragment+=r'\subsection{Reproducibilidad}'+'\n'+r'El banco \cod{tools/cierre_p4.py} ensambla las variantes, contrasta las decisiones con Python, simula el SPI y registra los ciclos y las métricas de síntesis. Los archivos de evidencia están en \cod{bench_p4_final/}. Las siguientes son las versiones registradas por el banco:'+'\n'+r'\begin{verbatim}'+'\n'+versions+r'\end{verbatim}'+'\n'
    (REPORT_DIR/'seccion_3_3.txt').write_text(fragment,encoding='utf8')
    print('Fragmento para Overleaf:', REPORT_DIR/'seccion_3_3.txt',flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preparar',action='store_true');ap.add_argument('--engine',choices=['auto','iverilog','verilator'],default='auto');ap.add_argument('--jobs',type=int,default=3);ap.add_argument('--solo-isa',action='store_true');args=ap.parse_args()
    prepare();synthetic()
    if blobhash(read('practica_meta.csv')) != '2821ad033dbed573b54e05489cf5af83f8522002':
        # El hash Git puede diferir por CRLF; contrastar bytes originales.
        b=(ROOT/'practica_meta.csv').read_bytes()
        assert hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()=='2821ad033dbed573b54e05489cf5af83f8522002','Serie Meta distinta de la auditada'
    if args.preparar:return
    versions=[]
    for cmd in [['python3','--version'],['cargo','--version'],['rustc','--version'],['yosys','-V'],['nextpnr-ice40','--version'],['iverilog','-V'],['verilator','--version']]:
        if shutil.which(cmd[0]):versions.append(subprocess.run(cmd,capture_output=True,text=True).stdout.splitlines()[:1] or subprocess.run(cmd,capture_output=True,text=True).stderr.splitlines()[:1])
    (OUT/'versiones.txt').write_text('\n'.join(' '.join(x) for x in versions)+'\n')
    (OUT/'BITSTREAM_ELEGIDO.txt').unlink(missing_ok=True)
    (OUT/'errores.txt').unlink(missing_ok=True)
    words={v:assemble(v) for v in VAR};hw={};measure={};isa=[];errors=[]
    for path in sorted((ROOT/'series').glob('*.csv')):
        p,ds,_,_=reference(path)
        for v,code in words.items():
            _,_,_,mode,n=VAR[v];got,_=emulate(code,[x[1] for x in p],mode,n);bad=sum(x[0]!=y for x,y in zip(got,ds));assert len(got)==len(ds) and not bad,(v,path,bad);isa.append({'variant':v,'series':path.name,'ticks':len(ds)})
        print('PASS ISA 3 variantes',path.name,flush=True)
    if args.solo_isa:report(hw,measure,isa);return
    for v in VAR:
        try:hw[v]=synth(v)
        except Exception as e:errors.append(f'Síntesis {v}: {e}');print(errors[-1],flush=True)
    report(hw,measure,isa)
    engine=('verilator' if shutil.which('verilator') else 'iverilog') if args.engine=='auto' else args.engine
    for case,path in [('adaptativa',ROOT/'series/prueba_adaptativa.csv'),('meta',ROOT/'practica_meta.csv')]:
        measure[case]={}
        def one(v):
            try:return sim(v,case,path,engine)
            except Exception:
                if engine!='verilator':raise
                print(f'{v}: Verilator falló; reintento con Icarus',flush=True);return sim(v,case,path,'iverilog')
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,args.jobs)) as pool:
            fs={pool.submit(one,v):v for v in VAR}
            for f in concurrent.futures.as_completed(fs):
                v=fs[f]
                try:measure[case][v]=f.result()
                except Exception as e:errors.append(f'RTL {case}/{v}: {e}');print(errors[-1],flush=True)
                report(hw,measure,isa)
    if errors:
        (OUT/'errores.txt').write_text('\n'.join(errors));raise SystemExit('Cierre parcial: revisar bench_p4_final/errores.txt')
    print('CIERRE COMPLETO. Revisar resumen.json, fragmento externo y BITSTREAM_ELEGIDO.txt. No se programa la placa automáticamente.')
if __name__=='__main__':main()
