from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from pydantic import field_validator

class RegisterIn(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    email:EmailStr
    password:str=Field(min_length=12,max_length=128)
    company:Optional[str]=""

class LoginIn(BaseModel):
    email:EmailStr
    password:str

class LeadIn(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    email:EmailStr
    company:Optional[str]=Field(default="",max_length=180)
    service:Optional[str]=Field(default="",max_length=120)
    budget:Optional[str]=Field(default="",max_length=80)
    message:str=Field(min_length=10,max_length=10000)

class TicketIn(BaseModel):
    subject:str=Field(min_length=2,max_length=200)
    message:str=Field(min_length=5,max_length=10000)

PROJECT_STATUSES=r"^(Planning|In progress|Review|Completed|On hold)$"

class ProjectIn(BaseModel):
    client_id:int
    title:str=Field(min_length=2,max_length=180)
    description:Optional[str]=Field(default="",max_length=10000)
    status:Optional[str]=Field(default="Planning",pattern=PROJECT_STATUSES)
    progress:int=Field(default=0,ge=0,le=100)
    due_date:Optional[str]=Field(default="",max_length=40)

class ProjectUpdate(BaseModel):
    title:Optional[str]=Field(default=None,min_length=2,max_length=180)
    description:Optional[str]=Field(default=None,max_length=10000)
    status:Optional[str]=Field(default=None,pattern=PROJECT_STATUSES)
    progress:Optional[int]=Field(default=None,ge=0,le=100)
    due_date:Optional[str]=Field(default=None,max_length=40)

class InvoiceIn(BaseModel):
    client_id:int
    number:str=Field(min_length=1,max_length=50)
    description:Optional[str]=Field(default="",max_length=255)
    amount:float=Field(gt=0,allow_inf_nan=False)
    currency:str=Field(default="KES",pattern=r"^(KES|USD|EUR|GBP)$")
    due_date:Optional[str]=Field(default="",max_length=40)

class ProductIn(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    slug:str=Field(min_length=2,max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category:str=Field(default="Software",max_length=100)
    description:str=Field(default="",max_length=10000)
    features:str=Field(default="",max_length=5000)
    price_label:str=Field(default="Request a quote",max_length=100)
    url:str=Field(default="",max_length=500)
    tagline:str=Field(default="",max_length=240)
    platforms:str=Field(default="",max_length=500)
    version:str=Field(default="",max_length=80)
    github_url:str=Field(default="",max_length=500)
    docs_url:str=Field(default="",max_length=500)
    demo_url:str=Field(default="",max_length=500)
    image_url:str=Field(default="",max_length=1000)
    is_featured:bool=False
    sort_order:int=0
    status:str=Field(default="draft", pattern=r"^(draft|published|archived)$")

class ProductUpdate(BaseModel):
    name:Optional[str]=Field(default=None,min_length=2,max_length=160)
    slug:Optional[str]=Field(default=None,min_length=2,max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category:Optional[str]=Field(default=None,max_length=100)
    description:Optional[str]=Field(default=None,max_length=10000)
    features:Optional[str]=Field(default=None,max_length=5000)
    price_label:Optional[str]=Field(default=None,max_length=100)
    url:Optional[str]=Field(default=None,max_length=500)
    tagline:Optional[str]=Field(default=None,max_length=240)
    platforms:Optional[str]=Field(default=None,max_length=500)
    version:Optional[str]=Field(default=None,max_length=80)
    github_url:Optional[str]=Field(default=None,max_length=500)
    docs_url:Optional[str]=Field(default=None,max_length=500)
    demo_url:Optional[str]=Field(default=None,max_length=500)
    image_url:Optional[str]=Field(default=None,max_length=1000)
    is_featured:Optional[bool]=None
    sort_order:Optional[int]=None
    status:Optional[str]=Field(default=None, pattern=r"^(draft|published|archived)$")

class ArticleIn(BaseModel):
    title:str=Field(min_length=2,max_length=200)
    slug:str=Field(min_length=2,max_length=200,pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category:str=Field(default="Insights",max_length=100)
    excerpt:str=Field(default="",max_length=2000)
    body:str=Field(default="",max_length=50000)
    published:bool=True

class ArticleUpdate(BaseModel):
    title:Optional[str]=Field(default=None,min_length=2,max_length=200)
    slug:Optional[str]=Field(default=None,min_length=2,max_length=200,pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category:Optional[str]=Field(default=None,max_length=100)
    excerpt:Optional[str]=Field(default=None,max_length=2000)
    body:Optional[str]=Field(default=None,max_length=50000)
    published:Optional[bool]=None

class CareerApplicationIn(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    email:EmailStr
    role:str=Field(min_length=2,max_length=160)
    portfolio:str=Field(default="",max_length=500)
    message:str=Field(default="",max_length=5000)

class TicketUpdate(BaseModel):
    response:Optional[str]=Field(default=None,max_length=10000)
    status:Optional[str]=Field(default=None,pattern=r"^(open|in_progress|resolved)$")


class QuoteIn(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    email:EmailStr
    company:Optional[str]=Field(default="",max_length=180)
    service:Optional[str]=Field(default="",max_length=160)
    product_slug:Optional[str]=Field(default="",max_length=160)
    budget:Optional[str]=Field(default="",max_length=80)
    timeline:Optional[str]=Field(default="",max_length=80)
    details:str=Field(default="",max_length=10000)

class QuoteUpdate(BaseModel):
    status:Optional[str]=Field(default=None,pattern=r"^(new|reviewing|quoted|accepted|declined|closed)$")
    admin_notes:Optional[str]=Field(default=None,max_length=10000)


class AuroraChatMessage(BaseModel):
    role:str=Field(pattern=r"^(system|user|assistant)$")
    content:str=Field(min_length=1,max_length=12000)

class AuroraChatIn(BaseModel):
    messages:list[AuroraChatMessage]=Field(min_length=1,max_length=40)
    model:str=Field(default="aurora",max_length=120)
    max_tokens:int=Field(default=900,ge=1,le=4000)
    temperature:float=Field(default=0.7,ge=0,le=2)

class AuroraKnowledgeAskIn(BaseModel):
    question:str=Field(min_length=2,max_length=1000)

class AutomationWorkflowIn(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    trigger_event:str=Field(pattern=r"^(lead\.created|quote\.created|ticket\.created|partner\.created)$")
    enabled:bool=False


class PartnerApplicationIn(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    email:EmailStr
    organization:str=Field(default="",max_length=180)
    website:str=Field(default="",max_length=500)
    partnership_type:str=Field(default="",max_length=100)
    message:str=Field(default="",max_length=5000)

class LicenseIn(BaseModel):
    client_id:int
    product_id:Optional[int]=None
    seats:int=Field(default=1,ge=1,le=10000)
    expires_at:Optional[str]=None
    notes:str=Field(default="",max_length=5000)

class NotificationIn(BaseModel):
    user_id:int
    title:str=Field(min_length=2,max_length=180)
    body:str=Field(default="",max_length=5000)
    kind:str=Field(default="general",max_length=40)
