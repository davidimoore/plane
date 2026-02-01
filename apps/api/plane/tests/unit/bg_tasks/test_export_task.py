import io
import os
import tempfile
import tracemalloc
import zipfile

import pytest
from unittest.mock import patch, MagicMock

from plane.bgtasks.export_task import (
    issue_export_task,
    create_zip_file,
    create_zip_file_from_paths,
    CHUNK_SIZE,
    LARGE_EXPORT_THRESHOLD,
)
from plane.db.models import ExporterHistory, Issue, Project, ProjectMember


# Memory limit in bytes (512MB)
MEMORY_LIMIT_BYTES = 512 * 1024 * 1024


@pytest.mark.unit
class TestCreateZipFile:
    """Tests for the create_zip_file function (in-memory ZIP creation)."""

    def test_creates_valid_zip_with_single_file(self):
        """Test creating a ZIP with a single file."""
        files = [("test.txt", "Hello, World!")]
        result = create_zip_file(files)

        assert isinstance(result, io.BytesIO)

        # Verify ZIP contents
        with zipfile.ZipFile(result, "r") as zf:
            assert zf.namelist() == ["test.txt"]
            assert zf.read("test.txt") == b"Hello, World!"

    def test_creates_valid_zip_with_multiple_files(self):
        """Test creating a ZIP with multiple files."""
        files = [
            ("file1.csv", "id,name\n1,test"),
            ("file2.json", '{"key": "value"}'),
            ("file3.txt", b"binary content"),
        ]
        result = create_zip_file(files)

        with zipfile.ZipFile(result, "r") as zf:
            assert len(zf.namelist()) == 3
            assert "file1.csv" in zf.namelist()
            assert "file2.json" in zf.namelist()
            assert "file3.txt" in zf.namelist()

    def test_creates_empty_zip_with_no_files(self):
        """Test creating a ZIP with no files."""
        files = []
        result = create_zip_file(files)

        with zipfile.ZipFile(result, "r") as zf:
            assert zf.namelist() == []

    def test_zip_is_seeked_to_beginning(self):
        """Test that the returned BytesIO is seeked to the beginning."""
        files = [("test.txt", "content")]
        result = create_zip_file(files)

        # Should be able to read immediately without seeking
        assert result.tell() == 0


@pytest.mark.unit
class TestCreateZipFileFromPaths:
    """Tests for the create_zip_file_from_paths function (file-based ZIP creation)."""

    def test_creates_zip_from_file_paths(self):
        """Test creating a ZIP from file paths."""
        # Create temp files
        temp1 = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
        temp1.write(b'id,name\n1,test')
        temp1.close()

        temp2 = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        temp2.write(b'{"key": "value"}')
        temp2.close()

        try:
            # Create ZIP from file paths
            file_entries = [
                ('data.csv', temp1.name, True),
                ('meta.json', temp2.name, True),
                ('inline.txt', 'inline content', False),
            ]

            zip_path = create_zip_file_from_paths(file_entries)

            # Verify ZIP was created
            assert os.path.exists(zip_path)

            # Verify contents
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                assert len(zipf.namelist()) == 3
                assert zipf.read('data.csv') == b'id,name\n1,test'
                assert zipf.read('meta.json') == b'{"key": "value"}'
                assert zipf.read('inline.txt') == b'inline content'

            # Clean up
            os.unlink(zip_path)

        finally:
            # Source temp files should be cleaned up by the function
            # but clean up if they still exist
            for path in [temp1.name, temp2.name]:
                if os.path.exists(path):
                    os.unlink(path)

    def test_cleans_up_source_files(self):
        """Test that source temp files are cleaned up after ZIP creation."""
        temp1 = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
        temp1.write(b'content')
        temp1.close()

        file_entries = [('data.csv', temp1.name, True)]
        zip_path = create_zip_file_from_paths(file_entries)

        try:
            # Source file should be cleaned up
            assert not os.path.exists(temp1.name), "Source temp file should be deleted"
            # ZIP file should exist
            assert os.path.exists(zip_path)
        finally:
            if os.path.exists(zip_path):
                os.unlink(zip_path)


