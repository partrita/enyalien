from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.database import init_db
from app.routes import router, RedirectException, redirect_exception_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions: Create database tables if they do not exist
    init_db()
    yield
    # Shutdown actions (if any)


app = FastAPI(
    title="Enyalien SRS",
    description="Anki-style Spaced Repetition Flashcard App",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_exception_handler(RedirectException, redirect_exception_handler)

# Mount static files (javascript swipe controllers and stylesheets)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include all the page/fragment routes
app.include_router(router)

# Favicon handler to silence 404 logs in browsers


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(
        url="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🧠</text></svg>"
    )
