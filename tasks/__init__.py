# ruff: noqa: F401
from app import celery_app
from tasks.ai_pr_review import ai_pr_view_task
from tasks.backfill_commit_data_to_storage import backfill_commit_data_to_storage_task
from tasks.backfill_existing_gh_app_installations import (
    backfill_existing_gh_app_installations_name,
    backfill_existing_individual_gh_app_installation_name,
)
from tasks.backfill_owners_without_gh_app_installations import (
    backfill_owners_without_gh_app_installation_individual_name,
    backfill_owners_without_gh_app_installations_name,
)
from tasks.brolly_stats_rollup import brolly_stats_rollup_task
from tasks.bundle_analysis_notify import bundle_analysis_notify_task
from tasks.bundle_analysis_processor import bundle_analysis_processor_task
from tasks.bundle_analysis_save_measurements import (
    bundle_analysis_save_measurements_task,
)
from tasks.commit_update import commit_update_task
from tasks.compute_comparison import compute_comparison_task
from tasks.delete_owner import delete_owner_task
from tasks.flush_repo import flush_repo
from tasks.github_app_webhooks_check import gh_webhook_check_task
from tasks.github_marketplace import ghm_sync_plans_task
from tasks.health_check import health_check_task
from tasks.hourly_check import hourly_check_task
from tasks.http_request import http_request_task
from tasks.label_analysis import label_analysis_task
from tasks.manual_trigger import manual_trigger_task
from tasks.mutation_test_upload import mutation_test_upload_task
from tasks.new_user_activated import new_user_activated_task
from tasks.notify import notify_task
from tasks.plan_manager_task import daily_plan_manager_task_name
from tasks.preprocess_upload import preprocess_upload_task
from tasks.process_flakes import process_flakes_task
from tasks.profiling_find_uncollected import find_untotalized_profilings_task
from tasks.profiling_normalizer import profiling_normalizer_task
from tasks.save_commit_measurements import save_commit_measurements_task
from tasks.save_report_results import save_report_results_task
from tasks.send_email import send_email
from tasks.static_analysis_suite_check import static_analysis_suite_check_task
from tasks.status_set_error import status_set_error_task
from tasks.status_set_pending import status_set_pending_task
from tasks.sync_pull import pull_sync_task
from tasks.sync_repo_languages import sync_repo_language_task
from tasks.sync_repo_languages_gql import sync_repo_languages_gql_task
from tasks.sync_repos import sync_repos_task
from tasks.sync_teams import sync_teams_task
from tasks.test_results_finisher import test_results_finisher_task
from tasks.test_results_processor import test_results_processor_task
from tasks.timeseries_backfill import (
    timeseries_backfill_commits_task,
    timeseries_backfill_dataset_task,
)
from tasks.timeseries_delete import timeseries_delete_task
from tasks.trial_expiration import trial_expiration_task
from tasks.trial_expiration_cron import trial_expiration_cron_task
from tasks.update_branches import update_branches_task_name
from tasks.upload import upload_task
from tasks.upload_clean_labels_index import clean_labels_index_task
from tasks.upload_finisher import upload_finisher_task
from tasks.upload_processor import upload_processor_task
