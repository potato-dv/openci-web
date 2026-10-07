from app.database import Base, engine
from app.models.investigation import Investigation

    
Base.metadata.create_all(bind=engine)

print("Database tables created.")