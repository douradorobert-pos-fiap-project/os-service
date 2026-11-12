from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import SessionDep
from src.infrastructure.database.models import CustomerModel

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    document: str = Field(pattern=r"^\d{11,14}$")


class CustomerResponse(BaseModel):
    id: UUID
    name: str


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(data: CustomerCreate, session: SessionDep) -> CustomerResponse:
    customer = CustomerModel(id=str(uuid4()), name=data.name, document=data.document)
    try:
        with session.begin():
            session.add(customer)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="customer already exists") from exc
    return CustomerResponse(id=UUID(customer.id), name=customer.name)
