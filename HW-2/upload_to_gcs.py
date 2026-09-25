#!/usr/bin/env python3
"""
upload_to_gcs.py -- Copy a local directory of N.html files into a GCS bucket
under a prefix. This is a convenience uploader; you may equivalently use:

    gsutil -m cp -r files_12k/*.html gs://thermal-circle-508221-m7-hw2/hw2/
    # or
    gcloud storage cp files_12k/*.html gs://thermal-circle-508221-m7-hw2/hw2/

Usage:
    python3 upload_to_gcs.py --bucket thermal-circle-508221-m7-hw2 \
                             --local files_12k --prefix hw2/
"""
import argparse
import os
import time

from google.cloud import storage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--local", required=True, help="dir of N.html files")
    ap.add_argument("--prefix", default="hw2/", help="object prefix in bucket")
    args = ap.parse_args()

    prefix = args.prefix if args.prefix.endswith("/") or args.prefix == "" \
        else args.prefix + "/"

    client = storage.Client()
    bucket = client.bucket(args.bucket)

    files = sorted(
        (f for f in os.listdir(args.local) if f.endswith(".html")),
        key=lambda f: int(f[:-5]),
    )
    total = len(files)
    print(f"Uploading {total} files to gs://{args.bucket}/{prefix}")
    t0 = time.time()
    for k, fname in enumerate(files):
        blob = bucket.blob(prefix + fname)
        blob.upload_from_filename(os.path.join(args.local, fname))
        if (k + 1) % 500 == 0:
            print(f"  ...{k + 1}/{total}")
    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
