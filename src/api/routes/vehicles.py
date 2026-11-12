from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import SessionDep
from src.infrastructure.database.models import VehicleModel
from src.infrastructure.database.repositories import get_customer

router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


class VehicleCreate(BaseModel):
    customer_id: UUID
    license_plate: str = Field(pattern=r"^[A-Z0-9]{7}$")
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1900, le=2100)


class VehicleResponse(BaseModel):
    id: UUID
    customer_id: UUID
    license_plate: str


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle(data: VehicleCreate, session: SessionDep) -> VehicleResponse:
    try:
        with session.begin():
            if get_customer(session, data.customer_id) is None:
                raise HTTPException(status_code=404, detail="customer not found")
            vehicle = VehicleModel(
                id=str(uuid4()),
                customer_id=str(data.customer_id),
                license_plate=data.license_plate,
                make=data.make,
                model=data.model,
                year=data.year,
            )
            session.add(vehicle)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="vehicle already exists") from exc
    return VehicleResponse(
        id=UUID(vehicle.id),
        customer_id=UUID(vehicle.customer_id),
        license_plate=vehicle.license_plate,
    )
