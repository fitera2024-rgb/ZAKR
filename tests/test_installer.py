import zipfile

from scripts.build_installer import build


def test_installer_is_deterministic_and_contains_no_accounting_data():
    archive, first_hash = build()
    _, second_hash = build()
    assert first_hash == second_hash
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert "HAT/Установить HAT.cmd" in names
        assert "HAT/Запустить HAT.cmd" in names
        assert "HAT/install.sh" in names
        assert "HAT/start.sh" in names
        assert "HAT/app/src/hierarchy_account_transfer/web/index.html" in names
        assert not any("local_inputs" in name or "/runs/" in name for name in names)
        assert not any(name.endswith((".xlsx", ".xls", ".csv")) for name in names)
