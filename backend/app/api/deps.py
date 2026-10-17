from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Path, Query, Request
from sqlalchemy.orm import Session

MAX_ID = 2_147_483_647  # INTEGER primary keys; larger ids would overflow the DB driver


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
IdPath = Annotated[int, Path(ge=1, le=MAX_ID)]
OptionalId = Annotated[int | None, Query(ge=1, le=MAX_ID)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]
