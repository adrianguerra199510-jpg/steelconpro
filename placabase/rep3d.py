# -*- coding: utf-8 -*-
"""Empaqueta el resultado crudo del analisis 3D (mesh3d.full_3d) en un `Fem3D` para el veredicto y la memoria."""
from __future__ import annotations
import tempfile
import traceback
from pathlib import Path

from .fem_checks import Fem3D
from . import mesh3d, view3d, plan3d


def make_rep3d(prj, res) -> dict | None:
    """Imagenes de von Mises y deformada (con etiqueta del maximo) y resumen numerico."""
    try:
        folder = Path(getattr(res, "folder", "") or tempfile.mkdtemp())
        folder.mkdir(parents=True, exist_ok=True)
        xs = list(res.nodes.values())
        dim = max(max(q[i] for q in xs) - min(q[i] for q in xs) for i in range(3))
        sc = 0.05 * dim / res.umax if res.umax > 0 else 0.0
        sc = 0.0 if sc <= 0 else max(1.0, float(f"{min(sc, 5000.0):.1g}"))
        vm = view3d.render_result_png(res, prj, "vm", str(folder / "reporte_vonmises.png"))
        de = view3d.render_result_png(res, prj, "u", str(folder / "reporte_deformada.png"), sc)
        nvm = max(res.vm, key=res.vm.get) if res.vm else None
        plan = plan3d.render_all(prj, res, str(folder))
        return dict(fast=mesh3d.is_fast_mesh(prj), lc=getattr(res, "lc", 0.0), vm_avg=getattr(res, "vm_avg", None),
                    vm=vm, u=de, plan=plan, scale=sc, n_nodes=res.n_nodes, n_elems=res.n_elems,
                    umax=res.umax, vmmax=res.vmmax, vm_node=nvm)
    except Exception:
        traceback.print_exc()
        return None


def make_fem(prj, res, rep=None) -> Fem3D:
    """`res` es el Result3D de mesh3d.full_3d.  La firma es la del proyecto con que se corrio."""
    if rep is None:
        rep = make_rep3d(prj, res)
    pp = getattr(res, "peeq_parts", None) or {}
    pk = pp["plate"]["raw"] if "plate" in pp else None
    return Fem3D(peeq=pk, peeq_parts=pp, peeq_r=max(prj.plate.tp, getattr(res, 'lc', 0.0) / 1.2), post=getattr(res, "post", None), vm_avg=getattr(res, "vm_avg", None), rep=rep,
                 fast=mesh3d.is_fast_mesh(prj), lc=getattr(res, "lc", 0.0), n_nodes=res.n_nodes, n_elems=res.n_elems,
                 umax=res.umax, vmmax=res.vmmax, folder=getattr(res, "folder", ""),
                 msg=getattr(getattr(res, "post", None), "msg", ""), sig=prj.sig3d())
