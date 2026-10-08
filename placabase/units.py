# -*- coding: utf-8 -*-
"""
Unidades internas del programa:  pulgada (in), kip, ksi.

Motivo: la base de datos AISC v14.1 y los diametros de perno en pulgadas son
nativos en este sistema, y las formulas de ACI 318-19 / AISC 360 en unidades
inglesas evitan factores de conversion enterrados en las ecuaciones.

Todas las funciones de ACI que internamente requieren psi/lb hacen la
conversion de forma explicita y devuelven kip.
"""
from __future__ import annotations
import math

# ---------------------------------------------------------------- longitud
IN_TO_MM = 25.4
MM_TO_IN = 1.0 / 25.4
FT_TO_IN = 12.0

# ---------------------------------------------------------------- fuerza
KIP_TO_KN = 4.4482216
KN_TO_KIP = 1.0 / KIP_TO_KN
KIP_TO_LB = 1000.0
LB_TO_KIP = 1e-3

# ---------------------------------------------------------------- esfuerzo
KSI_TO_MPA = 6.8947573
MPA_TO_KSI = 1.0 / KSI_TO_MPA
KSI_TO_PSI = 1000.0
PSI_TO_KSI = 1e-3

# ---------------------------------------------------------------- momento
KIPIN_TO_KNM = KIP_TO_KN * IN_TO_MM / 1000.0      # kip*in -> kN*m
KNM_TO_KIPIN = 1.0 / KIPIN_TO_KNM

# ---------------------------------------------------------------- material
ES_KSI = 29000.0          # modulo de elasticidad del acero
NU_STEEL = 0.30
NU_CONC = 0.20


def Ec_ksi(fc_ksi: float, wc_pcf: float = 145.0) -> float:
    """ACI 318-19 19.2.2.1(b): Ec = 57000*sqrt(f'c)  [psi]  para wc normal."""
    return 57000.0 * math.sqrt(max(fc_ksi, 1e-6) * KSI_TO_PSI) * PSI_TO_KSI


# ---------------------------------------------------------------- utilidades
def frac_to_float(txt: str) -> float:
    """'1-1/4' , '1 1/4' , '3/4' , '1.25'  ->  float."""
    t = str(txt).strip().replace("-", " ").replace('"', "")
    if not t:
        return 0.0
    tot, ok = 0.0, False
    for part in t.split():
        if "/" in part:
            a, b = part.split("/")
            tot += float(a) / float(b)
        else:
            tot += float(part)
        ok = True
    return tot if ok else 0.0


def float_to_frac(x: float, denom: int = 16) -> str:
    """1.25 -> '1-1/4'   (para rotular diametros y espesores)."""
    if x <= 0:
        return "0"
    whole = int(math.floor(x + 1e-9))
    rem = x - whole
    n = int(round(rem * denom))
    if n == denom:
        whole += 1
        n = 0
    if n == 0:
        return str(whole)
    g = math.gcd(n, denom)
    n, d = n // g, denom // g
    return f"{whole}-{n}/{d}" if whole else f"{n}/{d}"


class U:
    """Conversor de presentacion.  Interno siempre in/kip/ksi."""

    def __init__(self, metric: bool = False):
        self.metric = metric

    # --- etiquetas
    @property
    def L(self):   return "mm" if self.metric else "in"
    @property
    def F(self):   return "kN" if self.metric else "kip"
    @property
    def M(self):   return "kN·m" if self.metric else "kip·in"
    @property
    def S(self):   return "MPa" if self.metric else "ksi"
    @property
    def A(self):   return "mm²" if self.metric else "in²"

    # --- interno -> presentacion
    def l(self, v):  return v * IN_TO_MM if self.metric else v
    def f(self, v):  return v * KIP_TO_KN if self.metric else v
    def m(self, v):  return v * KIPIN_TO_KNM if self.metric else v
    def s(self, v):  return v * KSI_TO_MPA if self.metric else v
    def a(self, v):  return v * IN_TO_MM ** 2 if self.metric else v

    # --- presentacion -> interno
    def il(self, v): return v * MM_TO_IN if self.metric else v
    def if_(self, v): return v * KN_TO_KIP if self.metric else v
    def im(self, v): return v * KNM_TO_KIPIN if self.metric else v
    def is_(self, v): return v * MPA_TO_KSI if self.metric else v
    def ia(self, v): return v * MM_TO_IN ** 2 if self.metric else v


