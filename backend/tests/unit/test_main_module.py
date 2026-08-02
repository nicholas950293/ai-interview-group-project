from fastapi import FastAPI

from backend.src import main


def test_main_module_exposes_fastapi_app() -> None:
    assert isinstance(main.app, FastAPI)
