# EIR backend implementation status

The FastAPI foundation implements the public `GET /api/v1/health` operation. Run
it with `uvicorn eir.main:app`; `EIR_DATABASE_PATH` selects the SQLite file
(default: `eir.sqlite3`). Startup applies ordered transactional SQLite schema
migrations and fails if the database cannot be opened or has a newer schema.
The connection is closed at shutdown. Focused tests cover health, configuration,
database lifecycle, migration rollback and startup failures.

The remaining contract operations are not implemented. The initial migration
only establishes foundation metadata; it does not create user or clinical data
tables. Do not infer implementation of other features from the contract.
