"""Regresion de BOT-051.6.1 (Signal Quality Production UI Cleanup).

No hay tooling de test para JS en este proyecto (sin package.json/framework,
ver reports/BOT-051.6-* seccion 11) -- el comportamiento real del popover se
verifica invocando las funciones ya cargadas en el navegador contra la
pagina real (ver reports/BOT-051.6.1-*). Este archivo es la contraparte
AUTOMATIZADA y repetible: un guard de regresion a nivel de CODIGO FUENTE
(no ejecuta JS) que falla si alguien reintroduce la calificacion legacy
(Divergencia/Tendencia/CVP/Nodo/Total) dentro del popover productivo, o si
la tarjeta de acumulacion OOS deja de ser full-width sin que se note.

No reemplaza la verificacion visual (seccion 16 del enunciado) -- la
complementa, igual que test_signal_quality_production_ui.py (BOT-051.6)
complementa la verificacion visual de ESE ticket sin sustituirla.

Uso:
    python panel/test_signal_quality_popover_cleanup.py
"""
import re
import sys
from pathlib import Path

PANEL_DIR = Path(__file__).resolve().parent
APP_JS = PANEL_DIR / "app.js"
INDEX_HTML = PANEL_DIR / "index.html"

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


def _function_source(js: str, name: str) -> str:
    """Extrae el cuerpo de `function name(...) { ... }` contando llaves --
    suficiente para JS sin llaves dentro de strings/regex en esta funcion
    puntual (scoreBadge()/signalQualitySection() no las tienen)."""
    m = re.search(rf"function {re.escape(name)}\([^)]*\)\s*{{", js)
    if not m:
        raise AssertionError(f"no se encontro function {name}(...) en app.js")
    start = m.end() - 1
    depth = 0
    for i in range(start, len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[start:i + 1]
    raise AssertionError(f"no se pudo cerrar el cuerpo de {name}()")


def main() -> int:
    js = APP_JS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")

    print("=== A. scoreBadge() -- calificacion legacy eliminada del popover ===")
    score_badge_src = _function_source(js, "scoreBadge")
    legacy_tokens = ["Divergencia", "Tendencia", "CVP", "Nodo", "divergencia_score",
                      "tendencia_score", "cvp_score", "nodo_score", "score-total", "Total "]
    leaked = [t for t in legacy_tokens if t in score_badge_src]
    check("ningun token de la calificacion legacy aparece dentro de scoreBadge()",
          not leaked, f"leaked={leaked}")
    check("scoreBadge() sigue delegando en signalQualitySection() (Signal Quality v1)",
          "signalQualitySection(" in score_badge_src)
    check("scoreBadge() no muestra un total/valor numerico en el icono (solo el simbolo fijo, sin +N/-N)",
          re.search(r'score-icon["\'][^>]*>\S+\$\{', score_badge_src) is None)

    print("\n=== B. fmtSigned() -- dead code (solo lo usaba la calificacion legacy) ===")
    check("fmtSigned ya no esta definida en app.js (removida junto con su unico uso)",
          "function fmtSigned" not in js)

    print("\n=== C. signalQualitySection() -- Signal Quality v1 sigue completo ===")
    sq_section_src = _function_source(js, "signalQualitySection")
    for factor in ("Momentum", "Alignment", "Structure", "Context", "Direction"):
        check(f"signalQualitySection() sigue renderizando {factor}", factor in sq_section_src)
    check('titulo "al crear la LIMIT (t0)" preservado (seccion 8, CRITICO)',
          "al crear la LIMIT (t0)" in sq_section_src)

    print("\n=== D. signalQualityFactor() -- AVAILABLE/UNAVAILABLE+reason y NEUTRAL!=UNAVAILABLE intactos ===")
    sq_factor_src = _function_source(js, "signalQualityFactor")
    check('"Reason: <razon>" sigue presente para factores UNAVAILABLE',
          "Reason:" in sq_factor_src and "unavailable_reasons" in sq_factor_src)
    check('el chequeo es sobre status (AVAILABLE/UNAVAILABLE), no sobre el VALOR -- '
          "asi NEUTRAL (un valor de Alignment) nunca se confunde con UNAVAILABLE (un status)",
          'fo.status !== "AVAILABLE"' in sq_factor_src)

    print("\n=== E. Sin rastro de un score agregado 0-100 en ningun lado del panel ===")
    check("app.js no contiene un placeholder de score 0-100 (ej. '/100', 'XX/100')",
          "/100" not in js)
    check("index.html no contiene un placeholder de score 0-100",
          "/100" not in html)

    print("\n=== F. Columna de la tabla ya no se llama 'Calificacion' (calificacion legacy) ===")
    check('columna renombrada a "Signal Quality" en la tabla de cerradas',
          "<th>Signal Quality</th>" in html)
    check('"Calificación" (columna legacy) ya no aparece en index.html',
          "Calificación" not in html)

    print("\n=== G. Tarjeta 'Signal Quality -- Acumulacion OOS' es full width ===")
    m = re.search(r'<div class="card ([^"]*)">\s*<div class="label">Signal Quality — Acumulaci', html)
    check("la tarjeta OOS existe y se pudo localizar su clase de grid", m is not None)
    if m:
        classes = m.group(1).split()
        check('usa la clase "full" (antes "wide3", dejaba 1/4 del ancho vacio en desktop)',
              "full" in classes, f"classes={classes}")
        check('ya NO usa "wide3"', "wide3" not in classes, f"classes={classes}")

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
