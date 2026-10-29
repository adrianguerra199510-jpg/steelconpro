# -*- coding: utf-8 -*-
"""Extrae de los formularios de la interfaz Qt (solo para esta migracion) el esquema de datos de la placa base -> steelconpro/data/schema_baseplate.json.
La aplicacion Electron dibuja sus formularios a partir de ese esquema (etiquetas, unidades, limites y ayudas son las de siempre)."""
import json, os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication, QFormLayout, QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QCheckBox, QLineEdit, QGroupBox
from steelconpro import ui
import re

app = QApplication.instance() or QApplication([])
win = ui.MainWindow()
names = {id(v): k for k, v in vars(win).items() if hasattr(v, "metaObject")}


def clean(html):
    return re.sub(r"<[^>]+>", "", (html or "").replace("<br>", "\n")).strip()


out = []
for title in win.BASE_TABS:
    form = win.fnamed[title]
    fields = {id(w): (path, kind, uk) for path, w, kind, uk in form.fields}
    groups = []
    for gtitle, box in form.groups.items():
        lay = box.layout()
        items = []
        for r in range(lay.rowCount()):
            lab = lay.itemAt(r, QFormLayout.LabelRole)
            fld = lay.itemAt(r, QFormLayout.FieldRole)
            span = lay.itemAt(r, QFormLayout.SpanningRole)
            label = lab.widget().text() if lab is not None and isinstance(lab.widget(), QLabel) else ""
            w = (fld or span).widget() if (fld or span) is not None else None
            if w is None:
                continue
            if id(w) in fields:
                path, kind, uk = fields[id(w)]
                it = {"path": path, "label": label or (w.text() if isinstance(w, QCheckBox) else ""), "help": clean(form._help.get(w, ""))}
                if kind == "f":
                    it.update(type="num", lo=w._lo, hi=w._hi, step=w.singleStep(), dec=w.decimals(), suffix=w.suffix().strip(), uk=uk)
                elif kind == "i":
                    it.update(type="int", lo=w.minimum(), hi=w.maximum())
                elif kind == "c":
                    it.update(type="combo", items=[w.itemText(i) for i in range(w.count())], editable=w.isEditable())
                    if path == "lug.label":                       # lista de perfiles: la interfaz usa el selector de perfiles
                        it.update(type="section")
                        it.pop("items")
                        it.pop("editable")
                elif kind == "b":
                    it.update(type="check")
                elif kind == "t":
                    it.update(type="text")
                items.append(it)
            elif isinstance(w, QLabel) and span is not None and id(w) not in names:
                items.append({"type": "note", "text": clean(w.text())})
            else:
                items.append({"type": "custom", "id": names.get(id(w), ""), "label": label})
        groups.append({"title": gtitle, "items": items})
    out.append({"title": title, "groups": groups})
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "steelconpro", "data", "schema_baseplate.json")
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(path, sum(len(g["items"]) for t in out for g in t["groups"]), "elementos")
for t in out:
    for g in t["groups"]:
        for it in g["items"]:
            if it["type"] == "custom":
                print("  custom:", t["title"], g["title"], it)
