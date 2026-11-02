"""Manual restore helper. Never point this at production without a maintenance plan."""
import os, subprocess, tempfile, urllib.parse, sys
import boto3
if os.getenv("CONFIRM_RESTORE")!="YES": raise SystemExit("Set CONFIRM_RESTORE=YES only after verifying the target database and backup.")
url=os.getenv("MIGRATION_DATABASE_URL")
bucket=os.getenv("BACKUP_BUCKET"); key=os.getenv("BACKUP_OBJECT_KEY")
if not url or not bucket or not key: raise SystemExit("MIGRATION_DATABASE_URL, BACKUP_BUCKET and BACKUP_OBJECT_KEY are required")
parsed=urllib.parse.urlparse(url)
if parsed.port==6543: raise SystemExit("Restore requires Supabase session pooler/direct URL, not transaction pooler")
s3=boto3.client("s3",region_name=os.getenv("BACKUP_REGION","af-south-1"),endpoint_url=os.getenv("BACKUP_ENDPOINT_URL") or None)
with tempfile.NamedTemporaryFile(suffix=".dump") as tmp:
    s3.download_file(bucket,key,tmp.name)
    env=os.environ.copy(); env["PGPASSWORD"]=urllib.parse.unquote(parsed.password or ""); env["PGSSLMODE"]="require"
    cmd=["pg_restore","--clean","--if-exists","--no-owner","--no-acl","--host",parsed.hostname or "","--port",str(parsed.port or 5432),"--username",urllib.parse.unquote(parsed.username or ""),"--dbname",parsed.path.lstrip("/"),tmp.name]
    subprocess.run(cmd,env=env,check=True,timeout=3600)
print("Restore command completed. Verify application data and constraints before reopening traffic.")
