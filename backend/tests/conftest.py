from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from elite_logistics.database import Base
from elite_logistics.providers import SpanshDumpProvider


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as value:
        SpanshDumpProvider(value).import_file(Path(__file__).parent / "fixtures" / "tiny_spansh.json", "fixture")
        yield value

