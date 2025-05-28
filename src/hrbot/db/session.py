# hrbot/db/session.py
import ssl
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from hrbot.config.settings import settings

def _asyncpg_ssl_arg():
    """
    Convert Postgres‐style sslmode to the `ssl` argument asyncpg expects.
    """
    mode = settings.db.sslmode.lower()

    if mode == "disable":
        return False                               # force plain TCP
    if mode in {"allow", "prefer"}:
        return None                               # let server decide / opportunistic
    if mode in {"require", "verify-ca", "verify-full"}:
        ctx = ssl.create_default_context()
        if mode == "verify-full":
            ctx.check_hostname = True
        return ctx

    raise ValueError(f"Unsupported sslmode '{settings.db.sslmode}'")

connect_args = {"ssl": _asyncpg_ssl_arg()}

engine = create_async_engine(
    settings.db.url,              # already *without* ?sslmode=… in the URL
    pool_pre_ping=True,
    echo=False,
    connect_args=connect_args,
    **settings.db.engine_kwargs,
)

AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

