# Python imports
import io
import os
import tempfile
import zipfile
from typing import List, Union
import boto3
from botocore.client import Config
from uuid import UUID

# Third party imports
from celery import shared_task

# Django imports
from django.conf import settings
from django.utils import timezone
from django.db.models import Prefetch

# Module imports
from plane.db.models import ExporterHistory, Issue, IssueComment, IssueRelation, IssueSubscriber
from plane.utils.exception_logger import log_exception
from plane.utils.porters.exporter import DataExporter
from plane.utils.porters.serializers.issue import IssueExportSerializer

# Constants
LARGE_EXPORT_THRESHOLD = 5000
CHUNK_SIZE = 1000


def build_issue_queryset(workspace_id: UUID, project_ids: List[str], initiated_by_id: UUID):
    """
    Build the optimized queryset for fetching issues with all related data.
    """
    return (
        Issue.objects.filter(
            workspace__id=workspace_id,
            project_id__in=project_ids,
            project__project_projectmember__member=initiated_by_id,
            project__project_projectmember__is_active=True,
            project__archived_at__isnull=True,
        )
        .select_related(
            "project",
            "workspace",
            "state",
            "created_by",
            "estimate_point",
        )
        .prefetch_related(
            "labels",
            "issue_cycle__cycle",
            "issue_module__module",
            "assignees",
            "issue_link",
            Prefetch(
                "issue_subscribers",
                queryset=IssueSubscriber.objects.select_related("subscriber"),
            ),
            Prefetch(
                "issue_comments",
                queryset=IssueComment.objects.select_related("actor").order_by("created_at"),
            ),
            Prefetch(
                "issue_relation",
                queryset=IssueRelation.objects.select_related("related_issue", "related_issue__project"),
            ),
            Prefetch(
                "issue_related",
                queryset=IssueRelation.objects.select_related("issue", "issue__project"),
            ),
            Prefetch(
                "parent",
                queryset=Issue.objects.select_related("type", "project"),
            ),
        )
    )


