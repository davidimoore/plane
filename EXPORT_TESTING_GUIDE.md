# Export Optimization - Testing & Verification Guide

## Quick Start

This guide helps you verify that the export optimization implementation works correctly.

## Prerequisites

1. Docker containers running (check with `docker ps`)
2. Database accessible
3. Test data available (or create test issues)

## Step 1: Apply Database Migration

First, apply the migration to add progress tracking fields:

```bash
# If using Docker
docker exec plane-2-api-1 python manage.py migrate

# If running locally
cd apps/api
python manage.py migrate
```

Expected output:
```
Running migrations:
  Applying db.0117_exporterhistory_progress_tracking... OK
```

## Step 2: Verify Model Changes

Test that the new fields are accessible:

```bash
docker exec plane-2-api-1 python manage.py shell
```

Then in the Python shell:
```python
from plane.db.models import ExporterHistory

# Check fields exist
fields = [f.name for f in ExporterHistory._meta.fields]
print('progress_percentage' in fields)  # Should print True
print('total_items' in fields)  # Should print True
print('processed_items' in fields)  # Should print True
```

## Step 3: Run Unit Tests

### Test DataExporter Chunked Methods

```bash
# Run all exporter tests
docker exec plane-2-api-1 python -m pytest plane/tests/unit/utils/test_exporter_chunked.py -v

# Run specific memory test
docker exec plane-2-api-1 python -m pytest \
  plane/tests/unit/utils/test_exporter_chunked.py::TestDataExporterChunked::test_chunked_export_memory_usage_csv \
  -v -s
```

### Test Export Task Integration

```bash
# Run all export task tests
docker exec plane-2-api-1 python -m pytest plane/tests/unit/bg_tasks/test_export_task.py -v

# Run specific test
docker exec plane-2-api-1 python -m pytest \
  plane/tests/unit/bg_tasks/test_export_task.py::TestExportTask::test_export_task_uses_chunked_for_large_exports \
  -v
```

### Run All Tests with Coverage

```bash
docker exec plane-2-api-1 python -m pytest \
  plane/tests/unit/utils/test_exporter_chunked.py \
  plane/tests/unit/bg_tasks/test_export_task.py \
  --cov=plane.utils.porters.exporter \
  --cov=plane.bgtasks.export_task \
  --cov-report=term-missing
```

## Step 4: Manual Testing

### Create Test Data

Create a project with many issues for testing:

```python
# In Django shell (docker exec plane-2-api-1 python manage.py shell)
from plane.db.models import Workspace, Project, Issue, User

# Get or create test user
user = User.objects.first()

# Get or create test workspace
workspace = Workspace.objects.first()

# Create test project
project = Project.objects.create(
    name="Export Test Project",
    identifier="export-test",
    workspace=workspace
)

# Create 6000 test issues (to trigger chunked processing)
issues = []
for i in range(6000):
    issue = Issue(
        name=f"Test Issue {i}",
        workspace=workspace,
        project=project,
        description=f"This is test issue number {i}",
    )
    issues.append(issue)

    # Bulk create every 1000 issues
    if len(issues) >= 1000:
        Issue.objects.bulk_create(issues)
        issues = []
        print(f"Created {i+1} issues...")

# Create remaining issues
if issues:
    Issue.objects.bulk_create(issues)
    print("Finished creating test issues")
```

### Trigger an Export

1. Log in to Plane web interface
2. Navigate to the test project
3. Go to Issues view
4. Click Export button
5. Select CSV format
6. Click Export

### Monitor Export Progress

```python
# In Django shell
from plane.db.models import ExporterHistory

# Get the latest export
export = ExporterHistory.objects.latest('created_at')

# Check progress
print(f"Status: {export.status}")
print(f"Total items: {export.total_items}")
print(f"Processed items: {export.processed_items}")
print(f"Progress: {export.progress_percentage}%")

# Keep checking until complete
import time
while export.status == 'processing':
    export.refresh_from_db()
    print(f"Progress: {export.progress_percentage}%")
    time.sleep(2)

print(f"Final status: {export.status}")
if export.url:
    print(f"Download URL: {export.url}")
```

### Monitor Memory Usage

While export is running, check memory usage:

```bash
# Monitor container memory
docker stats plane-2-worker-1 --no-stream

# Check Celery worker logs
docker logs -f plane-2-worker-1
```

Expected: Memory should stay under 512MB even for 6000+ issues.

## Step 5: Verify Export Output

### Download and Verify ZIP

1. Download the export ZIP from the URL provided
2. Extract the ZIP file
3. Verify CSV/JSON/XLSX file contains all expected records

```bash
# Count lines in CSV (should be 6001: 6000 data + 1 header)
unzip -p export.zip *.csv | wc -l

# Check JSON record count
unzip -p export.zip *.json | jq '. | length'

# Check XLSX (requires openpyxl)
python3 << EOF
from openpyxl import load_workbook
import zipfile

with zipfile.ZipFile('export.zip', 'r') as zf:
    xlsx_file = [f for f in zf.namelist() if f.endswith('.xlsx')][0]
    with zf.open(xlsx_file) as f:
        wb = load_workbook(f)
        ws = wb.active
        print(f"Rows in XLSX: {ws.max_row}")
EOF
```

