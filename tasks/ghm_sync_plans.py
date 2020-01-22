import logging
import requests
from datetime import datetime

from app import celery_app
from celery_config import ghm_sync_plans_task_name
from database.models import Owner, Repository
from services.github_marketplace import GitHubMarketplaceService
from services.stripe import stripe
from tasks.base import BaseCodecovTask

log = logging.getLogger(__name__)


class SyncPlansTask(BaseCodecovTask):
    """
    Sync GitHub marketplace plans
    """

    name = ghm_sync_plans_task_name

    async def run_async(self, db_session, sender=None, account=None, action=None):
        log.info(
            "GitHub marketplace sync plans",
            extra=dict(sender=sender, account=account, action=action),
        )

        # Make sure sender and account owner entries exist
        if sender:
            self.upsert_owner(db_session, sender["id"], sender["login"])

        if account:
            self.upsert_owner(db_session, account["id"], account["login"])

        ghm_service = GitHubMarketplaceService()

        if account:
            # TODO sync all team members - 3 year old todo from legacy...

            # Get all the sender plans
            try:
                plans = ghm_service.get_sender_plans(account["id"])
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # account has not purchased the listing
                    await self.sync_plan(
                        db_session, ghm_service, account["id"], None, action=action
                    )
                raise

            await self.sync_plan(
                db_session,
                ghm_service,
                account["id"],
                plans["marketplace_purchase"],
                action=action,
            )
        else:
            has_a_plan = []

            # get codecov plans
            plans = ghm_service.get_codecov_plans()
            plan_ids = [plan["id"] for plan in plans]

            for plan_id in plan_ids:
                page = 0
                # loop through all plan accounts
                while True:
                    page = page + 1
                    accounts = ghm_service.get_plan_accounts(page, plan_id)

                    if len(accounts) == 0:
                        # next plan
                        break

                    # sync each plan
                    for customers in accounts:
                        has_a_plan.append(str(customers["id"]))
                        await self.sync_plan(
                            db_session,
                            ghm_service,
                            customers["id"],
                            customers["marketplace_purchase"],
                            action=action,
                        )

            self.disable_all_inactive(db_session, has_a_plan)

    async def sync_plan(
        self, db_session, ghm_service, service_id, purchase_object, action=None
    ):
        log.info(
            "Sync plan",
            extra=dict(
                service_id=service_id, purchase_object=purchase_object, action=action
            ),
        )

        if not purchase_object:
            self.remove_plan(db_session, ghm_service, service_id)

        elif (
            action != "cancelled"
            and purchase_object["plan"]["id"] in ghm_service.plan_ids
        ):
            self.create_or_update_plan(
                db_session, ghm_service, service_id, purchase_object
            )

        else:
            self.create_or_update_free_plan(db_session, ghm_service, service_id)

    def upsert_owner(self, db_session, service_id, username):
        log.info(
            "Upserting owner", extra=dict(service_id=service_id, username=username)
        )
        owner = (
            db_session.query(Owner)
            .filter(Owner.service == "github", Owner.service_id == str(service_id))
            .first()
        )

        if owner:
            owner.username = username
            owner.updatestamp = datetime.now()
        else:
            owner = self.create_owner(db_session, service_id, username)

        return owner.ownerid

    def create_owner(self, db_session, service_id, username, name=None, email=None):
        owner = Owner(
            service="github",
            service_id=service_id,
            username=username,
            name=name,
            email=email,
            plan_provider="github",
        )
        db_session.add(owner)
        db_session.flush()
        return owner

    def disable_all_inactive(self, db_session, active_account_ids):
        """
        Disable plans that are no longer active
        """
        active_account_ids = list(map(str, active_account_ids))

        db_session.query(Owner).filter(
            Owner.service == "github",
            Owner.plan == "users",
            Owner.plan_provider == "github",
            Owner.service_id.notin_(active_account_ids),
        ).update({Owner.plan: None}, synchronize_session=False)

    def deactivate_repos(self, db_session, ownerid):
        """
        Deactivate all repos for given ownerid
        """
        db_session.query(Repository).filter(Repository.ownerid == ownerid).update(
            {Repository.activated: False}, synchronize_session=False
        )

    def remove_plan(self, db_session, ghm_service, service_id):
        owner = (
            db_session.query(Owner)
            .filter(Owner.service == "github", Owner.service_id == str(service_id))
            .first()
        )

        if owner:
            owner.plan = None
            owner.plan_user_count = 0
            owner.plan_activated_users = None

            self.deactivate_repos(db_session, owner.ownerid)
        else:
            # get user data from GitHub and add to owners table
            user_data = ghm_service.get_user(service_id)
            self.create_owner(
                db_session,
                service_id,
                user_data["login"],
                user_data["name"],
                user_data["email"],
            )

    def create_or_update_plan(
        self, db_session, ghm_service, service_id, purchase_object
    ):
        owner = (
            db_session.query(Owner)
            .filter(Owner.service == "github", Owner.service_id == str(service_id))
            .first()
        )

        if owner:
            owner.plan = "users"
            owner.plan_provider = "github"
            owner.plan_auto_activate = True
            owner.plan_user_count = purchase_object["unit_count"]

            if owner.stripe_customer_id and owner.stripe_subscription_id:
                # cancel strip subscription
                stripe.Subscription.delete(owner.stripe_subscription_id)
                owner.stripe_subscription_id = None
        else:
            # create the user
            user_data = ghm_service.get_user(service_id)
            new_owner = self.create_owner(
                db_session,
                service_id,
                user_data["login"],
                user_data["name"],
                user_data["email"],
            )

            # set plan info
            new_owner.plan = "users"
            new_owner.plan_provider = "github"
            new_owner.plan_auto_activate = True
            new_owner.plan_user_count = purchase_object["unit_count"]

    def create_or_update_free_plan(self, db_session, ghm_service, service_id):
        # free plan -- occurs when the plan isn't known or the action is cancelled.
        owner = (
            db_session.query(Owner)
            .filter(Owner.service == "github", Owner.service_id == str(service_id))
            .first()
        )

        if owner:
            # deactivate repos and remove all activated users for this owner

            # NOTE: when we went to per user billing, we also needed to preserve legacy behavior, so we created a
            # free trial per user plan which is represented as `users-free` since `null` is used by legacy
            # to denote free trial of per repo billing
            plan = owner.plan
            owner.plan = "users-free" if plan == "users" else plan
            owner.plan_user_count = 5
            owner.plan_activated_users = None

            self.deactivate_repos(db_session, owner.ownerid)
        else:
            # create the user
            user_data = ghm_service.get_user(service_id)
            self.create_owner(
                db_session,
                service_id,
                user_data["login"],
                user_data["name"],
                user_data["email"],
            )


RegisteredGHMSyncPlansTask = celery_app.register_task(SyncPlansTask())
ghm_sync_plans_task = celery_app.tasks[SyncPlansTask.name]
