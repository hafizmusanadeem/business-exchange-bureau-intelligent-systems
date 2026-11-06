"""Load synthetic data:  cd backend && python -m app.bxb.seed   (after `alembic upgrade head`)"""
from sqlmodel import Session
from app.core.db import engine
from app.bxb.models import EventKind, InvestorEvent, InvestorProfile, Listing, ListingStatus
from app.bxb.synthetic import generate

def main() -> None:
    d = generate()
    with Session(engine) as s:
        s.add_all(Listing(**{**l, "status": ListingStatus(l["status"])}) for l in d["listings"])
        s.add_all(InvestorProfile(**i) for i in d["investors"])
        s.commit()  # parents first so foreign keys resolve
        s.add_all(InvestorEvent(**{**e, "kind": EventKind(e["kind"])}) for e in d["events"])
        s.commit()
    print({k: len(v) for k, v in d.items()}, "- all synthetic")

if __name__ == "__main__":
    main()
