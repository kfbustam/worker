import json
import pytest
from pathlib import Path

from database.tests.factories import OwnerFactory
from tasks.add_to_sendgrid_list import AddToSendgridListTask

here = Path(__file__)


class TestAddToSendgridListTask(object):
    @pytest.mark.asyncio
    async def test_new_oauthed_users_email(
        self,
        mocker,
        mock_configuration,
        dbsession,
        codecov_vcr,
        mock_storage,
        mock_redis,
    ):
        owner = OwnerFactory.create(ownerid=1, email="tom@codecov.io")
        dbsession.add(owner)
        result = await AddToSendgridListTask().run_async(
            db_session=dbsession, ownerid=owner.ownerid, list_type="new-oauthed-users"
        )
        print(result.__dict__)
        assert result["job_id"] == "9791f6a7-3d3b-4ae9-8f71-67bd98f33008"

    @pytest.mark.asyncio
    async def test_end_of_trial_email(
        self,
        mocker,
        mock_configuration,
        dbsession,
        codecov_vcr,
        mock_storage,
        mock_redis,
    ):
        owner = OwnerFactory.create(ownerid=1, email="felipe@codecov.io")
        dbsession.add(owner)
        result = await AddToSendgridListTask().run_async(
            db_session=dbsession, ownerid=owner.ownerid, list_type="end-of-trial"
        )
        assert result["job_id"] == "9791f6a7-3d3b-4ae9-8f71-67bd98f33008"

    @pytest.mark.asyncio
    async def test_send_email_no_owner(
        self, mocker, mock_configuration, dbsession, codecov_vcr
    ):
        result = await AddToSendgridListTask().run_async(
            db_session=dbsession, ownerid=45, list_type="end-of-trial"
        )
        assert result is None