@pytest.mark.unit
class TestMemoryUsage:
    """Tests to verify memory usage stays within limits."""

    def test_in_memory_zip_for_small_data(self):
        """Test that in-memory ZIP works fine for small data."""
        tracemalloc.start()

        # Small amount of data
        small_content = "test content " * 100
        files = [("small_file.txt", small_content)]

        zip_buffer = create_zip_file(files)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert peak < MEMORY_LIMIT_BYTES
        assert isinstance(zip_buffer, io.BytesIO)

    def test_file_based_zip_memory_usage(self):
        """Test that file-based ZIP creation keeps memory usage low."""
        tracemalloc.start()

        # Create temp files with ~5MB content each
        temp_files = []
        file_entries = []
        for i in range(5):
            temp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
            content = f"row,{i}\n" * 500000  # ~5MB per file
            temp.write(content.encode())
            temp.close()
            temp_files.append(temp.name)
            file_entries.append((f'file_{i}.csv', temp.name, True))

        zip_path = create_zip_file_from_paths(file_entries)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024

        try:
            # Verify ZIP was created
            assert os.path.exists(zip_path)

            # Memory should stay under 512MB even with large files
            assert peak_mb < 512, f"Peak memory usage was {peak_mb:.2f} MB, expected < 512 MB"

        finally:
            if os.path.exists(zip_path):
                os.unlink(zip_path)
            for path in temp_files:
                if os.path.exists(path):
                    os.unlink(path)


@pytest.mark.unit
class TestConstants:
    """Tests for module constants."""

    def test_chunk_size_is_reasonable(self):
        """Test that CHUNK_SIZE is set to a reasonable value."""
        assert CHUNK_SIZE == 1000
        assert CHUNK_SIZE > 0
        assert CHUNK_SIZE <= 5000

    def test_large_export_threshold(self):
        """Test that LARGE_EXPORT_THRESHOLD is set correctly."""
        assert LARGE_EXPORT_THRESHOLD == 5000
        assert LARGE_EXPORT_THRESHOLD > CHUNK_SIZE


