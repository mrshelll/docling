from workflows_heredados import a_desactivar


def test_solo_los_activos_que_no_son_propios():
    workflows = [
        {"id": 1, "path": ".github/workflows/ci.yml", "state": "active"},
        {"id": 2, "path": ".github/workflows/dotech-vigia.yml", "state": "active"},
        {"id": 3, "path": ".github/workflows/pypi.yml", "state": "disabled_manually"},
        {"id": 4, "path": "dynamic/pages/pages-build-deployment", "state": "active"},
        {"id": 5, "path": ".github/workflows/nuevo-de-ibm.yml", "state": "active"},
    ]
    assert [w["id"] for w in a_desactivar(workflows)] == [1, 5]
