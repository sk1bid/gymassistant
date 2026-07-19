"""Каталог упражнений: группы мышц, пресеты и личные упражнения пользователя."""
from fastapi import APIRouter

from database.orm_query import (
    orm_add_user_exercise,
    orm_delete_user_exercise,
    orm_get_admin_exercises_in_category,
    orm_get_categories,
    orm_get_user_exercises,
    orm_get_user_exercises_in_category,
    orm_update_user_exercise,
)
from miniapp.db import Session
from miniapp.deps import CurrentUser
from miniapp.ownership import own_user_exercise
from miniapp.schemas import UserExerciseIn

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/catalog")
async def categories(user: CurrentUser, session: Session):
    """Группы мышц со счётчиком (пресеты + личные упражнения этого пользователя)."""
    rows = await orm_get_categories(session, user.user_id)
    return {
        "ok": True,
        "categories": [{"id": c.id, "name": c.name, "count": count} for c, count in rows],
    }


@router.get("/catalog/{category_id}")
async def category(category_id: int, user: CurrentUser, session: Session):
    presets = await orm_get_admin_exercises_in_category(session, category_id)
    mine = await orm_get_user_exercises_in_category(session, category_id, user.user_id)

    return {
        "ok": True,
        "exercises": (
            [{"id": e.id, "name": e.name, "description": e.description, "kind": "admin"} for e in presets]
            + [{"id": e.id, "name": e.name, "description": e.description, "kind": "user"} for e in mine]
        ),
    }


@router.get("/user-exercises")
async def list_user_exercises(user: CurrentUser, session: Session):
    items = await orm_get_user_exercises(session, user.user_id)
    return {
        "ok": True,
        "exercises": [
            {"id": e.id, "name": e.name, "description": e.description, "category_id": e.category_id}
            for e in items
        ],
    }


@router.post("/user-exercises")
async def create_user_exercise(body: UserExerciseIn, user: CurrentUser, session: Session):
    await orm_add_user_exercise(session, {
        "name": body.name.strip(),
        "description": body.description.strip(),
        "user_id": user.user_id,
        "category_id": body.category_id,
    })
    return {"ok": True}


@router.patch("/user-exercises/{user_exercise_id}")
async def update_user_exercise(
    user_exercise_id: int, body: UserExerciseIn, user: CurrentUser, session: Session,
):
    await own_user_exercise(session, user.user_id, user_exercise_id)
    # orm_update_user_exercise ждёт ключ "category", а не "category_id" — так исторически.
    await orm_update_user_exercise(session, user_exercise_id, {
        "name": body.name.strip(),
        "description": body.description.strip(),
        "category": body.category_id,
    })
    return {"ok": True}


@router.delete("/user-exercises/{user_exercise_id}")
async def delete_user_exercise(user_exercise_id: int, user: CurrentUser, session: Session):
    await own_user_exercise(session, user.user_id, user_exercise_id)
    await orm_delete_user_exercise(session, user_exercise_id)
    return {"ok": True}
