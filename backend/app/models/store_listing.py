class Volume(Base):
    ...

    series: Mapped["Series"] = relationship(
        back_populates="volumes"
    )

    store_listings: Mapped[list["StoreListing"]] = relationship(
        back_populates="volume",
        cascade="all, delete-orphan",
    )