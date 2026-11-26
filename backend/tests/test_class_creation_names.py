"""Classes added by a principal are named like every other class ("Class 8-C") and cannot be added twice,
whichever way the name is typed."""
import pytest
from sqlalchemy import text

URL = "/api/v1/classes"


@pytest.mark.asyncio
async def test_new_classes_use_the_standard_name_and_duplicates_are_refused(client, db_session, principal_token):
    headers = {"Authorization": f"Bearer {principal_token}"}
    try:
        res = await client.post(URL, json={"school_id": "school-1", "name": "11q"}, headers=headers)
        assert res.status_code == 201, res.text
        assert res.json()["name"] == "Class 11-Q" and res.json()["grade"] == 11
        for again in ("11Q", "Class 11-Q", " 11q "):
            dup = await client.post(URL, json={"school_id": "school-1", "name": again}, headers=headers)
            assert dup.status_code == 409, (again, dup.text)

        named = await client.post(URL, json={"school_id": "school-1", "name": "11 Rose"}, headers=headers)
        assert named.status_code == 201 and named.json()["name"] == "Class 11-Rose"
        assert (await client.post(URL, json={"school_id": "school-1", "name": "11 rose"}, headers=headers)).status_code == 409

        for bad in ("", "99Q", "Q11"):
            assert (await client.post(URL, json={"school_id": "school-1", "name": bad}, headers=headers)).status_code in (400, 422)
    finally:
        await db_session.execute(text("DELETE FROM classes WHERE school_id = 'school-1' AND grade = 11"))
        await db_session.commit()
