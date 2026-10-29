# -*- coding: utf-8 -*-
"""Biblioteca de materiales: aceros, pernos de conexion, electrodos, varillas de anclaje y concretos.

Las filas de la biblioteca de AISC / ASTM / ACI se ven (en gris) y no se editan; los materiales del usuario se agregan, duplican, editan y
eliminan, y se guardan en %APPDATA%/SteelConPro/materials.json.  Se pueden exportar a / importar de un archivo JSON para llevarlos a otra PC.
Los materiales de usuario que usa un proyecto se guardan tambien dentro del archivo del proyecto.
"""
from __future__ import annotations
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTableWidget, QTableWidgetItem, QPushButton, QWidget, QHeaderView,
                               QMessageBox, QAbstractItemView, QFileDialog, QTextBrowser, QSplitter, QLineEdit)

from . import materials as M

KINDS = [("steel", "Aceros"), ("bolt", "Pernos de conexión"), ("electrode", "Electrodos"), ("anchor", "Varillas de anclaje"), ("concrete", "Concretos")]


class _Spec:
    """Columnas de una categoria: (titulo, clave, tipo) con tipo 's' texto, 'S' esfuerzo (unidad del usuario), 'n' numero, 'b' si/no."""

    def __init__(self, cols, new, builtin_names, default_note=""):
        self.cols, self.new, self.builtin_names = cols, new, builtin_names


SPECS = {
    "steel": _Spec([("Nombre", "name", "s"), ("Fy", "Fy", "S"), ("Fu", "Fu", "S"), ("E", "E", "S"), ("ν", "nu", "n"), ("ρ (kg/m³)", "rho", "n"), ("Nota", "note", "s")],
                   {"name": "Acero nuevo", "Fy": 50.0, "Fu": 65.0, "E": 29000.0, "nu": 0.30, "rho": 7850.0, "note": ""}, None),
    "bolt": _Spec([("Grado", "name", "s"), ("Fnt", "Fnt", "S"), ("Fnv", "Fnv", "S"), ("Nota", "note", "s")],
                  {"name": "Perno nuevo", "Fnt": 90.0, "Fnv": 54.0, "note": ""}, None),
    "electrode": _Spec([("Electrodo", "name", "s"), ("FEXX", "FEXX", "S")], {"name": "E70XX-nuevo", "FEXX": 70.0}, None),
    "anchor": _Spec([("Nombre", "name", "s"), ("Fy", "Fy", "S"), ("Fu", "Fu", "S"), ("Ø máx. (in)", "dmax", "n"), ("Dúctil", "ductile", "b"), ("Nota", "note", "s")],
                    {"name": "Anclaje nuevo", "Fy": 55.0, "Fu": 75.0, "dmax": 4.0, "ductile": True, "note": ""}, None),
    "concrete": _Spec([("Nombre", "name", "s"), ("f'c", "fc", "S"), ("λ", "lam", "n"), ("Nota", "note", "s")],
                      {"name": "Concreto nuevo", "fc": 4.0, "lam": 1.0, "note": ""}, None),
}


def _builtin(kind):
    """[dict] de los materiales de la biblioteca (no editables) de una categoria."""
    if kind == "steel":
        seen, out = set(), []
        for m in M.PLATE_STEELS + M.SHAPE_STEELS:
            if m.name in seen or M.is_extra("steel", m.name):
                continue
            seen.add(m.name)
            out.append({"name": m.name, "Fy": m.Fy, "Fu": m.Fu, "E": m.E, "nu": m.nu, "rho": m.rho, "note": m.note})
        return out
    if kind == "bolt":
        return [{"name": b.name, "Fnt": b.Fnt, "Fnv": b.Fnv, "note": b.note} for b in M.bolt_grades() if b.name in M.BUILTIN_BOLTS]
    if kind == "electrode":
        return [{"name": e.name, "FEXX": e.FEXX} for e in M.ELECTRODES if not M.is_extra("electrode", e.name)]
    if kind == "anchor":
        return [{"name": a.name, "Fy": a.Fy, "Fu": a.Fu, "dmax": a.dmax, "ductile": a.ductile, "note": a.note}
                for a in M.ANCHOR_STEELS if not M.is_extra("anchor", a.name)]
    return [{"name": c.name, "fc": c.fc, "lam": c.lam, "note": c.note} for c in M.CONCRETES if not M.is_extra("concrete", c.name)]


