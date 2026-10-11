from tessera import config


def test_project_root_contains_package() -> None:
    assert (config.PROJECT_ROOT / "src" / "tessera" / "config.py").is_file()


def test_data_and_output_dirs_exist() -> None:
    for path in (
        config.RAW_DIR,
        config.INTERIM_DIR,
        config.PROCESSED_DIR,
        config.FIGURES_DIR,
        config.TABLES_DIR,
        config.DOCS_DIR,
    ):
        assert path.is_dir(), path