## Step 6: Performance Testing

### Benchmark Regular vs Chunked Export

```python
# In Django shell
import time
import tracemalloc
from plane.db.models import Issue, Workspace, Project
from plane.utils.porters.exporter import DataExporter
from plane.utils.porters.serializers.issue import IssueExportSerializer

# Get test data
workspace = Workspace.objects.first()
project = Project.objects.filter(name="Export Test Project").first()
queryset = Issue.objects.filter(project=project)[:5000]

print(f"Testing with {queryset.count()} issues")

# Test regular export
print("\n=== Regular Export ===")
tracemalloc.start()
start = time.time()

exporter = DataExporter(IssueExportSerializer, format_type='csv')
filename, content = exporter.export('test-regular', queryset)

regular_time = time.time() - start
current, regular_peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

print(f"Time: {regular_time:.2f}s")
print(f"Peak memory: {regular_peak / 1024 / 1024:.2f} MB")
print(f"Content size: {len(content) / 1024 / 1024:.2f} MB")

# Test chunked export
print("\n=== Chunked Export ===")
tracemalloc.start()
start = time.time()

exporter = DataExporter(IssueExportSerializer, format_type='csv')
filename, content = exporter.export_chunked('test-chunked', queryset, chunk_size=1000)

chunked_time = time.time() - start
current, chunked_peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

print(f"Time: {chunked_time:.2f}s")
print(f"Peak memory: {chunked_peak / 1024 / 1024:.2f} MB")
print(f"Content size: {len(content) / 1024 / 1024:.2f} MB")

# Compare
print("\n=== Comparison ===")
print(f"Time difference: {((chunked_time - regular_time) / regular_time * 100):.1f}%")
print(f"Memory savings: {((regular_peak - chunked_peak) / regular_peak * 100):.1f}%")
```

Expected results:
- Chunked export should use 60-80% less memory
- Time difference should be minimal (<10%)

## Step 7: Stress Testing

### Test with Large Dataset

```python
# Create 15,000 issues
from plane.db.models import Issue, Workspace, Project

workspace = Workspace.objects.first()
project = Project.objects.filter(name="Export Test Project").first()

print("Creating 15,000 test issues...")
for batch in range(15):
    issues = []
    for i in range(1000):
        issue_num = batch * 1000 + i
        issues.append(Issue(
            name=f"Stress Test Issue {issue_num}",
            workspace=workspace,
            project=project,
            description=f"Description {issue_num}"
        ))
    Issue.objects.bulk_create(issues)
    print(f"Created {(batch + 1) * 1000} issues...")

print("Done! Now trigger an export and monitor memory.")
```

Monitor the export:
```bash
# Watch memory usage in real-time
watch -n 1 'docker stats plane-2-worker-1 --no-stream'

# Watch export progress
docker exec plane-2-api-1 python manage.py shell -c "
from plane.db.models import ExporterHistory
export = ExporterHistory.objects.latest('created_at')
export.refresh_from_db()
print(f'{export.progress_percentage}% - {export.processed_items}/{export.total_items}')
"
```

## Troubleshooting

### Tests Fail with "No module named 'plane'"

Solution: Run tests inside Docker container or set up local environment properly.

### Tests Fail with Redis Connection Error

Solution: Ensure Docker containers are running: `docker-compose up -d`

### Migration Fails with "relation already exists"

Solution: The fields may already exist. Check with:
```sql
docker exec plane-2-plane-db-1 psql -U plane -d plane -c "\d exporters"
```

### Export Task Doesn't Start

Check Celery worker logs:
```bash
docker logs plane-2-worker-1 --tail 100
```

### Memory Still Too High

Reduce chunk size in `export_task.py`:
```python
chunk_size = 500  # Reduce from 1000 to 500
```

## Success Criteria

✅ Migration applies successfully
✅ All unit tests pass
✅ Export completes without OOM errors
✅ Memory usage stays under 512MB
✅ Progress tracking updates correctly
✅ Export output contains all records
✅ Performance overhead is minimal (<10%)

## Next Steps

After verification:
1. Commit changes to version control
2. Deploy to staging environment
3. Run full integration test suite
4. Monitor staging for 24-48 hours
5. Deploy to production with monitoring
6. Update user documentation

## Additional Resources

- **Implementation Summary**: See `EXPORT_OPTIMIZATION_SUMMARY.md`
- **Python Memory Profiling**: https://docs.python.org/3/library/tracemalloc.html
- **Celery Best Practices**: https://docs.celeryproject.org/en/stable/userguide/tasks.html
- **Django Query Optimization**: https://docs.djangoproject.com/en/4.2/topics/db/optimization/
