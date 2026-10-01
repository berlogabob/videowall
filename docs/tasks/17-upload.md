# 17 Upload from the office
Goal: staff upload a photo or video in the office; within a minute it is in ~/tv-media (TV and wall).
DB: append private bucket wall-upload (file_size_limit 2 GB, mime image/*, video/*); staff insert/select/delete via is_staff() (copy the storage_quality migration).
Server: db.py storage_list(bucket), storage_get(bucket, path, dest) streaming to a file. app.py every 30 s: download objects not yet in <cache>/uploads.json into --media (.part then rename); pure `new_uploads(listing, seen)`.
Office: Files block lists tv_media; "Upload" with file_picker (add to pubspec if missing) and storage.from('wall-upload').uploadBinary, progress snackbar.
Tests: tests/test_db.py list/get request shapes and new_uploads.
Accept: uv run python tests/test_db.py; flutter analyze && flutter test.
Do not touch: files in ~/tv-media that did not come from the bucket.
