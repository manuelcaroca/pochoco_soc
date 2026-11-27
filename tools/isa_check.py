"""Emulación funcional de las palabras RV32E empleadas por trade.hex. No mide ciclos RTL."""
from collections import Counter
MASK=0xffffffff
BASE=0x80010000

def sign(v,n):
    return v-(1<<n) if v & (1<<(n-1)) else v

def decode(w):
    op=w&127; rd=(w>>7)&31; f=(w>>12)&7; a=(w>>15)&31; b=(w>>20)&31
    i=sign(w>>20,12)
    s=sign(((w>>25)<<5)|rd,12)
    br=sign(((w>>31)<<12)|(((w>>7)&1)<<11)|(((w>>25)&63)<<5)|(((w>>8)&15)<<1),13)
    j=sign(((w>>31)<<20)|(((w>>12)&255)<<12)|(((w>>20)&1)<<11)|(((w>>21)&1023)<<1),21)
    return op,rd,f,a,b,i,s,br,j,w&0xfffff000,w>>30&1

def emulate(words, prices, mode=0, ram_words=512):
    code=[decode(w) for w in words]; r=[0]*16; mem={}; pc=0; profile=Counter(); ticks=[]
    for price in prices:
        new=True; ic=0
        for _ in range(2000):
            ix=pc//4
            op,d,f,a,b,i,s,br,j,u,sub=code[ix]; nxt=pc+4; val=None; output=None
            profile[pc]+=1; ic+=1
            if op==0x37: val=u
            elif op==0x13:
                if f==0: val=r[a]+i
                elif f==7: val=r[a]&i
                elif f==1 and mode:
                    assert r[a] <= 255 and (i&31) in (2,3,5), (pc,r[a],i)
                    val=r[a]<<(i&31)
                else: raise ValueError((pc,op,f))
            elif op==0x33 and f==0: val=r[a]-r[b] if sub else r[a]+r[b]
            elif op==0x63:
                take={0:r[a]==r[b],1:r[a]!=r[b],6:r[a]<r[b],7:r[a]>=r[b]}[f]
                if take:nxt=pc+br
            elif op==0x6f: val=pc+4; nxt=pc+j
            elif op==0x03 and f==2:
                addr=(r[a]+i)&MASK
                if addr==BASE: val=int(new)
                elif addr==BASE+4: val=price; new=False
                else: val=mem[addr%(ram_words*4)]
            elif op==0x23 and f==2:
                addr=(r[a]+s)&MASK
                if addr==BASE+8: output=r[b]&255
                else: mem[addr%(ram_words*4)]=r[b]
            else: raise ValueError((pc,op,f))
            if val is not None and d: r[d]=val&MASK
            pc=nxt
            if output is not None:
                assert not new
                ticks.append((output,ic));break
        else: raise RuntimeError('sin decisión')
    return ticks,profile