class MaterialsLibrary(QDialog):
    def __init__(self, us, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Biblioteca de materiales")
        self.resize(1050, 640)
        self.us = us
        self.data = {k: [dict(d) for d in v] for k, v in M.user_materials().items()}
        for k, _t in KINDS:
            self.data.setdefault(k, [])
        self.tables, self._busy = {}, False
        root = QVBoxLayout(self)
        root.addWidget(QLabel(f"Esfuerzos en {us.S}. Las filas grises son de la biblioteca (AISC 360-22, ASTM, ACI 318) y no se editan: para partir de una, use "
                              "<b>Duplicar</b>. Los materiales propios quedan en todas las listas del programa y se guardan dentro de cada proyecto que los use."))
        root.itemAt(0).widget().setWordWrap(True)
        self.tabs = QTabWidget()
        for kind, title in KINDS:
            self.tabs.addTab(self._page(kind), title)
        root.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        for txt, fn in (("Exportar materiales propios...", self._export), ("Importar...", self._import)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        bs = QPushButton("Guardar y cerrar")
        bs.setDefault(True)
        bs.clicked.connect(self._save)
        bc = QPushButton("Cancelar")
        bc.clicked.connect(self.reject)
        row.addWidget(bs)
        row.addWidget(bc)
        root.addLayout(row)

    # ------------------------------------------------------------------ paginas
    def _page(self, kind):
        spec = SPECS[kind]
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        ed = QLineEdit()
        ed.setPlaceholderText("Buscar...")
        top.addWidget(ed)
        lay.addLayout(top)
        sp = QSplitter(Qt.Horizontal)
        t = QTableWidget(0, len(spec.cols))
        t.setHorizontalHeaderLabels([self._head(c) for c in spec.cols])
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(24)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        t.setColumnWidth(0, 210)
        for j in range(1, len(spec.cols) - 1):
            t.setColumnWidth(j, 80)
        t.itemChanged.connect(lambda it, k=kind: self._edited(k, it))
        t.itemSelectionChanged.connect(lambda k=kind: self._detail(k))
        sp.addWidget(t)
        det = QTextBrowser()
        det.setMinimumWidth(260)
        sp.addWidget(det)
        sp.setSizes([760, 260])
        lay.addWidget(sp, 1)
        row = QHBoxLayout()
        for txt, fn in (("Nuevo", lambda _c=False, k=kind: self._new(k)), ("Duplicar", lambda _c=False, k=kind: self._dup(k)),
                        ("Eliminar", lambda _c=False, k=kind: self._del(k))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.tables[kind] = (t, det, ed)
        ed.textChanged.connect(lambda _s, k=kind: self._fill(k))
        self._fill(kind)
        return w

    def _head(self, col):
        title, _key, typ = col
        return f"{title} ({self.us.S})" if typ == "S" else title

    def _rows(self, kind):
        """[(dict, es_del_usuario)]: biblioteca primero y luego los materiales del usuario (en el mismo orden de self.data)."""
        return [(d, False) for d in _builtin(kind)] + [(d, True) for d in self.data[kind]]

    def _fill(self, kind):
        t, _det, ed = self.tables[kind]
        spec = SPECS[kind]
        q = ed.text().strip().lower()
        rows = [(d, u) for d, u in self._rows(kind) if not q or q in str(d.get("name", "")).lower() or q in str(d.get("note", "")).lower()]
        self._busy = True
        t.setRowCount(len(rows))
        grey = QColor("#8b95a3")
        for i, (d, user) in enumerate(rows):
            for j, (_title, key, typ) in enumerate(spec.cols):
                v = d.get(key, "")
                if typ == "S":
                    txt = self.us.fmt("S", float(v)) if v != "" else ""
                elif typ == "b":
                    txt = "sí" if v else "no"
                elif typ == "n":
                    txt = f"{float(v):g}" if v != "" else ""
                else:
                    txt = str(v)
                it = QTableWidgetItem(txt)
                it.setData(Qt.UserRole, id(d))
                if typ in ("S", "n"):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if user:
                    it.setFlags(it.flags() | Qt.ItemIsEditable)
                else:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    it.setForeground(grey)
                t.setItem(i, j, it)
        self._busy = False
        self._shown = getattr(self, "_shown", {})
        self._shown[kind] = rows
        self._detail(kind)

    def _cur(self, kind):
        t = self.tables[kind][0]
        r = t.currentRow()
        rows = self._shown.get(kind, [])
        return rows[r] if 0 <= r < len(rows) else (None, False)

    # ------------------------------------------------------------------ edicion
    def _edited(self, kind, it):
        if self._busy:
            return
        d, user = self._cur_by_item(kind, it)
        if d is None or not user:
            return
        _title, key, typ = SPECS[kind].cols[it.column()]
        txt = it.text().strip()
        try:
            if typ == "S":
                d[key] = self.us.inn("S", float(txt.replace(",", "")))
            elif typ == "n":
                d[key] = float(txt.replace(",", ""))
            elif typ == "b":
                d[key] = txt.lower().startswith(("s", "y", "1", "t"))
            else:
                d[key] = txt
        except ValueError:
            QMessageBox.warning(self, "Materiales", f"«{txt}» no es un número.")
        self._fill(kind)

    def _cur_by_item(self, kind, it):
        rows = self._shown.get(kind, [])
        r = it.row()
        return rows[r] if 0 <= r < len(rows) else (None, False)

    def _new(self, kind):
        self.data[kind].append(dict(SPECS[kind].new))
        self.tables[kind][2].setText("")
        self._fill(kind)
        t = self.tables[kind][0]
        t.selectRow(t.rowCount() - 1)

    def _dup(self, kind):
        d, _user = self._cur(kind)
        if d is None:
            return
        n = dict(d)
        n["name"] = f"{d['name']} (copia)"
        if "note" in n:
            n["note"] = "usuario"
        self.data[kind].append(n)
        self._fill(kind)
        t = self.tables[kind][0]
        t.selectRow(t.rowCount() - 1)

    def _del(self, kind):
        d, user = self._cur(kind)
        if d is None or not user:
            QMessageBox.information(self, "Materiales", "Solo se pueden eliminar los materiales propios (filas con texto negro).")
            return
        self.data[kind] = [x for x in self.data[kind] if x is not d]
        self._fill(kind)

    def _detail(self, kind):
        det = self.tables[kind][1]
        d, user = self._cur(kind)
        if d is None:
            det.setHtml("")
            return
        us = self.us
        rows = []
        if kind == "steel":
            E, nu = float(d.get("E", 29000.0)), float(d.get("nu", 0.3))
            rows = [("Fy", us.q("S", d["Fy"])), ("Fu", us.q("S", d["Fu"])), ("E", us.q("S", E)), ("G = E/2(1+ν)", us.q("S", E / (2 * (1 + nu)))), ("ν", f"{nu:g}"),
                    ("ρ", f"{float(d.get('rho', 7850.0)):g} kg/m³"), ("Fu/Fy", f"{d['Fu'] / max(d['Fy'], 1e-9):.3f}"), ("εy = Fy/E", f"{d['Fy'] / E * 100:.3f} %")]
        elif kind == "bolt":
            rows = [("Fnt (tracción)", us.q("S", d["Fnt"])), ("Fnv (cortante)", us.q("S", d["Fnv"])), ("Fnv/Fnt", f"{d['Fnv'] / max(d['Fnt'], 1e-9):.3f}")]
        elif kind == "electrode":
            rows = [("FEXX", us.q("S", d["FEXX"])), ("Filete: 0.60·FEXX", us.q("S", 0.6 * d["FEXX"]))]
        elif kind == "anchor":
            rows = [("Fy", us.q("S", d["Fy"])), ("Fu", us.q("S", d["Fu"])), ("Ø máximo", f"{d.get('dmax', 0):g} in"), ("Dúctil (ACI 17.5.3)", "sí" if d.get("ductile", True) else "no")]
        else:
            fc = float(d["fc"])
            rows = [("f'c", us.q("S", fc)), ("λ", f"{d.get('lam', 1.0):g}"), ("Ec = 57000·√f'c (psi)", us.q("S", 57.0 * (fc * 1000.0) ** 0.5))]
        body = "".join(f"<tr><td style='padding-right:10px'><b>{a}</b></td><td>{b}</td></tr>" for a, b in rows)
        det.setHtml(f"<div style='font-size:9pt'><b>{d['name']}</b><br><span style='color:#7f7f7f'>{'material propio' if user else 'biblioteca'}"
                    f"{(' · ' + str(d['note'])) if d.get('note') and d.get('note') != 'usuario' else ''}</span><br><br><table>{body}</table></div>")

    # ------------------------------------------------------------------ archivo
    def _collect(self):
        out = {}
        for kind, _t in KINDS:
            lst = []
            for d in self.data[kind]:
                nm = str(d.get("name", "")).strip()
                if nm:
                    lst.append({**d, "name": nm})
            out[kind] = lst
        return out

    def _save(self):
        data = self._collect()
        for kind, lst in data.items():
            names = [d["name"] for d in lst]
            if len(set(names)) != len(names):
                QMessageBox.warning(self, "Materiales", f"Hay nombres repetidos en «{dict(KINDS)[kind]}».")
                return
            clash = [n for n in names if n in {b["name"] for b in _builtin(kind)}]
            if clash:
                QMessageBox.warning(self, "Materiales", f"«{clash[0]}» ya existe en la biblioteca: use otro nombre.")
                return
        old = {k: [d["name"] for d in v] for k, v in M.user_materials().items()}
        M.save_user_materials(data)
        self._unregister_removed(old, data)
        self.accept()

    @staticmethod
    def _unregister_removed(old, new):
        """Quita de las listas en uso lo que el usuario elimino (la sesion actual sigue sin reiniciarse)."""
        for kind, names in old.items():
            gone = set(names) - {d["name"] for d in new.get(kind, [])}
            if not gone:
                continue
            if kind == "steel":
                for lst in (M.PLATE_STEELS, M.SHAPE_STEELS):
                    lst[:] = [x for x in lst if x.name not in gone]
            elif kind == "electrode":
                M.ELECTRODES[:] = [x for x in M.ELECTRODES if x.name not in gone]
            elif kind == "anchor":
                M.ANCHOR_STEELS[:] = [x for x in M.ANCHOR_STEELS if x.name not in gone]
            elif kind == "concrete":
                M.CONCRETES[:] = [x for x in M.CONCRETES if x.name not in gone]
            elif kind == "bolt":
                from .conn import common, specs
                for n in gone:
                    common.FNT.pop(n, None)
                    common.FNV.pop(n, None)
                    if n in specs.BOLT_GRADES:
                        specs.BOLT_GRADES.remove(n)

    def _export(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Exportar materiales propios", "materiales_steelconpro.json", "JSON (*.json)")
        if not fn:
            return
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(self._collect(), f, indent=1, ensure_ascii=False)
        QMessageBox.information(self, "Materiales", f"Exportado a {fn}")

    def _import(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Importar materiales", "", "JSON (*.json)")
        if not fn:
            return
        try:
            with open(fn, encoding="utf-8") as f:
                d = json.load(f)
            n = 0
            for kind, _t in KINDS:
                have = {x["name"] for x in self.data[kind]}
                for x in d.get(kind, []):
                    if x.get("name") and x["name"] not in have:
                        self.data[kind].append(dict(x))
                        n += 1
        except Exception as e:
            QMessageBox.warning(self, "Importar", f"No se pudo leer el archivo: {e}")
            return
        for kind, _t in KINDS:
            self._fill(kind)
        QMessageBox.information(self, "Importar", f"{n} materiales importados (los que ya existían se omitieron).")
