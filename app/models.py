from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ValueSet(Base):
    __tablename__ = "valueset"

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500))
    resource_type: Mapped[str] = mapped_column(String(20))  # ValueSet / CodeSystem
    code_system: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)

    codes: Mapped[list["Code"]] = relationship(
        back_populates="valueset", cascade="all, delete-orphan", lazy="selectin"
    )


class Code(Base):
    __tablename__ = "code"

    id: Mapped[int] = mapped_column(primary_key=True)
    valueset_id: Mapped[int] = mapped_column(ForeignKey("valueset.id"))
    code: Mapped[str] = mapped_column(String(100), index=True)
    display: Mapped[str | None] = mapped_column(String(500))

    valueset: Mapped["ValueSet"] = relationship(back_populates="codes")
