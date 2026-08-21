"""Calcula razao de contraste WCAG 2.1 dos tokens contra os fundos. Descartavel."""
def lin(c):
    c = c/255
    return c/12.92 if c <= 0.03928 else ((c+0.055)/1.055)**2.4
def lum(h):
    h=h.lstrip('#'); r,g,b=(int(h[i:i+2],16) for i in (0,2,4))
    return 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b)
def cr(a,b):
    l1,l2=sorted((lum(a),lum(b)),reverse=True)
    return (l1+0.05)/(l2+0.05)

BG   = "#0B0E13"   # fundo base
SURF = "#161B22"   # painel

tok = {
 "text-primario":"#E8EDF4","text-secundario":"#9BA9BC","text-mudo":"#66727F",
 "compra/bid":"#3B9EFF","venda/ask":"#FF5C6C",
 "delta-pos":"#26D07C","delta-neg":"#FF5C6C","neutro":"#7D8896",
 "absorcao":"#FFB224","alerta":"#F7C948","sinal-confirmado":"#C77DFF",
 "poc":"#FFD166","vwap":"#5AC8FA","desconectado":"#FF3B30",
}
print(f"{'token':<20}{'hex':<10}{'vs #0B0E13':>12}{'vs #161B22':>12}   nivel(AA=4.5 / AA-large=3.0)")
for k,v in tok.items():
    a,b=cr(v,BG),cr(v,SURF)
    n = "AAA" if a>=7 else "AA" if a>=4.5 else "AA-large" if a>=3 else "FALHA"
    print(f"{k:<20}{v:<10}{a:>11.2f}:1{b:>11.2f}:1   {n}")
print()
print(f"{'superficie':<20}{'hex':<10}{'vs base':>12}")
for k,v in {"surface":"#161B22","surface-alta":"#1F2630","borda":"#2A323D","borda-forte":"#3D4854"}.items():
    print(f"{k:<20}{v:<10}{cr(v,BG):>11.2f}:1")
