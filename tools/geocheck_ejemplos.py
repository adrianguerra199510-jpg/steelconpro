import sys, time, glob; import os; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from steelconpro.model import load_book
from steelconpro.conn import assembly as AS, geocheck as GC
for f in sorted(glob.glob(os.path.join(ROOT, 'ejemplos', 'CN-*.scp'))):
    for k, p in enumerate(load_book(f)):
        t=time.time(); m=AS.build_model(p); t1=time.time(); iss=GC.check(m); t2=time.time()
        print(f"== {f.split('/')[-1]} [{k}] piezas {len(m.parts)} pernos {len(m.bolts)} sold {len(m.welds)}  build {t1-t:.2f}s check {t2-t1:.2f}s  {GC.summary(iss)}")
        for e in iss: print("   ", e['sev'], e['code'], e['text'][:170])
