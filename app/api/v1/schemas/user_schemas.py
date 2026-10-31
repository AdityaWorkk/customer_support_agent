from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class GoogleIn(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=300)


class PasswordIn(BaseModel):
    current_password: str | None = Field(default=None, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class GoogleTokenIn(BaseModel):
    access_token: str = Field(min_length=20, max_length=4096)
