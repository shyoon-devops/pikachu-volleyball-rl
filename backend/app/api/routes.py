"""REST API endpoints — see docs/PLAN.md section 3.1."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/training/status")
async def training_status(request: Request):
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        return {"state": "stopped", "current_step": 0, "current_episode": 0}
    return training_service.status()


@router.get("/games")
async def list_games(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    game_service = request.app.state.game_service
    return await game_service.get_games(page=page, limit=limit)


@router.get("/games/{game_id}")
async def get_game(request: Request, game_id: str):
    game_service = request.app.state.game_service
    doc = await game_service.get_game(game_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return doc


@router.get("/replays/{game_id}")
async def get_replay(game_id: str):
    replay_service = None  # Wave 3: injected via app.state
    if replay_service is None:
        raise HTTPException(status_code=501, detail="Replay service not available yet")
    return await replay_service.load_replay(game_id)


@router.get("/models")
async def list_models():
    model_dir = Path(os.getenv("MODEL_DIR", "./models"))
    if not model_dir.exists():
        return {"models": []}
    files = sorted(model_dir.rglob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "models": [
            {"path": str(f.relative_to(model_dir)), "size_bytes": f.stat().st_size}
            for f in files
        ]
    }


@router.post("/evaluation/run")
async def run_evaluation(request: Request):
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        raise HTTPException(status_code=501, detail="Evaluation service not available yet")
    body = await request.json()
    result = await eval_service.run(
        model_path=body["model_path"],
        bot_level=body.get("bot_level", 1),
        n_games=body.get("n_games", 50),
    )
    return result


@router.get("/evaluation/results")
async def get_evaluation_results(request: Request):
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        return {"data": []}
    return await eval_service.get_results()
