# PixelPet Phase 1 Implementation Plan

> Execute inline with executing-plans, as authorized by the user's “开始实现”.

**Goal:** Deliver a locally runnable, hardware-free PixelPet simulator.

**Architecture:** FastAPI serves same-origin static assets and typed simulation APIs. SQLAlchemy initializes five SQLite tables in output; an in-memory simulator manages a single local pet independently of persistence.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2, Pydantic Settings, vanilla Canvas/JS, Pytest.

## 1. Environment and contracts
- [x] Create a Python 3.10 virtual environment on D and install dependencies.
- [x] Write tests in tests/test_app.py for health, five-table initialization, persistence across restarts, unavailable database, static homepage, all seven events, eight preview states, invalid events and app isolation.
- [x] Run `.venv\Scripts\python -m pytest -q`; observe missing application failure before implementation.

## 2. Backend
- [x] Create backend/core/config.py (root-relative settings), database/models.py and engine.py (schema and foreign keys), character/state.py (typed states), hardware/simulator.py (adapter boundary), api/routes.py (validated endpoints), main.py (lifespan/static mounting).
- [x] Implement GET /api/health, GET /api/pet/state, POST /api/simulator/events and POST /api/simulator/preview. Unsupported events/states return 422; health database failure returns 503 without exposing exception details.
- [x] Run the backend suite and resolve failures before proceeding.

## 3. Simulator frontend
- [x] Create frontend/index.html, css/style.css, js/pet.js and js/app.js. Draw the original star character on a low-resolution canvas scaled to 240px without interpolation; animate all eight states using requestAnimationFrame.
- [x] Connect event and preview buttons to API, display error/status text, serialize writes, keep offline animation working, add accessible text and reduced motion support.
- [x] Implement explicitly labelled local demo chat using textContent, with clear, length limit, and no microphone/network AI calls.
- [x] Verify actual page, all states, event buttons, clear chat and mobile layout using browser automation; save evidence in output/playwright.

## 4. Delivery
- [x] Add exact installed dependency versions to requirements.txt, .env.example, .gitignore, pytest.ini, scripts/start.ps1 and scripts/test.ps1.
- [x] Write Chinese README with setup, launch, test commands, stage limitations, file map and future adapter boundaries.
- [x] Run complete tests, Python compile and JavaScript syntax checks, start real Uvicorn and verify health.
- [x] Record actual verification output and deliver launch instructions with a preview image.

