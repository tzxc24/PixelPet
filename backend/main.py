"""App factory with isolated simulator state and managed database lifecycle."""
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.responses import FileResponse
from backend.release import VERSION
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.api.chat import router as chat_router
from backend.api.assets import router as assets_router
from backend.api.audio import router as audio_router
from backend.api.devices import router as devices_router
from backend.api.preferences import router as preferences_router
from backend.api.diagnostics import router as diagnostics_router
from backend.ai.provider import make_provider
from backend.chat.service import ChatService
from backend.core.config import ROOT, Settings
from backend.database.engine import initialize_database
from backend.database.store import Store
from backend.hardware.simulator import HardwareSimulator
from backend.speech.service import SpeechService
from backend.preferences import PreferencesService,ReminderScheduler
from backend.events import EventBus
from backend.pet import PetEngine
from backend.devices import DeviceService
from backend.access import LocalAccessMiddleware, parse_allowed_hosts


def create_app(database_path: Path | None = None, settings: Settings | None = None, provider=None) -> FastAPI:
    settings = settings or Settings()
    allowed_hosts = parse_allowed_hosts(settings.allowed_hosts)
    path = database_path if database_path is not None else settings.resolved_database_path()
    uploads=ROOT/'tmp'/'uploads'
    uploads.mkdir(parents=True,exist_ok=True)
    tempfile.tempdir=str(uploads)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.engine = initialize_database(path)
        application.state.hardware = HardwareSimulator()
        application.state.access_token = settings.access_token.get_secret_value()
        application.state.allowed_hosts = allowed_hosts
        try:
            application.state.store = Store(application.state.engine,settings.memory_decay_days)
            application.state.preferences=PreferencesService(application.state.engine)
            application.state.scheduler=ReminderScheduler(application.state.preferences)
            application.state.event_bus=EventBus()
            application.state.pet_engine=PetEngine(application.state.event_bus)
            application.state.pet_engine.preferences=application.state.preferences
            application.state.pet_engine.configure(application.state.preferences.get().model_dump())
            application.state.devices=DeviceService(application.state.event_bus,application.state.pet_engine)
            application.state.speech=SpeechService(settings)
            application.state.speech.preferences=application.state.preferences
            application.state.provider = provider if provider is not None else make_provider(settings)
            saved=application.state.preferences.read_json('preferences.v1', {})
            if 'llm_model' in saved and hasattr(application.state.provider,'model'):
                application.state.provider.model=application.state.preferences.get().llm_model
            application.state.chat = ChatService(application.state.store, application.state.provider, settings)
            application.state.chat.preferences=application.state.preferences
            application.state.chat.pet_engine=application.state.pet_engine
            yield
        finally:
            if hasattr(application.state, "provider"):
                await application.state.provider.close()
            application.state.engine.dispose()

    application = FastAPI(title="PixelPet · 小星", version=VERSION, lifespan=lifespan)
    application.add_middleware(LocalAccessMiddleware,token=settings.access_token.get_secret_value(),allowed_hosts=allowed_hosts)
    application.include_router(router)
    application.include_router(preferences_router)
    application.include_router(chat_router)
    application.include_router(assets_router)
    application.include_router(audio_router)
    application.include_router(devices_router)
    application.include_router(diagnostics_router)
    application.mount("/static", StaticFiles(directory=ROOT / "frontend", check_dir=False), name="static")

    @application.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "frontend" / "index.html")

    @application.get('/voice-test',include_in_schema=False)
    def voice_test():
        return FileResponse(ROOT/'frontend'/'voice-test.html')

    @application.get('/device-debug', include_in_schema=False)
    def device_debug():
        return FileResponse(ROOT / 'frontend' / 'device-debug.html')

    return application


app = create_app()