def create_zip_file(files: List[tuple[str, str | bytes]]) -> io.BytesIO:
    """
    Create a ZIP file from the provided files in memory.
    Used for small exports (<= LARGE_EXPORT_THRESHOLD issues).
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for filename, file_content in files:
            zipf.writestr(filename, file_content)

    zip_buffer.seek(0)
    return zip_buffer


def create_zip_file_from_paths(
    file_entries: List[tuple[str, Union[str, bytes], bool]]
) -> str:
    """
    Create a ZIP file on disk from file paths and/or content.

    Args:
        file_entries: List of tuples (archive_name, content_or_path, is_file_path)
            - archive_name: Name in the ZIP archive
            - content_or_path: Either file content (str/bytes) or path to temp file
            - is_file_path: True if content_or_path is a file path

    Returns:
        Path to the created ZIP file. Caller is responsible for cleanup.
    """
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_zip.close()

    temp_files_to_cleanup = []

    try:
        with zipfile.ZipFile(temp_zip.name, "w", zipfile.ZIP_DEFLATED) as zipf:
            for archive_name, content_or_path, is_file_path in file_entries:
                if is_file_path:
                    # Add file from disk path
                    zipf.write(content_or_path, archive_name)
                    temp_files_to_cleanup.append(content_or_path)
                else:
                    # Add content directly
                    zipf.writestr(archive_name, content_or_path)

        return temp_zip.name

    except Exception:
        # Clean up ZIP file on error
        if os.path.exists(temp_zip.name):
            os.unlink(temp_zip.name)
        raise

    finally:
        # Clean up source temp files
        for temp_path in temp_files_to_cleanup:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


# TODO: Change the upload_to_s3 function to use the new storage method with entry in file asset table
def upload_to_s3(
    zip_file: Union[io.BytesIO, str],
    workspace_id: UUID,
    token_id: str,
    slug: str,
    is_file_path: bool = False
) -> None:
    """
    Upload a ZIP file to S3 and generate a presigned URL.

    Args:
        zip_file: Either a BytesIO object or a path to a ZIP file on disk
        workspace_id: The workspace UUID
        token_id: The export token
        slug: The workspace slug
        is_file_path: If True, zip_file is a path to a file on disk
    """
    file_name = f"{workspace_id}/export-{slug}-{token_id[:6]}-{str(timezone.now().date())}.zip"
    expires_in = 7 * 24 * 60 * 60

    # Handle file path vs BytesIO
    if is_file_path:
        file_obj = open(zip_file, "rb")
    else:
        file_obj = zip_file

    try:
        if settings.USE_MINIO:
            upload_s3 = boto3.client(
                "s3",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4"),
            )
            upload_s3.upload_fileobj(
                file_obj,
                settings.AWS_STORAGE_BUCKET_NAME,
                file_name,
                ExtraArgs={"ACL": "public-read", "ContentType": "application/zip"},
            )

            # Generate presigned url for the uploaded file with different base
            presign_s3 = boto3.client(
                "s3",
                endpoint_url=(
                    f"{settings.AWS_S3_URL_PROTOCOL}//{str(settings.AWS_S3_CUSTOM_DOMAIN).replace('/uploads', '')}/"
                ),
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4"),
            )

            presigned_url = presign_s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": file_name},
                ExpiresIn=expires_in,
            )
        else:
            # If endpoint url is present, use it
            if settings.AWS_S3_ENDPOINT_URL:
                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    config=Config(signature_version="s3v4"),
                )
            else:
                s3 = boto3.client(
                    "s3",
                    region_name=settings.AWS_REGION,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    config=Config(signature_version="s3v4"),
                )

            # Upload the file to S3
            s3.upload_fileobj(
                file_obj,
                settings.AWS_STORAGE_BUCKET_NAME,
                file_name,
                ExtraArgs={"ContentType": "application/zip"},
            )

            # Generate presigned url for the uploaded file
            presigned_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": file_name},
                ExpiresIn=expires_in,
            )
    finally:
        if is_file_path:
            file_obj.close()
            # Clean up the temp ZIP file
            if os.path.exists(zip_file):
                os.unlink(zip_file)

    exporter_instance = ExporterHistory.objects.get(token=token_id)

    # Update the exporter instance with the presigned url
    if presigned_url:
        exporter_instance.url = presigned_url
        exporter_instance.status = "completed"
        exporter_instance.key = file_name
        exporter_instance.progress_percentage = 100
    else:
        exporter_instance.status = "failed"

    exporter_instance.save(update_fields=["status", "url", "key", "progress_percentage"])


@shared_task
def issue_export_task(
    provider: str,
    workspace_id: UUID,
    project_ids: List[str],
    token_id: str,
    multiple: bool,
    slug: str,
):
    """
    Export issues from the workspace.
    provider (str): The provider to export the issues to csv | json | xlsx.
    token_id (str): The export object token id.
    multiple (bool): Whether to export the issues to multiple files per project.

    For exports with more than LARGE_EXPORT_THRESHOLD issues, uses file-based
    chunked processing to keep memory usage low (<512MB).
    """
    try:
        exporter_instance = ExporterHistory.objects.get(token=token_id)
        exporter_instance.status = "processing"
        exporter_instance.save(update_fields=["status"])

        # Build base queryset for issues
        workspace_issues = build_issue_queryset(
            workspace_id, project_ids, exporter_instance.initiated_by_id
        )

        # Count total issues for progress tracking
        total_issues = workspace_issues.count()

        # Update exporter with total count
        exporter_instance.total_items = total_issues
        exporter_instance.save(update_fields=["total_items"])

        # Determine if we need chunked processing
        use_chunked = total_issues > LARGE_EXPORT_THRESHOLD

        # Create exporter for the specified format
        try:
            exporter = DataExporter(IssueExportSerializer, format_type=provider)
        except ValueError as e:
            # Invalid format type
            exporter_instance = ExporterHistory.objects.get(token=token_id)
            exporter_instance.status = "failed"
            exporter_instance.reason = str(e)
            exporter_instance.save(update_fields=["status", "reason"])
            return

        # Determine if we should use file-based chunked processing
        use_file_based = total_issues > LARGE_EXPORT_THRESHOLD

        if use_file_based:
            # Large export: use file-based processing to keep memory low
            _process_large_export(
                exporter, exporter_instance, workspace_issues, project_ids,
                multiple, slug, workspace_id, token_id, total_issues
            )
        else:
            # Small export: use in-memory processing
            _process_small_export(
                exporter, exporter_instance, workspace_issues, project_ids,
                multiple, slug, workspace_id, token_id, total_issues
            )

    except Exception as e:
        exporter_instance = ExporterHistory.objects.get(token=token_id)
        exporter_instance.status = "failed"
        exporter_instance.reason = str(e)
        exporter_instance.save(update_fields=["status", "reason"])
        log_exception(e)
        return


def _process_small_export(
    exporter: DataExporter,
    exporter_instance: ExporterHistory,
    workspace_issues,
    project_ids: List[str],
    multiple: bool,
    slug: str,
    workspace_id: UUID,
    token_id: str,
    total_issues: int,
) -> None:
    """
    Process a small export (<= LARGE_EXPORT_THRESHOLD issues) in memory.
    """
    files = []

    if multiple:
        # Export each project separately
        for project_id in project_ids:
            project_issues = workspace_issues.filter(project_id=project_id)
            project_count = project_issues.count()
            export_filename = f"{slug}-{project_id}"

            filename, content = exporter.export(export_filename, project_issues)
            files.append((filename, content))

            # Update progress
            exporter_instance.processed_items += project_count
            if total_issues > 0:
                exporter_instance.progress_percentage = int(
                    (exporter_instance.processed_items / total_issues) * 100
                )
            exporter_instance.save(update_fields=["processed_items", "progress_percentage"])
    else:
        # Export all issues in a single file
        export_filename = f"{slug}-{workspace_id}"
        filename, content = exporter.export(export_filename, workspace_issues)
        files.append((filename, content))

        # Update progress to 100%
        exporter_instance.processed_items = total_issues
        exporter_instance.progress_percentage = 100
        exporter_instance.save(update_fields=["processed_items", "progress_percentage"])

    # Create ZIP in memory and upload
    zip_buffer = create_zip_file(files)
    upload_to_s3(zip_buffer, workspace_id, token_id, slug, is_file_path=False)


def _process_large_export(
    exporter: DataExporter,
    exporter_instance: ExporterHistory,
    workspace_issues,
    project_ids: List[str],
    multiple: bool,
    slug: str,
    workspace_id: UUID,
    token_id: str,
    total_issues: int,
) -> None:
    """
    Process a large export (> LARGE_EXPORT_THRESHOLD issues) using file-based
    chunked processing to keep memory usage under 512MB.
    """
    # file_entries: list of (archive_name, content_or_path, is_file_path)
    file_entries = []
    temp_files = []

    try:
        if multiple:
            # Export each project separately
            for project_id in project_ids:
                project_issues = workspace_issues.filter(project_id=project_id)
                project_count = project_issues.count()
                export_filename = f"{slug}-{project_id}"

                # Use file-based export for this project
                filename, temp_path = exporter.export_chunked_to_file(
                    export_filename, project_issues, CHUNK_SIZE
                )
                file_entries.append((filename, temp_path, True))
                temp_files.append(temp_path)

                # Update progress
                exporter_instance.processed_items += project_count
                if total_issues > 0:
                    exporter_instance.progress_percentage = int(
                        (exporter_instance.processed_items / total_issues) * 100
                    )
                exporter_instance.save(update_fields=["processed_items", "progress_percentage"])
        else:
            # Export all issues in a single file
            export_filename = f"{slug}-{workspace_id}"

            filename, temp_path = exporter.export_chunked_to_file(
                export_filename, workspace_issues, CHUNK_SIZE
            )
            file_entries.append((filename, temp_path, True))
            temp_files.append(temp_path)

            # Update progress to 100%
            exporter_instance.processed_items = total_issues
            exporter_instance.progress_percentage = 100
            exporter_instance.save(update_fields=["processed_items", "progress_percentage"])

        # Create ZIP from temp files (this also cleans up source temp files)
        zip_path = create_zip_file_from_paths(file_entries)

        # Upload ZIP and clean it up
        upload_to_s3(zip_path, workspace_id, token_id, slug, is_file_path=True)

    except Exception:
        # Clean up any remaining temp files on error
        for temp_path in temp_files:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        raise
