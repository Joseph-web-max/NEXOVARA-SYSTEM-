"""Daily Supabase PostgreSQL backup to an S3-compatible bucket.

Run as a Render Cron Job. Use MIGRATION_DATABASE_URL (Supabase shared session
pooler on port 5432) because pg_dump needs a stable database session.
"""
import os, subprocess, tempfile, datetime, urllib.parse, sys
import boto3

url=os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
bucket=os.getenv("BACKUP_BUCKET")
if not url or not bucket:
    raise SystemExit("MIGRATION_DATABASE_URL and BACKUP_BUCKET are required")
parsed=urllib.parse.urlparse(url)
if not parsed.scheme.startswith("postgres"):
    raise SystemExit("Backup source must be Supabase/PostgreSQL, not SQLite")
if parsed.port==6543:
    raise SystemExit("Use Supabase shared SESSION pooler on port 5432 for pg_dump, not transaction mode 6543")
if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
    raise SystemExit("S3-compatible backup credentials are required")
now=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
with tempfile.NamedTemporaryFile(prefix="nexovara-",suffix=".dump") as tmp:
    env=os.environ.copy()
    env["PGPASSWORD"]=urllib.parse.unquote(parsed.password or "")
    env["PGSSLMODE"]="require"
    cmd=["pg_dump","--format=custom","--no-owner","--no-acl","--host",parsed.hostname or "","--port",str(parsed.port or 5432),"--username",urllib.parse.unquote(parsed.username or ""),"--dbname",parsed.path.lstrip("/"),"--file",tmp.name]
    subprocess.run(cmd,env=env,check=True,timeout=1800)
    tmp.flush()
    if os.path.getsize(tmp.name)<1024:
        raise SystemExit("Backup file is unexpectedly small; upload aborted")
    subprocess.run(["pg_restore","--list",tmp.name],check=True,stdout=subprocess.DEVNULL,timeout=120)
    s3=boto3.client("s3",region_name=os.getenv("BACKUP_REGION","af-south-1"),endpoint_url=os.getenv("BACKUP_ENDPOINT_URL") or None)
    key=f"nexovara/postgres/{now}.dump"
    s3.upload_file(tmp.name,bucket,key,ExtraArgs={"ServerSideEncryption":"AES256","ContentType":"application/octet-stream"})
    head=s3.head_object(Bucket=bucket,Key=key)
    if int(head.get("ContentLength",-1))!=os.path.getsize(tmp.name):
        raise SystemExit("Uploaded backup size verification failed")
    print(f"Backup uploaded and size-verified: s3://{bucket}/{key} ({os.path.getsize(tmp.name)} bytes)")
