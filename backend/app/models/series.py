class Series(Base):
    __tablename__ = "series"

    id
    publisher_id

    title
    slug

    description

    status

    cover_url

volumes: Mapped[list["Volume"]] = relationship(
    back_populates="series",
    cascade="all, delete-orphan",
)
    