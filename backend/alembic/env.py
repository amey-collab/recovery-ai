from pathlib import Path
import sys
from alembic import context

# Make `alembic` executable from the repository root or backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import Base,settings
config=context.config
# ConfigParser treats `%` as interpolation syntax; URLs may contain encoded
# credentials such as `%40`. Escape only for Alembic's in-memory config.
config.set_main_option('sqlalchemy.url', settings.database_url.replace('%', '%%'))
target_metadata=Base.metadata
def run_migrations_offline():
 context.configure(url=settings.database_url,target_metadata=target_metadata,literal_binds=True); 
 with context.begin_transaction(): context.run_migrations()
def run_migrations_online():
 from sqlalchemy import create_engine
 connectable=create_engine(settings.database_url)
 with connectable.connect() as connection:
  context.configure(connection=connection,target_metadata=target_metadata)
  with context.begin_transaction(): context.run_migrations()
if context.is_offline_mode():run_migrations_offline()
else:run_migrations_online()
