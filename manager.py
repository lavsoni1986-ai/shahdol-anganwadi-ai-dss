import asyncio
from app.database import AsyncSessionLocal, init_db, _sync_schema_columns, engine
from app.models import AnganwadiMaster
from sqlalchemy import select, text
import json

async def main():
    # Force schema update
    async with engine.begin() as conn:
        await conn.run_sync(_sync_schema_columns)
        
    async with AsyncSessionLocal() as session:
        # Check Bhagwati Baiga
        q = select(AnganwadiMaster).where(AnganwadiMaster.worker_mobile == "6263302625")
        res = await session.execute(q)
        worker1 = res.scalars().first()
        worker1_exists = worker1 is not None

        if not worker1_exists:
            worker1 = AnganwadiMaster(
                worker_name="Bhagwati Baiga",
                worker_mobile="6263302625",
                awc_code="23460060604",
                center_name="Pongri 1",
                district="Shahdol",
                block_name="Sohagpur",
                sector="Jamui",
                active_status=True
            )
            session.add(worker1)

        # Check Savitri Singh
        q = select(AnganwadiMaster).where(AnganwadiMaster.worker_mobile == "6261756298")
        res = await session.execute(q)
        worker2 = res.scalars().first()
        worker2_exists = worker2 is not None

        if not worker2_exists:
            worker2 = AnganwadiMaster(
                worker_name="Savitri Singh",
                worker_mobile="6261756298",
                awc_code="23460060602",
                center_name="Chapa 1",
                district="Shahdol",
                block_name="Sohagpur",
                sector="Jamui",
                active_status=True
            )
            session.add(worker2)

        # Check Demo Worker
        q = select(AnganwadiMaster).where(AnganwadiMaster.worker_mobile == "9753239303")
        res = await session.execute(q)
        demo_worker = res.scalars().first()
        demo_worker_exists = demo_worker is not None

        if not demo_worker_exists:
            demo_worker = AnganwadiMaster(
                worker_name="Lav Soni (Demo)",
                worker_mobile="9753239303",
                awc_code="DEMO001",
                center_name="Demo Anganwadi",
                district="Shahdol",
                block_name="Sohagpur",
                sector="Jamui",
                active_status=True,
                worker_type="DEMO",
                is_demo=True
            )
            session.add(demo_worker)

        await session.commit()
        
        print(json.dumps({
            "worker1_existed": worker1_exists,
            "worker2_existed": worker2_exists,
            "demo_created": not demo_worker_exists
        }))

if __name__ == "__main__":
    asyncio.run(main())
