from app.database import Base, engine
from app.models.investigation import Investigation
from app.models.assignment import InvestigationAssignment
from app.models.user import User
from app.models.report import InvestigationReport
from app.models.review import InvestigationReview
    
Base.metadata.create_all(bind=engine)

print("Database tables created.")