@pytest.mark.unit
class TestExportTask:
    """Test the issue export task with progress tracking."""

    @pytest.fixture
    def project(self, create_user, workspace):
        """Create a test project."""
        project = Project.objects.create(
            name="Test Project",
            identifier="test-project",
            workspace=workspace
        )
        ProjectMember.objects.create(
            project=project,
            member=create_user,
            role=20,
            is_active=True
        )
        return project

    @pytest.fixture
    def exporter_history(self, workspace, create_user):
        """Create an ExporterHistory instance."""
        return ExporterHistory.objects.create(
            workspace=workspace,
            initiated_by=create_user,
            provider='csv',
            status='queued'
        )

    @pytest.fixture
    def mock_issues(self, workspace, project):
        """Create mock issues for testing."""
        issues = []
        for i in range(100):
            issue = Issue.objects.create(
                name=f"Test Issue {i}",
                workspace=workspace,
                project=project,
                description=f"Description for issue {i}",
            )
            issues.append(issue)
        return issues

    @pytest.mark.django_db
    def test_exporter_history_has_progress_fields(self, exporter_history):
        """Test that ExporterHistory model has the new progress tracking fields."""
        assert hasattr(exporter_history, 'progress_percentage')
        assert hasattr(exporter_history, 'total_items')
        assert hasattr(exporter_history, 'processed_items')
        assert exporter_history.progress_percentage == 0
        assert exporter_history.total_items == 0
        assert exporter_history.processed_items == 0

    @pytest.mark.django_db
    def test_exporter_history_progress_update(self, exporter_history):
        """Test updating progress fields on ExporterHistory."""
        exporter_history.total_items = 1000
        exporter_history.processed_items = 500
        exporter_history.progress_percentage = 50
        exporter_history.save()

        # Reload from database
        exporter_history.refresh_from_db()

        assert exporter_history.total_items == 1000
        assert exporter_history.processed_items == 500
        assert exporter_history.progress_percentage == 50

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_sets_total_items(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        mock_issues,
        create_user
    ):
        """Test that export task sets total_items correctly."""
        # Run the export task
        issue_export_task(
            provider='csv',
            workspace_id=workspace.id,
            project_ids=[str(project.id)],
            token_id=exporter_history.token,
            multiple=False,
            slug='test-export'
        )

        # Reload exporter history
        exporter_history.refresh_from_db()

        # Should have counted 100 issues
        assert exporter_history.total_items == 100
        assert exporter_history.processed_items == 100
        assert exporter_history.progress_percentage == 100

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_uses_file_based_for_large_exports(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        create_user
    ):
        """Test that export task uses file-based processing for >5000 issues."""
        # Create 6000 mock issues
        for i in range(6000):
            Issue.objects.create(
                name=f"Issue {i}",
                workspace=workspace,
                project=project,
            )

        with patch('plane.utils.porters.exporter.DataExporter.export_chunked_to_file') as mock_chunked:
            # Return a tuple of (filename, temp_file_path)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
            temp_file.write(b'test,content')
            temp_file.close()
            mock_chunked.return_value = ('test.csv', temp_file.name)

            # Run the export task
            issue_export_task(
                provider='csv',
                workspace_id=workspace.id,
                project_ids=[str(project.id)],
                token_id=exporter_history.token,
                multiple=False,
                slug='test-export'
            )

            # Verify that export_chunked_to_file was called
            assert mock_chunked.called

        # Reload exporter history
        exporter_history.refresh_from_db()

        assert exporter_history.total_items == 6000

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_uses_regular_export_for_small_datasets(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        mock_issues,
        create_user
    ):
        """Test that export task uses regular export for <=5000 issues."""
        with patch('plane.utils.porters.exporter.DataExporter.export') as mock_export:
            mock_export.return_value = ('test.csv', 'test,content')

            # Run the export task
            issue_export_task(
                provider='csv',
                workspace_id=workspace.id,
                project_ids=[str(project.id)],
                token_id=exporter_history.token,
                multiple=False,
                slug='test-export'
            )

            # Verify that regular export was called
            assert mock_export.called

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_handles_multiple_projects(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        create_user
    ):
        """Test export task with multiple projects."""
        # Create second project
        project2 = Project.objects.create(
            name="Test Project 2",
            identifier="test-project-2",
            workspace=workspace
        )
        ProjectMember.objects.create(
            project=project2,
            member=create_user,
            role=20,
            is_active=True
        )

        # Create issues in both projects
        for i in range(50):
            Issue.objects.create(
                name=f"Issue P1 {i}",
                workspace=workspace,
                project=project,
            )
        for i in range(30):
            Issue.objects.create(
                name=f"Issue P2 {i}",
                workspace=workspace,
                project=project2,
            )

        # Run export with multiple=True
        issue_export_task(
            provider='csv',
            workspace_id=workspace.id,
            project_ids=[str(project.id), str(project2.id)],
            token_id=exporter_history.token,
            multiple=True,
            slug='test-export'
        )

        # Reload exporter history
        exporter_history.refresh_from_db()

        # Should have counted all 80 issues
        assert exporter_history.total_items == 80
        assert exporter_history.processed_items == 80
        assert exporter_history.progress_percentage == 100

    @pytest.mark.django_db
    def test_export_task_handles_invalid_format(
        self,
        workspace,
        project,
        exporter_history,
        create_user
    ):
        """Test that export task handles invalid format gracefully."""
        # Run with invalid format
        issue_export_task(
            provider='invalid_format',
            workspace_id=workspace.id,
            project_ids=[str(project.id)],
            token_id=exporter_history.token,
            multiple=False,
            slug='test-export'
        )

        # Reload exporter history
        exporter_history.refresh_from_db()

        # Should be marked as failed
        assert exporter_history.status == 'failed'
        assert 'Unsupported format' in exporter_history.reason

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_all_formats(
        self,
        mock_upload,
        workspace,
        project,
        create_user,
        mock_issues
    ):
        """Test export task with all supported formats."""
        formats = ['csv', 'json', 'xlsx']

        for fmt in formats:
            exporter = ExporterHistory.objects.create(
                workspace=workspace,
                initiated_by=create_user,
                provider=fmt,
                status='queued'
            )

            issue_export_task(
                provider=fmt,
                workspace_id=workspace.id,
                project_ids=[str(project.id)],
                token_id=exporter.token,
                multiple=False,
                slug=f'test-export-{fmt}'
            )

            # Reload and verify
            exporter.refresh_from_db()
            assert exporter.total_items == 100, f"Failed for format {fmt}"
            assert exporter.processed_items == 100, f"Failed for format {fmt}"
