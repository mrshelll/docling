from lote import Cambio, parsear_log, relevantes, workflows_nuevos
from registro import Arreglo

LOG = (
    "\x1eaaa\x1ffeat(pdf, reading-order): updating the reading-order algorithm (#4276)\n\n"
    "docling/utils/layout_postprocessor.py\ndocs/x.md\n"
    "\x1ebbb\x1ffix(vlm): report failed remote API calls as INFERENCE_ERROR (#4332)\n\n"
    "docling/pipeline/vlm_pipeline.py\n"
    "\x1eccc\x1ffix(docx): preserve duplicate paragraphs (#4606)\n\n"
    "docling/backend/msword_backend.py\n"
    "\x1eddd\x1ffix(pdf): keep failed-page sizes on the conversion (#4486)\n\n"
    "docling/pipeline/base_pipeline.py\n"
    "\x1eeee\x1fchore: bump pdf tooling\n\ndocling/x.py\n"
)

ARREGLOS = [
    Arreglo("bug2", "Bug 2", True, ("docling/utils/layout_postprocessor.py",), "t.py"),
    Arreglo("bug45", "Bugs 4 y 5", True, ("docling/pipeline/vlm_pipeline.py",), "t.py"),
]


def test_parsea_commits_con_archivos():
    cambios = parsear_log(LOG)
    assert [c.sha for c in cambios] == ["aaa", "bbb", "ccc", "ddd", "eee"]
    assert cambios[0].archivos == ("docling/utils/layout_postprocessor.py", "docs/x.md")
    assert cambios[0].pr == 4276
    assert cambios[4].pr is None


def test_agrupa_por_arreglo_y_por_area():
    r = relevantes(parsear_log(LOG), ARREGLOS)
    assert [c.sha for c in r["bug2"]] == ["aaa"]
    assert [c.sha for c in r["bug45"]] == ["bbb"]
    # ddd menciona pdf y es un fix; eee menciona pdf pero es chore; ccc no menciona áreas
    assert [c.sha for c in r["_areas"]] == ["ddd"]


def test_workflows_nuevos_ignora_los_propios():
    nombres = ".github/workflows/nuevo.yml\n.github/workflows/dotech-vigia.yml\n\n"
    assert workflows_nuevos(nombres) == [".github/workflows/nuevo.yml"]


def test_log_vacio():
    assert parsear_log("") == []
