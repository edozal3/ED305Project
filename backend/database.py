from sqlmodel import create_engine, Session
from pathlib import Path

# Get the project root directory (parent of backend/)
PROJECT_ROOT = Path(__file__).parent.parent
DATABASE_URL = f"sqlite:///{PROJECT_ROOT}/database/nps.db"

# Create the engine once at module import
engine = create_engine(DATABASE_URL, echo=False)


def get_session():
    """Provide a new SQLModel Session for dependency injection."""
    with Session(engine) as session:
        yield session