# ==================================================================== UNIDADES
# Factores: valor_interno = valor_mostrado * factor
LEN_UNITS = {
    "in": 1.0,
    "ft": 12.0,
    "mm": 1.0 / 25.4,
    "cm": 1.0 / 2.54,
    "m":  1000.0 / 25.4,
}

FORCE_UNITS = {           # a kip
    "kip":  1.0,
    "lbf":  1.0e-3,
    "kN":   KN_TO_KIP,
    "N":    KN_TO_KIP * 1e-3,
    "tonf": 2.2046226,    # tonelada-fuerza metrica (1000 kgf)
    "kgf":  2.2046226e-3,
}

STRESS_UNITS = {          # a ksi
    "ksi":     1.0,
    "psi":     1.0e-3,
    "MPa":     MPA_TO_KSI,
    "kgf/cm2": 0.0142233,
    "kgf/mm2": 1.42233,
}

MOMENT_UNITS = {          # a kip*in
    "kip·in":  1.0,
    "kip·ft":  12.0,
    "lbf·ft":  0.012,
    "kN·m":    KN_TO_KIP * 1000.0 / 25.4,
    "kN·mm":   KN_TO_KIP / 25.4,
    "N·m":     KN_TO_KIP / 25.4,
    "tonf·m":  2.2046226 * 1000.0 / 25.4,
    "kgf·m":   2.2046226e-3 * 1000.0 / 25.4,
    "kgf·cm":  2.2046226e-3 * 10.0 / 25.4,
}

DEFAULT_SETS = {
    "Imperial (in, kip, ksi)":  ("in", "kip", "ksi"),
    "SI (mm, kN, MPa)":         ("mm", "kN", "MPa"),
    "SI (m, kN, MPa)":          ("m", "kN", "MPa"),
    "Metrico tecnico (cm, tonf, kgf/cm2)": ("cm", "tonf", "kgf/cm2"),
}


