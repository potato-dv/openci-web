from sqlalchemy import Boolean, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255))

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    password: Mapped[str] = mapped_column(String(255))

    role: Mapped[str] = mapped_column(
        String(50),
        default="agent",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )