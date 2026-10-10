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
    "\x1efff\x1frefactor(pdf): split the page backend (#4700)\n\ndocling/backend/pdf.py\n"
)

ARREGLOS = [
    Arreglo("bug2", "Bug 2", True, ("docling/utils/layout_postprocessor.py",), "t.py"),
    Arreglo("bug45", "Bugs 4 y 5", True, ("docling/pipeline/vlm_pipeline.py",), "t.py"),
]


def test_parsea_commits_con_archivos():
    cambios = parsear_log(LOG)
    assert [c.sha for c in cambios] == ["aaa", "bbb", "ccc", "ddd", "eee", "fff"]
    assert cambios[0].archivos == ("docling/utils/layout_postprocessor.py", "docs/x.md")
    assert cambios[0].pr == 4276
    assert cambios[4].pr is None


def test_agrupa_por_arreglo_y_por_area():
    r = relevantes(parsear_log(LOG), ARREGLOS)
    assert [c.sha for c in r["bug2"]] == ["aaa"]
    assert [c.sha for c in r["bug45"]] == ["bbb"]
    # ddd (fix) y fff (refactor) mencionan pdf; eee menciona pdf pero es chore; ccc no menciona áreas
    assert [c.sha for c in r["_areas"]] == ["ddd", "fff"]


def test_workflows_nuevos_ignora_los_propios():
    nombres = ".github/workflows/nuevo.yml\n.github/workflows/dotech-vigia.yml\n\n"
    assert workflows_nuevos(nombres) == [".github/workflows/nuevo.yml"]


def test_log_vacio():
    assert parsear_log("") == []


def test_movimientos_y_renombres_no_se_pierden(tmp_path, monkeypatch):
    import json
    import subprocess

    from lote import main

    def git(*a):
        subprocess.run(["git", *a], check=True, capture_output=True, cwd=tmp_path)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "docling/utils").mkdir(parents=True)
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "docling/utils/layout_postprocessor.py").write_text("x = 1\n" * 20)
    (tmp_path / ".github/workflows/viejo.yml").write_text("name: viejo\n" * 20)
    git("add", ".")
    git("commit", "-qm", "base")
    git("tag", "v1")
    git("mv", "docling/utils/layout_postprocessor.py", "docling/utils/otro.py")
    git("commit", "-qm", "refactor: move layout postprocessor")
    git("mv", ".github/workflows/viejo.yml", ".github/workflows/nuevo.yml")
    git("commit", "-qm", "ci: rename workflow")
    (tmp_path / "t.toml").write_text(
        '[[arreglo]]\nclave = "bug2"\nnombre = "Bug 2"\nen_main = true\n'
        'archivos = ["docling/utils/layout_postprocessor.py"]\n'
        'test_comportamiento = "t.py"\n'
    )
    monkeypatch.chdir(tmp_path)
    assert main(["--registro", "t.toml", "--desde", "v1", "--hasta", "HEAD", "--salida", "o.json"]) == 0
    datos = json.loads((tmp_path / "o.json").read_text())
    assert [c["titulo"] for c in datos["por_arreglo"]["bug2"]] == ["refactor: move layout postprocessor"]
    assert datos["workflows_nuevos"] == [".github/workflows/nuevo.yml"]
