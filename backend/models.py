from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


class Region(SQLModel, table=True):
    region_id: str = Field(primary_key=True)
    region_name: str
    description: Optional[str] = None

    parks: List["Park"] = Relationship(back_populates="region")


class Park(SQLModel, table=True):
    park_code: str = Field(primary_key=True)
    park_name: str
    state: str
    designation: str
    region_id: Optional[str] = Field(default=None, foreign_key="region.region_id")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    website: Optional[str] = None
    boundary: Optional[str] = None

    region: Optional[Region] = Relationship(back_populates="parks")
    monthly_visits: List["MonthlyVisit"] = Relationship(back_populates="park")


class MonthlyVisit(SQLModel, table=True):

    __tablename__ = "monthly_visit"
    
    park_code: str = Field(foreign_key="park.park_code", primary_key=True)
    year: int = Field(primary_key=True)
    month: int = Field(primary_key=True)

    recreation_visits: Optional[int] = None
    non_recreation_visits: Optional[int] = None
    total_visits: Optional[int] = None
    concessioner_lodging: Optional[int] = None
    concessioner_camping: Optional[int] = None
    tent_campers: Optional[int] = None
    rv_campers: Optional[int] = None
    backcountry: Optional[int] = None
    nonrecreation_overnight_stays: Optional[int] = None
    miscellaneous_overnight_stays: Optional[int] = None

    park: Optional[Park] = Relationship(back_populates="monthly_visits")
