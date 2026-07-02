#!/usr/bin/env python3
"""Recover a truncated/no-moov iOS .mov by rebuilding a decodable H.264 stream.

The TRACE recorder died before finalize: the file has ftyp+wide+mdat (the H.264 sample
data, AVCC 4-byte-length-prefixed NAL units) but NO moov (no SPS/PPS, no sample table).
We borrow SPS/PPS from a VALID reference recording (same device/codec), convert the mdat's
AVCC NAL units to Annex-B, prepend the headers, and let ffmpeg decode it to frames.

    .venv/bin/python scripts/recover_mov.py <corrupt.mov> <reference.mov> --out-dir <frames>
"""
from __future__ import annotations

import argparse
import struct
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
START = b"\x00\x00\x00\x01"


def _find_mdat_data(path: Path) -> int:
    data = open(path, "rb")
    pos = 0
    size = path.stat().st_size
    while pos < size:
        data.seek(pos)
        hdr = data.read(8)
        if len(hdr) < 8:
            break
        ln = struct.unpack(">I", hdr[:4])[0]
        typ = hdr[4:8]
        if typ == b"mdat":
            return pos + 8
        if ln < 8:
            break
        pos += ln
    raise SystemExit("no mdat found")


def _ref_headers(ref: Path, tmp: Path) -> bytes:
    """Get SPS+PPS as Annex-B by transcoding the reference's first second to annexb."""
    out = tmp / "ref.h264"
    subprocess.run([FF, "-y", "-i", str(ref), "-t", "1", "-c:v", "copy",
                    "-bsf:v", "h264_mp4toannexb", "-f", "h264", str(out)],
                   check=True, capture_output=True)
    raw = out.read_bytes()
    # collect the first SPS (type 7) and PPS (type 8) Annex-B units
    parts = raw.split(START)
    sps = pps = None
    for p in parts:
        if not p:
            continue
        nal_type = p[0] & 0x1F
        if nal_type == 7 and sps is None:
            sps = p
        elif nal_type == 8 and pps is None:
            pps = p
        if sps and pps:
            break
    if not (sps and pps):
        raise SystemExit("could not extract SPS/PPS from reference")
    return START + sps + START + pps


def _avcc_to_annexb(mdat: bytes) -> tuple[bytes, int]:
    out = bytearray()
    pos = 0
    n = len(mdat)
    count = 0
    while pos + 4 <= n:
        nal_len = struct.unpack(">I", mdat[pos:pos + 4])[0]
        if nal_len == 0 or nal_len > n - pos:  # truncation / bad boundary -> stop cleanly
            break
        out += START + mdat[pos + 4:pos + 4 + nal_len]
        pos += 4 + nal_len
        count += 1
    return bytes(out), count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corrupt")
    ap.add_argument("reference")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--fps", type=float, default=2.0)
    args = ap.parse_args()

    corrupt = Path(args.corrupt)
    ref = Path(args.reference)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir

    data_off = _find_mdat_data(corrupt)
    mdat = corrupt.read_bytes()[data_off:]
    print(f"mdat data: {len(mdat)} bytes from offset {data_off}")

    headers = _ref_headers(ref, tmp)
    annexb, n_nal = _avcc_to_annexb(mdat)
    print(f"parsed {n_nal} NAL units -> {len(annexb)} annexb bytes")
    if n_nal < 10:
        raise SystemExit("too few NAL units parsed — AVCC length size may differ; abort")

    h264 = tmp / "recovered.h264"
    h264.write_bytes(headers + annexb)

    frames = out_dir / "frame_%05d.jpg"
    res = subprocess.run([FF, "-y", "-fflags", "+genpts", "-err_detect", "ignore_err",
                          "-f", "h264", "-i", str(h264),
                          "-vf", f"fps={args.fps}", "-q:v", "3", str(frames)],
                         capture_output=True, text=True)
    n_frames = len(list(out_dir.glob("frame_*.jpg")))
    print(f"ffmpeg decode rc={res.returncode}; recovered {n_frames} frames -> {out_dir}")
    if n_frames == 0:
        sys.stderr.write(res.stderr[-1500:])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
