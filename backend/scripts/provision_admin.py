"""Explicit local bootstrap. Never seeds schools, sample data, or overwrites accounts.

Run from apps/lumeneios with production settings already exported:
python -m backend.scripts.provision_admin --email admin@example.com --name Administrator
"""
import argparse
import asyncio
import getpass
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.app.core.config import settings
from backend.app.core.security import get_password_hash
from backend.app.db.session import AsyncSessionLocal, init_db
from backend.app.models.entities import User
from backend.app.schemas.auth import UserCreate


async def provision_admin(db, email, name, password):
    if settings.DEMO_MODE:
        raise ValueError('Disable DEMO_MODE before provisioning a real administrator.')
    body=UserCreate(email=email,name=name,password=password,role='admin')
    if (await db.execute(select(User.id).where(User.email==body.email.lower()))).first():
        raise ValueError('Account already exists; provisioning never changes existing accounts.')
    user=User(email=body.email.lower(),name=body.name,role='admin',hashed_password=get_password_hash(body.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError('Account already exists; no account was overwritten.') from None
    return user


async def run(args, password):
    # Register all existing models before the existing non-destructive initialization.
    from backend.app.api.v1.router import api_router  # noqa: F401
    await init_db()
    async with AsyncSessionLocal() as db:
        await provision_admin(db,args.email,args.name,password)


def main():
    parser=argparse.ArgumentParser(description='Provision an initial administrator in the configured database.')
    parser.add_argument('--email',required=True);parser.add_argument('--name',required=True)
    args=parser.parse_args()
    if settings.DEMO_MODE:parser.error('DEMO_MODE must be false; no data has been written.')
    password=getpass.getpass('Initial administrator password: ')
    if password!=getpass.getpass('Confirm password: '):parser.error('Passwords do not match.')
    try:
        asyncio.run(run(args,password))
    except Exception:
        parser.error("Provisioning failed. Check configuration, password policy, address and existing-account status.")
    print('Administrator created. No sample records were seeded.')


if __name__=='__main__':main()
