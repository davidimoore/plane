import os
import pytest
import tempfile
import tracemalloc
from unittest.mock import patch, MagicMock, Mock
from plane.bgtasks.export_task import (
    issue_export_task,
    create_zip_file,
    create_zip_file_from_paths,
    LARGE_EXPORT_THRESHOLD,
    CHUNK_SIZE,
)
from plane.db.models import ExporterHistory, Issue, Project, ProjectMember
import io
import zipfile


@pytest.mark.unit
class TestExportTask:
    """Test the issue export task with progress tracking and memory constraints"""

    @pytest.fixture
    def project(self, create_user, workspace):
        """Create a test project"""
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
        """Create an ExporterHistory instance"""
        return ExporterHistory.objects.create(
            workspace=workspace,
            initiated_by=create_user,
            provider='csv',
            status='queued'
        )

    @pytest.fixture
    def mock_issues(self, workspace, project):
        """Create mock issues for testing"""
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
        """Test that ExporterHistory model has the new progress tracking fields"""
        assert hasattr(exporter_history, 'progress_percentage')
        assert hasattr(exporter_history, 'total_items')
        assert hasattr(exporter_history, 'processed_items')
        assert exporter_history.progress_percentage == 0
        assert exporter_history.total_items == 0
        assert exporter_history.processed_items == 0

    @pytest.mark.django_db
    def test_exporter_history_progress_update(self, exporter_history):
        """Test updating progress fields on ExporterHistory"""
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
        """Test that export task sets total_items correctly"""
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
    def test_export_task_uses_file_based_chunked_for_large_exports(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        create_user
    ):
        """Test that export task uses file-based chunked processing for >5000 issues"""
        # Create 6000 mock issues
        for i in range(6000):
            Issue.objects.create(
                name=f"Issue {i}",
                workspace=workspace,
                project=project,
            )

        with patch.object(
            __import__('plane.utils.porters.exporter', fromlist=['DataExporter']).DataExporter,
            'export_chunked_to_file'
        ) as mock_chunked_to_file:
            # Return a tuple of (filename, temp_file_path)
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
            temp_file.write(b'test,content')
            temp_file.close()
            mock_chunked_to_file.return_value = ('test.csv', temp_file.name)

            # Run the export task
            issue_export_task(
                provider='csv',
                workspace_id=workspace.id,
                project_ids=[str(project.id)],
                token_id=exporter_history.token,
                multiple=False,
                slug='test-export'
            )

            # Verify that export_chunked_to_file was called (file-based processing)
            assert mock_chunked_to_file.called

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
        """Test that export task uses regular export for <=5000 issues"""
        with patch('plane.bgtasks.export_task.DataExporter.export') as mock_export:
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

    def test_create_zip_file(self):
        """Test the create_zip_file function"""
        files = [
            ('file1.csv', 'content1'),
            ('file2.csv', 'content2'),
            ('file3.txt', b'binary content')
        ]

        zip_buffer = create_zip_file(files)

        # Verify it's a valid zip file
        assert isinstance(zip_buffer, io.BytesIO)
        zip_buffer.seek(0)

        with zipfile.ZipFile(zip_buffer, 'r') as zipf:
            # Should have 3 files
            assert len(zipf.namelist()) == 3
            assert 'file1.csv' in zipf.namelist()
            assert 'file2.csv' in zipf.namelist()
            assert 'file3.txt' in zipf.namelist()

            # Verify contents
            assert zipf.read('file1.csv').decode('utf-8') == 'content1'
            assert zipf.read('file2.csv').decode('utf-8') == 'content2'
            assert zipf.read('file3.txt') == b'binary content'

    def test_create_zip_file_memory_usage(self):
        """Test that create_zip_file doesn't use excessive memory"""
        tracemalloc.start()

        # Create multiple large files (simulating export output)
        files = []
        for i in range(10):
            # Each file is ~1MB of content
            content = f"Line {i}\n" * 50000
            files.append((f'file_{i}.csv', content))

        zip_buffer = create_zip_file(files)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024

        # Verify zip was created
        assert isinstance(zip_buffer, io.BytesIO)

        # Memory usage should stay reasonable (under 512MB)
        assert peak_mb < 512, f"Peak memory usage was {peak_mb:.2f} MB, expected < 512 MB"

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
        """Test export task with multiple projects"""
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
        """Test that export task handles invalid format gracefully"""
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
        """Test export task with all supported formats"""
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

    def test_create_zip_file_from_paths_with_file_content(self):
        """Test creating a ZIP from file paths"""
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

    def test_create_zip_file_from_paths_cleans_up_source_files(self):
        """Test that source temp files are cleaned up after ZIP creation"""
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

    def test_constants_are_set_correctly(self):
        """Test that export constants are set to expected values"""
        assert LARGE_EXPORT_THRESHOLD == 5000
        assert CHUNK_SIZE == 1000
        assert CHUNK_SIZE < LARGE_EXPORT_THRESHOLD


@pytest.mark.unit
class TestExportMemoryEfficiency:
    """Tests specifically for memory efficiency of export operations"""

    def test_file_based_zip_memory_usage(self):
        """Test that file-based ZIP creation keeps memory usage low"""
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
            # The actual limit may vary, but file-based approach should be much lower
            assert peak_mb < 512, f"Peak memory usage was {peak_mb:.2f} MB, expected < 512 MB"

        finally:
            if os.path.exists(zip_path):
                os.unlink(zip_path)
            for path in temp_files:
                if os.path.exists(path):
                    os.unlink(path)