class UnitSet:
    """Conversion entre las unidades que elige el usuario y las internas
    (in, kip, ksi).  El momento se deriva de fuerza x longitud y el modulo
    de balasto de fuerza / longitud^3."""

    def __init__(self, length="in", force="kip", stress="ksi", moment=None):
        self.moment = moment if (moment in MOMENT_UNITS) else None
        self.set_units(length, force, stress, moment)

    def set_units(self, length=None, force=None, stress=None, moment=None):
        if moment is not None:
            self.moment = moment if moment in MOMENT_UNITS else None
        if length:
            self.length = length if length in LEN_UNITS else "in"
        if force:
            self.force = force if force in FORCE_UNITS else "kip"
        if stress:
            self.stress = stress if stress in STRESS_UNITS else "ksi"
        self.fl = LEN_UNITS[self.length]
        self.ff = FORCE_UNITS[self.force]
        self.fs = STRESS_UNITS[self.stress]
        self.fm = MOMENT_UNITS[self.moment] if self.moment else self.ff * self.fl

    # ------------------------------------------------------------ etiquetas
    @property
    def L(self):  return self.length
    @property
    def F(self):  return self.force
    @property
    def S(self):  return self.stress
    @property
    def M(self):  return self.moment if self.moment else f"{self.force}·{self.length}"
    @property
    def A(self):  return f"{self.length}²"
    @property
    def K(self):  return f"{self.force}/{self.length}³"
    @property
    def LF(self): return f"{self.force}/{self.length}"

    def label(self, kind):
        return {"L": self.L, "F": self.F, "M": self.M, "S": self.S,
                "A": self.A, "K": self.K, "LF": self.LF, "-": ""}.get(kind, "")

    # ------------------------------------------- interno -> lo que se muestra
    def out(self, kind, v):
        f = self._factor(kind)
        return v / f if f else v

    # ------------------------------------------- lo que se escribe -> interno
    def inn(self, kind, v):
        return v * self._factor(kind)

    def _factor(self, kind):
        if kind == "L":  return self.fl
        if kind == "F":  return self.ff
        if kind == "M":  return self.fm
        if kind == "S":  return self.fs
        if kind == "A":  return self.fl ** 2
        if kind == "K":  return self.ff / self.fl ** 3
        if kind == "LF": return self.ff / self.fl
        return 1.0

    # ---------------------------------------------------------------- formato
    def fmt(self, kind, v, dec=None):
        x = self.out(kind, v)
        if dec is None:
            a = abs(x)
            dec = 0 if a >= 1000 else (1 if a >= 100 else (2 if a >= 1 else 4))
        return f"{x:,.{dec}f}"

    def q(self, kind, v, dec=None):
        """Valor + unidad."""
        return f"{self.fmt(kind, v, dec)} {self.label(kind)}".strip()

    def step(self, kind):
        """Paso razonable del control numerico segun la unidad elegida."""
        if kind == "L":
            return {"in": 0.25, "ft": 0.05, "mm": 5.0, "cm": 0.5, "m": 0.005}[self.length]
        if kind == "F":
            return {"kip": 5.0, "lbf": 500.0, "kN": 25.0, "N": 5000.0,
                    "tonf": 2.5, "kgf": 500.0}[self.force]
        if kind == "M":
            return max(0.1, round(10.0 * self.step("F") * self.step("L") /
                                  max(self.fm / (self.ff * self.fl), 1e-9), 2))
        if kind == "S":
            return {"ksi": 1.0, "psi": 100.0, "MPa": 5.0,
                    "kgf/cm2": 50.0, "kgf/mm2": 0.5}[self.stress]
        return 0.1

    def dec(self, kind):
        if kind == "L":
            return {"in": 3, "ft": 4, "mm": 1, "cm": 2, "m": 4}[self.length]
        if kind == "F":
            return {"kip": 2, "lbf": 0, "kN": 2, "N": 0, "tonf": 3, "kgf": 0}[self.force]
        if kind == "M":
            return 2
        if kind == "S":
            return {"ksi": 2, "psi": 0, "MPa": 1, "kgf/cm2": 0, "kgf/mm2": 2}[self.stress]
        return 3


# ------------------------------------------------- pegado desde Excel / texto
def parse_number(txt: str):
    """Numero de una celda de Excel. Acepta coma o punto decimal y separador de
    miles ('1,234.5', '1.234,5', '12,5', '12.5', '-3', '1 234,5'). None si no es numero."""
    t = txt.strip().replace(" ", "").replace(" ", "")
    if not t:
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):          # 1.234,5
            t = t.replace(".", "").replace(",", ".")
        else:                                    # 1,234.5
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".") if t.count(",") == 1 else t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def parse_xy_clipboard(text: str) -> list:
    """Filas (x, y) a partir de texto copiado de Excel (columnas por tabulacion, filas por
    salto de linea; tambien acepta ';' o espacios). De cada fila toma los dos primeros numeros;
    las filas sin dos numeros (encabezados, rotulos) se ignoran."""
    import re
    out = []
    for line in text.replace("\r", "").split("\n"):
        if not line.strip():
            continue
        cells = line.split("\t") if "\t" in line else (
            line.split(";") if ";" in line else re.split(r"\s+", line.strip()))
        nums = [n for n in (parse_number(c) for c in cells) if n is not None]
        if len(nums) >= 2:
            out.append((nums[0], nums[1]))
    return out
