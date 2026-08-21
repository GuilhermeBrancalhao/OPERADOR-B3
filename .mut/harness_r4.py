"""Harness R4: sha256 antes/depois, registro EM VOO, restauracao no finally.
Casa ancoras em texto com newline universal; preserva CRLF na escrita."""
import json, subprocess, sys, pathlib, hashlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
EM_VOO = RAIZ / ".mut" / "r4_em_voo.json"
CR = chr(13); LF = chr(10); CRLF = CR + LF

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def rodar():
    r = subprocess.run([sys.executable,"-m","pytest","tests/","-q","--tb=no","-p","no:cacheprovider"],
                       cwd=RAIZ, capture_output=True, text=True)
    s=(r.stdout or "")+(r.stderr or "")
    return r.returncode, (s.strip().splitlines()[-1] if s.strip() else "")

def main(tab):
    tabela=json.loads(pathlib.Path(tab).read_text(encoding="utf-8"))
    res=[]
    for m in tabela:
        alvo=RAIZ/m["arquivo"]
        original=alvo.read_bytes()
        h0=hashlib.sha256(original).hexdigest()
        crlf = CRLF.encode() in original
        texto=original.decode("utf-8").replace(CRLF, LF)
        if m["de"] not in texto:
            res.append((m["id"],"ERRO_ANCORA","string ausente")); print(f'{m["id"]:6} ERRO_ANCORA  {m["arquivo"]}',flush=True); continue
        n=texto.count(m["de"]); esp=m.get("n",1)
        if n!=esp:
            res.append((m["id"],"ERRO_ANCORA",f"{n} ocorrencias, esperado {esp}")); print(f'{m["id"]:6} ERRO_ANCORA {n} ocorr (esp {esp})',flush=True); continue
        EM_VOO.write_text(json.dumps({"id":m["id"],"arquivo":m["arquivo"],"sha256_original":h0,
                                      "de":m["de"],"para":m["para"]},indent=1,ensure_ascii=False),encoding="utf-8")
        try:
            novo=texto.replace(m["de"],m["para"])
            if crlf: novo=novo.replace(LF, CRLF)
            alvo.write_bytes(novo.encode("utf-8"))
            rc,linha=rodar()
        finally:
            alvo.write_bytes(original)
            h1=sha(alvo)
            assert h1==h0, f"RESTAURACAO FALHOU {m['id']} {m['arquivo']}"
            EM_VOO.unlink(missing_ok=True)
        estado="MORTA" if rc!=0 else "SOBREVIVEU"
        res.append((m["id"],estado,linha))
        print(f'{m["id"]:6} {estado:11} sha_ok  {linha}   <- {m["desc"][:55]}',flush=True)
    print("\n=== RESUMO ===")
    sob=[r for r in res if r[1]=="SOBREVIVEU"]; err=[r for r in res if r[1]=="ERRO_ANCORA"]
    print(f"total={len(res)} mortas={len(res)-len(sob)-len(err)} SOBREVIVERAM={len(sob)} erro_ancora={len(err)}")
    for r in sob: print("  SOBREVIVEU:",r[0])
    for r in err: print("  ERRO_ANCORA:",r[0],r[2])
    json.dump(res,open(RAIZ/".mut"/(pathlib.Path(tab).stem+"_res.json"),"w"),indent=1)

if __name__=="__main__": main(sys.argv[1])
